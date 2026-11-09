"""Classificação de risco (Protocolo de Manchester simplificado)."""

from __future__ import annotations

from enum import Enum

from triagem.config import SLA_MINUTOS


class ClassificacaoRisco(Enum):
    """As 5 cores da triagem; o valor é o nível (1 = mais grave)."""

    VERMELHO = 1
    LARANJA = 2
    AMARELO = 3
    VERDE = 4
    AZUL = 5

    @property
    def nivel(self) -> int:
        """Nível de prioridade: 1 é o mais grave, 5 o menos grave."""
        return self.value

    @property
    def cor(self) -> str:
        """Nome da cor para exibição (ex.: "Laranja")."""
        return self.name.capitalize()

    @property
    def sla_minutos(self) -> int:
        """Tempo-alvo de atendimento da cor, lido da configuração."""
        return SLA_MINUTOS[self.value]

    @staticmethod
    def from_cor(cor: str) -> ClassificacaoRisco:
        """Converte texto em cor, ignorando maiúsculas e espaços nas pontas."""
        chave = cor.strip().upper()
        try:
            return ClassificacaoRisco[chave]
        except KeyError:
            raise ValueError(f"Cor inválida: {cor!r}") from None

    @staticmethod
    def from_nivel(nivel: int) -> ClassificacaoRisco:
        """Converte um nível (1 a 5) na cor correspondente."""
        try:
            return ClassificacaoRisco(nivel)
        except ValueError:
            raise ValueError(f"Nível inválido: {nivel!r}") from None


class TipoEvento(Enum):
    """Tipos de evento da trilha de auditoria (tabela evento_fila)."""

    ENTRADA = "ENTRADA"
    PROMOCAO_AGING = "PROMOCAO_AGING"
    ATENDIMENTO = "ATENDIMENTO"
    REMOCAO = "REMOCAO"
    ATRASO_SLA = "ATRASO_SLA"


def _validar_sla() -> None:
    """Garante SLA definido para todas as cores e > 0 nos níveis 2-5.

    O aging divide a espera pelo SLA; SLA zero nesses níveis dividiria por zero.
    """
    for classificacao in ClassificacaoRisco:
        if classificacao.value not in SLA_MINUTOS:
            raise ValueError(f"SLA não configurado para {classificacao.cor}")
        if classificacao.value >= 2 and SLA_MINUTOS[classificacao.value] <= 0:
            raise ValueError(f"SLA de {classificacao.cor} precisa ser maior que zero")


_validar_sla()
