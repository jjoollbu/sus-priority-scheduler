"""Testes do simulador de plantão (fluxo de chegadas e atendimentos)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from triagem.dominio.enums import ClassificacaoRisco as Cor
from triagem.dominio.enums import TipoEvento
from triagem.dominio.excecoes import FilaVaziaError
from triagem.dominio.paciente import Paciente
from triagem.dominio.relogio import RelogioSimulado
from triagem.fila.plantao import INICIO, ConfigPlantao, SimuladorPlantao
from triagem.fila.politicas import PoliticaAging, PoliticaSemAging


def simulador(**config: object) -> SimuladorPlantao:
    """Simulador sem aging começando em INICIO."""
    return SimuladorPlantao(
        PoliticaSemAging(),
        RelogioSimulado(INICIO),
        ConfigPlantao(**config),  # type: ignore[arg-type]
    )


class TestConfigPlantao:
    def test_capacidade_usa_a_duracao_media(self) -> None:
        config = ConfigPlantao(medicos=3, consulta_min=10, consulta_max=20)
        assert config.consulta_media_min == 15
        assert config.capacidade_por_hora == 12

    def test_padrao_consulta_entre_5_e_15_min(self) -> None:
        config = ConfigPlantao()
        assert (config.consulta_min, config.consulta_max) == (5, 15)
        assert config.capacidade_por_hora == 12  # 2 médicos, média de 10 min

    @pytest.mark.parametrize(
        "parametros",
        [
            {"chegadas_por_hora": 61},
            {"medicos": 0},
            {"consulta_min": 0},
            {"consulta_min": 10, "consulta_max": 9},
        ],
    )
    def test_parametros_invalidos(self, parametros: dict[str, int]) -> None:
        with pytest.raises(ValueError):
            ConfigPlantao(**parametros)  # type: ignore[arg-type]


class TestFluxo:
    def test_mesma_semente_mesmas_chegadas(self) -> None:
        a, b = simulador(semente=7), simulador(semente=7)
        a.avancar(240)
        b.avancar(240)
        chegadas_a = [(e.paciente.id, e.paciente.classificacao) for e in a.eventos]
        chegadas_b = [(e.paciente.id, e.paciente.classificacao) for e in b.eventos]
        assert chegadas_a == chegadas_b

    def test_chegadas_proximas_da_taxa(self) -> None:
        sim = simulador(chegadas_por_hora=15)
        sim.avancar(24 * 60)
        chegadas = sum(1 for e in sim.eventos if e.tipo is TipoEvento.ENTRADA)
        assert 15 * 24 * 0.8 < chegadas < 15 * 24 * 1.2

    def test_sem_chegadas_automaticas(self) -> None:
        sim = simulador()
        sim.chegadas_automaticas = False
        sim.avancar(120)
        assert sim.eventos == []

    def test_duracao_sorteada_dentro_dos_limites_e_varia(self) -> None:
        sim = simulador(chegadas_por_hora=30)
        sim.avancar(8 * 60)
        duracoes = [a.duracao_min for a in sim.atendimentos]
        assert all(5 <= d <= 15 for d in duracoes)
        assert len(set(duracoes)) > 1  # não é um valor fixo

    def test_mesma_semente_mesmas_duracoes(self) -> None:
        a, b = simulador(semente=7), simulador(semente=7)
        a.avancar(240)
        b.avancar(240)
        assert [x.duracao_min for x in a.atendimentos] == [
            x.duracao_min for x in b.atendimentos
        ]

    def test_medico_respeita_duracao_da_consulta(self) -> None:
        sim = simulador(medicos=2, chegadas_por_hora=30)
        sim.avancar(300)
        for medico in (1, 2):
            dele = [a for a in sim.atendimentos if a.medico == medico]
            assert len(dele) > 5
            # Só chama o próximo depois de terminar a consulta sorteada.
            assert all(b.inicio >= a.fim for a, b in zip(dele, dele[1:], strict=False))

    def test_duracao_fixa_quando_minimo_igual_ao_maximo(self) -> None:
        sim = simulador(medicos=1, consulta_min=10, consulta_max=10)
        sim.chegadas_automaticas = False
        for _ in range(3):
            sim.adicionar(
                Paciente(sim.novo_id(), "Ana", 30, "febre", Cor.VERDE, INICIO)
            )
        sim.avancar(30)
        inicios = [a.inicio for a in sim.atendimentos]
        assert inicios == [INICIO + timedelta(minutes=m) for m in (1, 11, 21)]

    def test_capacidade_limita_atendimentos(self) -> None:
        # Mesmo que todas as consultas saiam com o mínimo de 5 min.
        sim = simulador(medicos=2, chegadas_por_hora=30)
        sim.avancar(60)
        assert len(sim.atendimentos) <= 2 * 60 // 5

    def test_amostra_a_cada_10_min(self) -> None:
        sim = simulador()
        sim.avancar(60)
        assert len(sim.amostras) == 7  # 08:00, 08:10, ..., 09:00


class TestAcoesManuais:
    def test_adicionar_e_atender(self) -> None:
        sim = simulador()
        sim.chegadas_automaticas = False
        p = Paciente(sim.novo_id(), "Ana", 30, "febre", Cor.AMARELO, INICIO)
        sim.adicionar(p)
        registro = sim.atender_proximo()
        assert registro.paciente is p
        assert registro.medico is None
        assert sim.atendimento_de(p.id) is registro
        assert [e.tipo for e in sim.eventos] == [
            TipoEvento.ENTRADA,
            TipoEvento.ATENDIMENTO,
        ]

    def test_atender_fila_vazia(self) -> None:
        with pytest.raises(FilaVaziaError):
            simulador().atender_proximo()

    def test_promocao_gera_evento(self) -> None:
        # 1 médico ocupado 5 h com o Laranja: o Azul fica esperando e é promovido.
        config = ConfigPlantao(medicos=1, consulta_min=300, consulta_max=300)
        sim = SimuladorPlantao(PoliticaAging(), RelogioSimulado(INICIO), config)
        sim.chegadas_automaticas = False
        sim.adicionar(Paciente(sim.novo_id(), "Ana", 30, "receita", Cor.AZUL, INICIO))
        sim.adicionar(Paciente(sim.novo_id(), "Rui", 50, "dor", Cor.LARANJA, INICIO))
        sim.avancar(240)
        promocao = [e for e in sim.eventos if e.tipo is TipoEvento.PROMOCAO_AGING]
        assert len(promocao) == 1
        assert promocao[0].instante == INICIO + timedelta(minutes=240)


def test_resumo_inclui_quem_ainda_espera() -> None:
    sim = simulador()
    sim.chegadas_automaticas = False
    sim.adicionar(Paciente(sim.novo_id(), "Ana", 30, "receita", Cor.AZUL, INICIO))
    sim.relogio.avancar(100)
    azul = next(r for r in sim.resumo_por_cor() if r.cor is Cor.AZUL)
    assert (azul.chegaram, azul.atendidos, azul.aguardando) == (1, 0, 1)
    assert azul.maior_espera == 100
    assert azul.espera_media_atendidos is None
