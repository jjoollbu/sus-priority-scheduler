"""Políticas de fairness: como calcular o nível efetivo de um paciente."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from triagem.config import FATOR_AGING, PISO_AGING
from triagem.dominio.paciente import Paciente


class PoliticaFairness(ABC):
    """Estratégia que decide o nível efetivo usado para ordenar a fila."""

    nome: str = ""  # gravado na tabela plantao

    @abstractmethod
    def nivel_efetivo(self, p: Paciente, agora: datetime) -> int:
        """Nível usado na ordenação no instante `agora` (1 = mais urgente)."""

    def instante_de_promocao(self, p: Paciente, nivel_alvo: int) -> datetime | None:
        """Quando o paciente atinge `nivel_alvo`; None se nunca atingir.

        Padrão: sem promoções. Políticas com aging sobrescrevem.
        """
        return None


class PoliticaSemAging(PoliticaFairness):
    """Prioridade estrita pela cor original (baseline que causa starvation)."""

    nome = "SEM_AGING"

    def nivel_efetivo(self, p: Paciente, agora: datetime) -> int:
        """Sempre o nível da cor original, por mais que o paciente espere."""
        return p.classificacao.nivel


class PoliticaAging(PoliticaFairness):
    """Sobe 1 nível a cada `fator` x SLA de espera, sem passar do `piso`."""

    nome = "AGING"

    def __init__(self, fator: float = FATOR_AGING, piso: int = PISO_AGING) -> None:
        """Configura K (fator) e o nível mínimo alcançável (piso)."""
        if fator <= 0:
            raise ValueError("O fator de aging deve ser maior que zero.")
        if not 1 <= piso <= 5:
            raise ValueError("O piso deve estar entre 1 e 5.")
        self._fator = fator
        self._piso = piso

    @property
    def fator(self) -> float:
        """Fator K do aging."""
        return self._fator

    @property
    def piso(self) -> int:
        """Nível mínimo que o aging alcança."""
        return self._piso

    def _janela(self, p: Paciente) -> float:
        """Minutos de espera necessários para cada promoção (K x SLA original)."""
        return self._fator * p.classificacao.sla_minutos

    def nivel_efetivo(self, p: Paciente, agora: datetime) -> int:
        """Nível original menos as promoções acumuladas, limitado ao piso."""
        nivel = p.classificacao.nivel
        # Vermelho (e quem já está no piso ou acima dele) não é promovido.
        # Isso também evita dividir pelo SLA 0 do Vermelho.
        if nivel <= self._piso:
            return nivel
        promocoes = int(p.tempo_espera(agora) // self._janela(p))
        return max(self._piso, nivel - promocoes)

    def instante_de_promocao(self, p: Paciente, nivel_alvo: int) -> datetime | None:
        """Chegada + (nível original - alvo) janelas; None se inalcançável."""
        nivel = p.classificacao.nivel
        if nivel_alvo < self._piso or nivel_alvo >= nivel:
            return None
        minutos = (nivel - nivel_alvo) * self._janela(p)
        return p.chegada + timedelta(minutes=minutos)
