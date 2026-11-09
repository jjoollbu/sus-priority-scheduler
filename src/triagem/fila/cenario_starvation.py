"""Cenário de starvation: 1 Azul contra um fluxo contínuo de Laranjas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from triagem.dominio.enums import ClassificacaoRisco
from triagem.dominio.paciente import Paciente
from triagem.dominio.relogio import RelogioSimulado
from triagem.fila.fila_prioridade import FilaPrioridade
from triagem.fila.politicas import PoliticaFairness

INICIO = datetime(2026, 11, 24, 8, 0)
INTERVALO_CHEGADA_LARANJA = 5  # min
INTERVALO_ATENDIMENTO = 6  # min
ID_AZUL = 0


@dataclass(frozen=True)
class ResultadoCenario:
    """O que aconteceu com o paciente Azul na simulação."""

    atendido: bool
    instante: datetime | None  # quando o Azul foi atendido
    espera_min: float | None
    nivel_no_atendimento: int | None
    promocoes: list[tuple[datetime, int, int]]  # (instante, de, para)
    tamanho_fila_final: int


def _novo_paciente(
    id: int, classificacao: ClassificacaoRisco, chegada: datetime
) -> Paciente:
    """Cria um paciente fictício do cenário."""
    return Paciente(
        id=id,
        nome=f"{classificacao.cor} {id}",
        idade=40,
        queixa="cenário de starvation",
        classificacao=classificacao,
        chegada=chegada,
    )


def simular_starvation(politica: PoliticaFairness, horas: int = 16) -> ResultadoCenario:
    """Simula minuto a minuto: Laranja chega a cada 5 min, atende-se a cada 6.

    Como chegam mais Laranjas do que são atendidos, sem aging o Azul nunca sai.
    """
    fila = FilaPrioridade(politica)
    azul = _novo_paciente(ID_AZUL, ClassificacaoRisco.AZUL, INICIO)
    fila.inserir(azul)

    promocoes: list[tuple[datetime, int, int]] = []
    nivel_anterior = fila.nivel_efetivo(azul, INICIO)
    proximo_id = 1

    for m in range(horas * 60 + 1):
        agora = INICIO + timedelta(minutes=m)

        # 1) registra promoção do Azul, se o nível efetivo mudou
        nivel_atual = fila.nivel_efetivo(azul, agora)
        if nivel_atual != nivel_anterior:
            promocoes.append((agora, nivel_anterior, nivel_atual))
            nivel_anterior = nivel_atual

        # 2) chegada de um Laranja
        if m % INTERVALO_CHEGADA_LARANJA == 0:
            fila.inserir(_novo_paciente(proximo_id, ClassificacaoRisco.LARANJA, agora))
            proximo_id += 1

        # 3) atendimento
        if m % INTERVALO_ATENDIMENTO == 0:
            atendido = fila.retirar_proximo(agora)
            if atendido.id == ID_AZUL:
                return ResultadoCenario(
                    atendido=True,
                    instante=agora,
                    espera_min=azul.tempo_espera(agora),
                    nivel_no_atendimento=nivel_atual,
                    promocoes=promocoes,
                    tamanho_fila_final=len(fila),
                )

    return ResultadoCenario(
        atendido=False,
        instante=None,
        espera_min=None,
        nivel_no_atendimento=None,
        promocoes=promocoes,
        tamanho_fila_final=len(fila),
    )


def montar_fila_inicial(
    politica: PoliticaFairness, relogio: RelogioSimulado, qtd_laranjas: int = 6
) -> FilaPrioridade:
    """Fila para a tela: 1 Azul e N Laranjas chegando de 5 em 5 min.

    Todos chegam a partir de `relogio.agora()`; o relógio avança junto com as
    chegadas, para que ninguém fique com chegada no futuro.
    """
    fila = FilaPrioridade(politica)
    fila.inserir(_novo_paciente(ID_AZUL, ClassificacaoRisco.AZUL, relogio.agora()))
    for i in range(1, qtd_laranjas + 1):
        if i > 1:
            relogio.avancar(INTERVALO_CHEGADA_LARANJA)
        fila.inserir(_novo_paciente(i, ClassificacaoRisco.LARANJA, relogio.agora()))
    return fila