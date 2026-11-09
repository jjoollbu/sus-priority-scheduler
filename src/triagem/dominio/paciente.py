"""Entidade Paciente."""

from __future__ import annotations

from datetime import datetime, timedelta

from triagem.dominio.enums import ClassificacaoRisco
from triagem.dominio.excecoes import PacienteInvalidoError

IDADE_MAXIMA = 130


class Paciente:
    """Paciente aguardando atendimento; imutável depois de criado.

    Os atributos são privados e expostos só para leitura, para que nada fora
    da classe altere a cor ou a chegada (isso quebraria a ordem da fila).
    """

    def __init__(
        self,
        id: int,
        nome: str,
        idade: int,
        queixa: str,
        classificacao: ClassificacaoRisco,
        chegada: datetime,
    ) -> None:
        """Valida os dados e cria o paciente; dados inválidos geram erro."""
        if not isinstance(id, int) or id < 0:
            raise PacienteInvalidoError("O id deve ser um inteiro maior ou igual a 0.")
        if not isinstance(nome, str) or not nome.strip():
            raise PacienteInvalidoError("O nome não pode ser vazio.")
        if not isinstance(idade, int) or not 0 <= idade <= IDADE_MAXIMA:
            raise PacienteInvalidoError(
                f"A idade deve estar entre 0 e {IDADE_MAXIMA} anos."
            )
        if not isinstance(classificacao, ClassificacaoRisco):
            raise PacienteInvalidoError("Classificação de risco inválida.")
        if not isinstance(chegada, datetime):
            raise PacienteInvalidoError("A chegada deve ser um datetime.")

        self._id = id
        self._nome = nome.strip()
        self._idade = idade
        self._queixa = queixa
        self._classificacao = classificacao
        self._chegada = chegada

    @property
    def id(self) -> int:
        """Identificador único do paciente."""
        return self._id

    @property
    def nome(self) -> str:
        """Nome do paciente."""
        return self._nome

    @property
    def idade(self) -> int:
        """Idade em anos."""
        return self._idade

    @property
    def queixa(self) -> str:
        """Queixa principal informada na triagem."""
        return self._queixa

    @property
    def classificacao(self) -> ClassificacaoRisco:
        """Cor original dada na triagem (o aging não a altera)."""
        return self._classificacao

    @property
    def chegada(self) -> datetime:
        """Instante de entrada na fila."""
        return self._chegada

    def tempo_espera(self, agora: datetime) -> float:
        """Minutos de espera até `agora`; nunca negativo."""
        return max(0.0, (agora - self._chegada).total_seconds() / 60)

    def limite_sla(self) -> datetime:
        """Instante até o qual o paciente deveria ser atendido."""
        return self._chegada + timedelta(minutes=self._classificacao.sla_minutos)

    def sla_estourado(self, agora: datetime) -> bool:
        """Verdadeiro se já passou do limite (espera igual ao SLA está no prazo)."""
        return agora > self.limite_sla()

    def __repr__(self) -> str:
        """Representação curta para depuração."""
        return (
            f"Paciente(id={self._id}, nome={self._nome!r}, "
            f"cor={self._classificacao.cor})"
        )
