"""T3 e T4: plantão de 24 h com muitos pacientes, com e sem aging.

Cenário: UPA superlotada, com 15 chegadas por hora e capacidade de 12 por hora
(2 médicos, 10 min por consulta). As duas simulações recebem exatamente os
mesmos pacientes; só muda a política de fairness.
"""

from __future__ import annotations

import pytest

from triagem.dominio.enums import ClassificacaoRisco as Cor
from triagem.dominio.enums import TipoEvento
from triagem.fila.plantao import (
    ConfigPlantao,
    ResumoCor,
    SimuladorPlantao,
    rodar_plantao,
)
from triagem.fila.politicas import PoliticaAging, PoliticaSemAging

HORAS = 24
CONFIG = ConfigPlantao(chegadas_por_hora=15, medicos=2, duracao_consulta_min=10)


@pytest.fixture(scope="module")
def sem_aging() -> SimuladorPlantao:
    return rodar_plantao(PoliticaSemAging(), HORAS, CONFIG)


@pytest.fixture(scope="module")
def com_aging() -> SimuladorPlantao:
    return rodar_plantao(PoliticaAging(), HORAS, CONFIG)


def resumo(sim: SimuladorPlantao, cor: Cor) -> ResumoCor:
    return next(r for r in sim.resumo_por_cor() if r.cor is cor)


def test_mesmos_pacientes_nas_duas_simulacoes(
    sem_aging: SimuladorPlantao, com_aging: SimuladorPlantao
) -> None:
    def chegadas(sim: SimuladorPlantao) -> list[tuple[int, Cor]]:
        return [
            (e.paciente.id, e.paciente.classificacao)
            for e in sim.eventos
            if e.tipo is TipoEvento.ENTRADA
        ]

    assert chegadas(sem_aging) == chegadas(com_aging)
    assert len(chegadas(sem_aging)) > 300  # muitos pacientes


def test_t3_sem_aging_nenhum_azul_e_atendido(sem_aging: SimuladorPlantao) -> None:
    azul = resumo(sem_aging, Cor.AZUL)
    assert azul.chegaram >= 40
    assert azul.atendidos == 0
    # O Azul mais antigo esperou praticamente o plantão inteiro e segue na fila.
    assert azul.maior_espera > 23 * 60


def test_t3_espera_do_azul_cresce_sem_parar(sem_aging: SimuladorPlantao) -> None:
    serie = [a.maior_espera_por_cor[Cor.AZUL] for a in sem_aging.amostras]
    depois_da_primeira_chegada = [e for e in serie if e > 0]
    assert depois_da_primeira_chegada == sorted(depois_da_primeira_chegada)


def test_t3_cores_graves_continuam_bem_atendidas(sem_aging: SimuladorPlantao) -> None:
    # A starvation atinge só quem tem baixa prioridade.
    assert resumo(sem_aging, Cor.VERMELHO).aguardando == 0
    assert resumo(sem_aging, Cor.LARANJA).aguardando == 0


def test_t4_com_aging_azuis_sao_atendidos(com_aging: SimuladorPlantao) -> None:
    azul = resumo(com_aging, Cor.AZUL)
    assert azul.atendidos >= azul.chegaram // 2


def test_t4_com_aging_espera_maxima_fica_limitada(
    sem_aging: SimuladorPlantao, com_aging: SimuladorPlantao
) -> None:
    maior_sem = resumo(sem_aging, Cor.AZUL).maior_espera
    maior_com = resumo(com_aging, Cor.AZUL).maior_espera
    assert maior_com < 12 * 60
    assert maior_com < maior_sem / 2


def test_t4_vermelho_nao_e_prejudicado(
    sem_aging: SimuladorPlantao, com_aging: SimuladorPlantao
) -> None:
    assert resumo(com_aging, Cor.VERMELHO).maior_espera <= (
        resumo(sem_aging, Cor.VERMELHO).maior_espera
    )


def test_aging_nao_cria_capacidade(
    sem_aging: SimuladorPlantao, com_aging: SimuladorPlantao
) -> None:
    # Mesmo número de consultas: o aging só muda QUEM é chamado.
    assert len(sem_aging.atendimentos) == len(com_aging.atendimentos)


def test_sem_sobrecarga_nao_ha_starvation() -> None:
    folgado = ConfigPlantao(chegadas_por_hora=9, medicos=2, duracao_consulta_min=10)
    sim = rodar_plantao(PoliticaSemAging(), HORAS, folgado)
    azul = resumo(sim, Cor.AZUL)
    assert azul.atendidos >= azul.chegaram - 1
    assert azul.maior_espera < 4 * 60
