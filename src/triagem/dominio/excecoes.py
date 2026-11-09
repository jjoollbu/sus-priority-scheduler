"""Exceções do domínio da triagem."""

from __future__ import annotations


class ErroTriagem(Exception):
    """Base de todos os erros do domínio, para capturá-los de uma vez."""


class FilaVaziaError(ErroTriagem):
    """Tentativa de consultar ou retirar paciente de uma fila vazia."""


class PacienteInvalidoError(ErroTriagem):
    """Dados do paciente inválidos ou id repetido na fila."""


class PacienteNaoEncontradoError(ErroTriagem):
    """O paciente procurado não está aguardando na fila."""
