"""Evento da trilha de auditoria (uma linha da tabela evento_fila)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from triagem.dominio.enums import ClassificacaoRisco, TipoEvento
from triagem.dominio.paciente import Paciente


@dataclass(frozen=True)
class EventoFila:
    """Algo que aconteceu com um paciente; imutável, como no banco."""

    tipo: TipoEvento
    instante: datetime
    paciente: Paciente
    nivel_efetivo: int
    detalhes: str
    contagem_por_cor: dict[ClassificacaoRisco, int]  # fila LOGO APÓS o evento

    @property
    def paciente_id(self) -> int:
        """Id do paciente do evento."""
        return self.paciente.id

    @property
    def tamanho_fila(self) -> int:
        """Total de pacientes na fila logo após o evento."""
        return sum(self.contagem_por_cor.values())
