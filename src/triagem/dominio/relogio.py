"""Relógios: fonte do instante atual, real ou simulada."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta


class Relogio(ABC):
    """Abstração do "agora"; permite trocar o tempo real por um simulado."""

    @abstractmethod
    def agora(self) -> datetime:
        """Devolve o instante atual segundo este relógio."""


class RelogioSimulado(Relogio):
    """Relógio controlado manualmente, usado na tela e nos testes."""

    def __init__(self, inicio: datetime) -> None:
        """Cria o relógio parado no instante `inicio`."""
        self._atual = inicio

    def agora(self) -> datetime:
        """Devolve o instante simulado atual."""
        return self._atual

    def avancar(self, minutos: float) -> None:
        """Avança o relógio; o tempo não pode voltar."""
        if minutos < 0:
            raise ValueError("Não é possível voltar o relógio.")
        self._atual += timedelta(minutes=minutos)


class RelogioSistema(Relogio):
    """Relógio real do computador."""

    def agora(self) -> datetime:
        """Devolve a data e hora atuais do sistema."""
        return datetime.now()
