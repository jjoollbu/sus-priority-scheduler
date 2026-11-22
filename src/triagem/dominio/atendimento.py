"""Atendimento: o resultado de chamar um paciente (uma linha da tabela atendimento)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from triagem.dominio.paciente import Paciente


@dataclass(frozen=True)
class Atendimento:
    """Paciente chamado para consulta; imutável depois de criado."""

    paciente: Paciente
    inicio: datetime
    espera_min: float
    nivel_efetivo: int
    medico: int | None  # None quando a chamada é manual
    duracao_min: int  # sorteada pelo simulador

    def __post_init__(self) -> None:
        """Recusa consulta sem duração."""
        if self.duracao_min < 1:
            raise ValueError("A consulta precisa durar ao menos 1 min.")

    @property
    def fim(self) -> datetime:
        """Instante em que a consulta termina e o médico fica livre."""
        return self.inicio + timedelta(minutes=self.duracao_min)

    @property
    def dentro_do_sla(self) -> bool:
        """Atendido dentro do tempo-alvo da cor original (espera igual ao SLA vale)."""
        return self.espera_min <= self.paciente.classificacao.sla_minutos
