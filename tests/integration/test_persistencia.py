"""Integração com o SQLite: gravação, trilha de auditoria, append-only e logs.sql.

Usa banco em memória (`:memory:`): rápido e sem deixar arquivos.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from triagem.config import CAMINHO_SCHEMA
from triagem.dominio.atendimento import Atendimento
from triagem.dominio.enums import ClassificacaoRisco as Cor
from triagem.dominio.evento import EventoFila
from triagem.dominio.paciente import Paciente
from triagem.dominio.relogio import RelogioSimulado
from triagem.fila.plantao import (
    INICIO,
    ConfigPlantao,
    RegistroPlantao,
    SimuladorPlantao,
    rodar_plantao,
)
from triagem.fila.politicas import PoliticaAging, PoliticaSemAging
from triagem.persistencia import repositorio
from triagem.persistencia.conexao import abrir_conexao
from triagem.persistencia.exportador_sql import exportar_logs, literal_sql
from triagem.persistencia.repositorio import RepositorioPlantao


@pytest.fixture
def conexao() -> sqlite3.Connection:
    return abrir_conexao()


def contar(conexao: sqlite3.Connection, tabela: str) -> int:
    return conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


def plantao_gravado(
    conexao: sqlite3.Connection, horas: int = 4, politica=None
) -> SimuladorPlantao:
    """Roda um plantão gravando no banco."""
    politica = politica or PoliticaSemAging()
    config = ConfigPlantao()
    repo = RepositorioPlantao.novo_plantao(conexao, politica, config, INICIO)
    return rodar_plantao(politica, horas, config, registro=repo)


class TestSchema:
    def test_tabelas_e_catalogo(self, conexao: sqlite3.Connection) -> None:
        tabelas = {
            r[0]
            for r in conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "classificacao",
            "plantao",
            "paciente",
            "evento_fila",
            "atendimento",
        } <= (tabelas)
        azul = conexao.execute(
            "SELECT cor, sla_minutos FROM classificacao WHERE nivel = 5"
        ).fetchone()
        assert tuple(azul) == ("AZUL", 240)

    def test_abrir_duas_vezes_nao_duplica_catalogo(self, tmp_path) -> None:
        caminho = tmp_path / "triagem.db"
        abrir_conexao(caminho).close()
        conexao = abrir_conexao(caminho)
        assert contar(conexao, "classificacao") == 5

    def test_banco_recusa_dados_invalidos(self, conexao: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conexao.execute(
                "INSERT INTO plantao (inicio, politica, chegadas_por_hora, medicos, "
                "duracao_consulta_min, semente) VALUES ('x', 'OUTRA', 1, 1, 1, 1)"
            )


class TestGravacao:
    def test_memoria_e_banco_batem(self, conexao: sqlite3.Connection) -> None:
        sim = plantao_gravado(conexao, horas=6, politica=PoliticaAging())
        assert contar(conexao, "paciente") == sum(
            r.chegaram for r in sim.resumo_por_cor()
        )
        assert contar(conexao, "evento_fila") == len(sim.eventos)
        assert contar(conexao, "atendimento") == len(sim.atendimentos)

    def test_evento_guarda_fila_por_cor(self, conexao: sqlite3.Connection) -> None:
        plantao_gravado(conexao, horas=2)
        linhas = conexao.execute(
            "SELECT total, qtd_vermelho + qtd_laranja + qtd_amarelo + qtd_verde "
            "+ qtd_azul AS soma FROM evento_fila"
        ).fetchall()
        assert linhas and all(r["total"] == r["soma"] for r in linhas)

    def test_dois_plantoes_no_mesmo_banco(self, conexao: sqlite3.Connection) -> None:
        plantao_gravado(conexao, horas=1)
        plantao_gravado(conexao, horas=1, politica=PoliticaAging())
        plantoes = repositorio.listar_plantoes(conexao)
        assert [p["politica"] for p in plantoes] == ["AGING", "SEM_AGING"]
        assert all(p["pacientes"] > 0 for p in plantoes)


def test_trilha_de_auditoria_do_azul(conexao: sqlite3.Connection) -> None:
    """Reproduz a trilha da seção 10 das regras de negócio.

    1 médico ocupado com um Laranja até as 20:00; o Azul espera e é promovido.
    """
    config = ConfigPlantao(medicos=1, duracao_consulta_min=719)
    politica = PoliticaAging()
    repo = RepositorioPlantao.novo_plantao(conexao, politica, config, INICIO)
    sim = SimuladorPlantao(
        politica, RelogioSimulado(INICIO), config, chegadas_automaticas=False,
        registro=repo,
    )  # fmt: skip
    sim.adicionar(Paciente(sim.novo_id(), "Gabriela", 40, "receita", Cor.AZUL, INICIO))
    sim.adicionar(
        Paciente(sim.novo_id(), "Rui", 50, "dor no peito", Cor.LARANJA, INICIO)
    )
    sim.avancar(12 * 60)

    trilha = [
        (r["instante"][11:16], r["tipo"], r["nivel_efetivo"], r["total"])
        for r in repositorio.eventos(conexao, repo.plantao_id, paciente_id=1)
    ]
    assert trilha == [
        ("08:00", "ENTRADA", 5, 1),
        ("12:00", "PROMOCAO_AGING", 4, 1),
        ("12:00", "ATRASO_SLA", 4, 1),
        ("16:00", "PROMOCAO_AGING", 3, 1),
        ("20:00", "PROMOCAO_AGING", 2, 1),
        ("20:00", "ATENDIMENTO", 2, 0),
    ]
    atendido = repositorio.atendimentos(conexao, repo.plantao_id)[0]
    assert (atendido["espera_min"], atendido["dentro_do_sla"]) == (720, 0)


class TestAppendOnly:
    def test_nao_deixa_alterar_nem_apagar_eventos(
        self, conexao: sqlite3.Connection
    ) -> None:
        plantao_gravado(conexao, horas=1)
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conexao.execute("UPDATE evento_fila SET detalhes = 'editado'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conexao.execute("DELETE FROM evento_fila")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conexao.execute("DELETE FROM atendimento")


class TestCommitAntesDaMemoria:
    """Se a gravação falhar, a fila em memória não pode mudar."""

    class RegistroQueFalha(RegistroPlantao):
        def registrar_entrada(self, evento: EventoFila) -> None:
            raise sqlite3.OperationalError("banco indisponível")

        def registrar_evento(self, evento: EventoFila) -> None:
            raise sqlite3.OperationalError("banco indisponível")

        def registrar_atendimento(
            self, atendimento: Atendimento, evento: EventoFila
        ) -> None:
            raise sqlite3.OperationalError("banco indisponível")

    def test_entrada_nao_entra_na_fila(self) -> None:
        sim = SimuladorPlantao(
            PoliticaSemAging(), RelogioSimulado(INICIO),
            registro=self.RegistroQueFalha(),
        )  # fmt: skip
        with pytest.raises(sqlite3.OperationalError):
            sim.adicionar(Paciente(1, "Ana", 30, "febre", Cor.VERDE, INICIO))
        assert len(sim.fila) == 0
        assert sim.eventos == []

    def test_atendimento_nao_tira_da_fila(self, conexao: sqlite3.Connection) -> None:
        repo = RepositorioPlantao.novo_plantao(
            conexao, PoliticaSemAging(), ConfigPlantao(), INICIO
        )
        sim = SimuladorPlantao(
            PoliticaSemAging(), RelogioSimulado(INICIO), registro=repo
        )
        sim.adicionar(Paciente(1, "Ana", 30, "febre", Cor.VERDE, INICIO))
        sim._registro = self.RegistroQueFalha()  # banco "cai" depois da entrada
        with pytest.raises(sqlite3.OperationalError):
            sim.atender_proximo()
        assert len(sim.fila) == 1
        assert sim.atendimentos == []


class TestExportador:
    def test_literal_sql(self) -> None:
        assert literal_sql(None) == "NULL"
        assert literal_sql(3) == "3"
        assert literal_sql("D'Ávila") == "'D''Ávila'"

    def test_logs_recriam_o_historico_em_banco_vazio(
        self, conexao: sqlite3.Connection
    ) -> None:
        sim = plantao_gravado(conexao, horas=3)
        logs = exportar_logs(conexao)

        novo = sqlite3.connect(":memory:")
        novo.executescript(CAMINHO_SCHEMA.read_text(encoding="utf-8"))
        novo.executescript(logs)
        for tabela in ("classificacao", "plantao", "paciente", "evento_fila"):
            assert contar(novo, tabela) == contar(conexao, tabela)
        assert contar(novo, "atendimento") == len(sim.atendimentos)

    def test_exporta_so_um_plantao(self, conexao: sqlite3.Connection) -> None:
        plantao_gravado(conexao, horas=1)
        plantao_gravado(conexao, horas=1)
        logs = exportar_logs(conexao, plantao_id=2)
        novo = sqlite3.connect(":memory:")
        novo.executescript(CAMINHO_SCHEMA.read_text(encoding="utf-8"))
        novo.executescript(logs)
        assert [r[0] for r in novo.execute("SELECT id FROM plantao")] == [2]


def test_instantes_em_iso() -> None:
    assert repositorio.iso(datetime(2026, 11, 24, 8, 5)) == "2026-11-24T08:05:00"
