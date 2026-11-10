"""Repositório SQLite do plantão: grava eventos e atendimentos e os consulta."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from triagem.dominio.atendimento import Atendimento
from triagem.dominio.enums import ClassificacaoRisco
from triagem.dominio.evento import EventoFila
from triagem.fila.plantao import ConfigPlantao, RegistroPlantao
from triagem.fila.politicas import PoliticaFairness

FORMATO_ISO = "%Y-%m-%dT%H:%M:%S"


def iso(instante: datetime) -> str:
    """Instante em texto ISO-8601, como está no banco."""
    return instante.strftime(FORMATO_ISO)


class RepositorioPlantao(RegistroPlantao):
    """Implementa a porta RegistroPlantao gravando num banco SQLite.

    Cada método é uma transação: `with self._conexao:` faz commit no fim ou
    rollback se der erro. Como o simulador só mexe na fila depois que o método
    retorna, a fila em memória nunca fica à frente do banco.
    """

    def __init__(self, conexao: sqlite3.Connection, plantao_id: int) -> None:
        """Usa um plantão que já existe no banco."""
        self._conexao = conexao
        self._plantao_id = plantao_id

    @classmethod
    def novo_plantao(
        cls,
        conexao: sqlite3.Connection,
        politica: PoliticaFairness,
        config: ConfigPlantao,
        inicio: datetime,
    ) -> RepositorioPlantao:
        """Cria a linha do plantão (regra da fila e parâmetros) e devolve o repo."""
        with conexao:
            cursor = conexao.execute(
                "INSERT INTO plantao (inicio, politica, chegadas_por_hora, medicos, "
                "duracao_consulta_min, semente) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    iso(inicio),
                    politica.nome,
                    config.chegadas_por_hora,
                    config.medicos,
                    config.duracao_consulta_min,
                    config.semente,
                ),
            )
        return cls(conexao, int(cursor.lastrowid))

    @property
    def plantao_id(self) -> int:
        """Id do plantão no banco."""
        return self._plantao_id

    # ----- porta RegistroPlantao -----
    def registrar_entrada(self, evento: EventoFila) -> None:
        """Grava o paciente e o evento ENTRADA na mesma transação."""
        p = evento.paciente
        with self._conexao:
            self._conexao.execute(
                "INSERT INTO paciente (plantao_id, id, nome, idade, queixa, nivel, "
                "chegada) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    self._plantao_id,
                    p.id,
                    p.nome,
                    p.idade,
                    p.queixa,
                    p.classificacao.nivel,
                    iso(p.chegada),
                ),
            )
            self._inserir_evento(evento)

    def registrar_evento(self, evento: EventoFila) -> None:
        """Grava um evento avulso (promoção ou atraso)."""
        with self._conexao:
            self._inserir_evento(evento)

    def registrar_atendimento(
        self, atendimento: Atendimento, evento: EventoFila
    ) -> None:
        """Grava o atendimento e o evento ATENDIMENTO na mesma transação."""
        with self._conexao:
            self._conexao.execute(
                "INSERT INTO atendimento (plantao_id, paciente_id, inicio, espera_min, "
                "nivel_efetivo, dentro_do_sla, medico) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    self._plantao_id,
                    atendimento.paciente.id,
                    iso(atendimento.inicio),
                    atendimento.espera_min,
                    atendimento.nivel_efetivo,
                    int(atendimento.dentro_do_sla),
                    atendimento.medico,
                ),
            )
            self._inserir_evento(evento)

    def _inserir_evento(self, evento: EventoFila) -> None:
        """INSERT de uma linha em evento_fila (sem commit: quem chama decide)."""
        c = evento.contagem_por_cor
        self._conexao.execute(
            "INSERT INTO evento_fila (plantao_id, paciente_id, tipo, instante, "
            "nivel_efetivo, detalhes, qtd_vermelho, qtd_laranja, qtd_amarelo, "
            "qtd_verde, qtd_azul, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self._plantao_id,
                evento.paciente_id,
                evento.tipo.value,
                iso(evento.instante),
                evento.nivel_efetivo,
                evento.detalhes,
                c[ClassificacaoRisco.VERMELHO],
                c[ClassificacaoRisco.LARANJA],
                c[ClassificacaoRisco.AMARELO],
                c[ClassificacaoRisco.VERDE],
                c[ClassificacaoRisco.AZUL],
                evento.tamanho_fila,
            ),
        )


# ----- consultas (leitura) usadas pela tela -----
def listar_plantoes(conexao: sqlite3.Connection) -> list[sqlite3.Row]:
    """Plantões gravados, do mais recente ao mais antigo, com totais."""
    return conexao.execute(
        """
        SELECT pl.id, pl.inicio, pl.politica, pl.chegadas_por_hora, pl.medicos,
               pl.duracao_consulta_min, pl.semente,
               (SELECT COUNT(*) FROM paciente p WHERE p.plantao_id = pl.id)
                   AS pacientes,
               (SELECT COUNT(*) FROM atendimento a WHERE a.plantao_id = pl.id)
                   AS atendidos,
               (SELECT COUNT(*) FROM evento_fila e WHERE e.plantao_id = pl.id)
                   AS eventos
        FROM plantao pl
        ORDER BY pl.id DESC
        """
    ).fetchall()


def eventos(
    conexao: sqlite3.Connection,
    plantao_id: int,
    paciente_id: int | None = None,
    limite: int | None = None,
    mais_recentes_primeiro: bool = False,
) -> list[sqlite3.Row]:
    """Eventos de um plantão (opcionalmente de um paciente), com nome e cor."""
    sql = """
        SELECT e.id, e.instante, e.tipo, e.paciente_id, p.nome, c.cor,
               e.nivel_efetivo, e.detalhes, e.total
        FROM evento_fila e
        JOIN paciente p ON p.plantao_id = e.plantao_id AND p.id = e.paciente_id
        JOIN classificacao c ON c.nivel = p.nivel
        WHERE e.plantao_id = ?
    """
    parametros: list[object] = [plantao_id]
    if paciente_id is not None:
        sql += " AND e.paciente_id = ?"
        parametros.append(paciente_id)
    sql += " ORDER BY e.id DESC" if mais_recentes_primeiro else " ORDER BY e.id"
    if limite is not None:
        sql += " LIMIT ?"
        parametros.append(limite)
    return conexao.execute(sql, parametros).fetchall()


def atendimentos(conexao: sqlite3.Connection, plantao_id: int) -> list[sqlite3.Row]:
    """Atendimentos de um plantão, do mais recente ao mais antigo."""
    return conexao.execute(
        """
        SELECT a.inicio, a.medico, a.paciente_id, p.nome, c.cor,
               a.nivel_efetivo, a.espera_min, a.dentro_do_sla
        FROM atendimento a
        JOIN paciente p ON p.plantao_id = a.plantao_id AND p.id = a.paciente_id
        JOIN classificacao c ON c.nivel = p.nivel
        WHERE a.plantao_id = ?
        ORDER BY a.inicio DESC, a.paciente_id DESC
        """,
        (plantao_id,),
    ).fetchall()


def buscar_pacientes(
    conexao: sqlite3.Connection, plantao_id: int, texto: str
) -> list[sqlite3.Row]:
    """Pacientes do plantão cujo nome contém `texto` ou cujo id é `texto`."""
    return conexao.execute(
        """
        SELECT p.id, p.nome, c.cor, p.chegada
        FROM paciente p JOIN classificacao c ON c.nivel = p.nivel
        WHERE p.plantao_id = ? AND (p.nome LIKE ? OR CAST(p.id AS TEXT) = ?)
        ORDER BY p.id
        """,
        (plantao_id, f"%{texto.strip()}%", texto.strip()),
    ).fetchall()
