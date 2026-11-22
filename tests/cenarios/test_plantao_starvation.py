"""T3 e T4: plantão de 24 h com muitos pacientes, com e sem aging.

Cenário: UPA superlotada, com 15 chegadas por hora e capacidade média de 12 por
hora (2 médicos, consulta sorteada entre 5 e 15 min). As duas simulações recebem
exatamente os mesmos pacientes e as mesmas durações; só muda a política.
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
CONFIG = ConfigPlantao(chegadas_por_hora=15, medicos=2)


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


def test_t3_sem_aging_quase_nenhum_azul_e_atendido(
    sem_aging: SimuladorPlantao,
) -> None:
    azul = resumo(sem_aging, Cor.AZUL)
    assert azul.chegaram >= 40
    # Com a duração sorteada, às vezes sobra um médico e um Azul é chamado;
    # ainda assim, a grande maioria nunca é atendida.
    assert azul.atendidos <= azul.chegaram // 4
    assert azul.aguardando >= 30
    # O Azul mais antigo que segue na fila espera há mais de 18 h.
    assert azul.maior_espera > 18 * 60


def test_t3_sempre_ha_azul_com_prazo_estourado(sem_aging: SimuladorPlantao) -> None:
    # Depois que a fila se forma (14:00), sempre há um Azul além do SLA de 4 h.
    sla = Cor.AZUL.sla_minutos
    inicio = sem_aging.amostras[0].instante
    depois_das_14h = [
        a.maior_espera_por_cor[Cor.AZUL]
        for a in sem_aging.amostras
        if (a.instante - inicio).total_seconds() >= 6 * 3600
    ]
    assert depois_das_14h and all(espera > sla for espera in depois_das_14h)


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


def test_mesmas_duracoes_nas_duas_simulacoes(
    sem_aging: SimuladorPlantao, com_aging: SimuladorPlantao
) -> None:
    # A n-ésima consulta dura o mesmo nas duas: a comparação continua justa.
    def agenda(sim: SimuladorPlantao) -> list[tuple[object, int | None, int]]:
        return [(a.inicio, a.medico, a.duracao_min) for a in sim.atendimentos]

    assert agenda(sem_aging) == agenda(com_aging)


def test_sem_sobrecarga_nao_ha_starvation() -> None:
    folgado = ConfigPlantao(chegadas_por_hora=9, medicos=2)
    sim = rodar_plantao(PoliticaSemAging(), HORAS, folgado)
    azul = resumo(sim, Cor.AZUL)
    assert azul.atendidos >= azul.chegaram - 1
    assert azul.maior_espera < 4 * 60
