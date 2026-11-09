"""Fila de prioridade da triagem: 5 filas FIFO, uma por cor."""

from __future__ import annotations

from collections import deque
from datetime import datetime

from triagem.dominio.enums import ClassificacaoRisco
from triagem.dominio.excecoes import (
    FilaVaziaError,
    PacienteInvalidoError,
    PacienteNaoEncontradoError,
)
from triagem.dominio.paciente import Paciente
from triagem.fila.politicas import PoliticaFairness


class FilaPrioridade:
    """Fila de atendimento ordenada por (nível efetivo, chegada, id).

    Agrega pacientes já criados (não os cria). A política de fairness é
    injetada, então a mesma fila funciona com ou sem aging (polimorfismo).
    """

    def __init__(self, politica: PoliticaFairness) -> None:
        """Cria as 5 filas vazias e guarda a política de fairness."""
        self._filas: dict[ClassificacaoRisco, deque[Paciente]] = {
            cor: deque() for cor in ClassificacaoRisco
        }
        self._politica = politica
        self._ids: set[int] = set()  # ids aguardando, para checar repetição em O(1)

    @property
    def politica(self) -> PoliticaFairness:
        """Política de fairness em uso."""
        return self._politica

    def _chave(self, p: Paciente, agora: datetime) -> tuple[int, datetime, int]:
        """Critério de ordenação: mais urgente, depois quem chegou antes, depois id."""
        return (self.nivel_efetivo(p, agora), p.chegada, p.id)

    def validar_insercao(self, p: Paciente) -> None:
        """Erro se `p` não puder entrar na fila; não altera nada. O(1).

        Separado de `inserir` para o serviço validar ANTES de gravar no banco.
        """
        if p.id in self._ids:
            raise PacienteInvalidoError(f"Já existe paciente com id {p.id} na fila.")
        fila = self._filas[p.classificacao]
        # Cada fila precisa estar em ordem de (chegada, id): o `proximo` depende disso.
        if fila and (p.chegada, p.id) < (fila[-1].chegada, fila[-1].id):
            raise PacienteInvalidoError(
                "Chegada anterior à do último paciente da mesma cor."
            )

    def inserir(self, p: Paciente) -> None:
        """Coloca o paciente no fim da fila da sua cor original. O(1)."""
        self.validar_insercao(p)
        self._filas[p.classificacao].append(p)
        self._ids.add(p.id)

    def proximo(self, agora: datetime) -> Paciente:
        """Devolve, sem retirar, quem deve ser atendido agora. O(1).

        Basta comparar as cabeças das 5 filas: dentro de uma mesma cor, quem
        chegou antes esperou mais e, como o aging depende só do tempo de espera
        e da cor original, tem nível efetivo menor ou igual ao de quem está
        atrás. Logo a cabeça sempre vence o resto da sua própria fila.
        """
        cabecas = [fila[0] for fila in self._filas.values() if fila]
        if not cabecas:
            raise FilaVaziaError("Não há pacientes aguardando.")
        return min(cabecas, key=lambda p: self._chave(p, agora))

    def retirar_proximo(self, agora: datetime) -> Paciente:
        """Retira e devolve quem deve ser atendido agora. O(1)."""
        p = self.proximo(agora)
        self._filas[p.classificacao].popleft()
        self._ids.discard(p.id)
        return p

    def remover(self, paciente_id: int) -> Paciente:
        """Retira um paciente específico (ex.: desistência). O(n)."""
        for fila in self._filas.values():
            for p in fila:
                if p.id == paciente_id:
                    fila.remove(p)
                    self._ids.discard(p.id)
                    return p
        raise PacienteNaoEncontradoError(f"Paciente {paciente_id} não está na fila.")

    def listar_ordenada(self, agora: datetime) -> list[Paciente]:
        """Todos os pacientes na ordem em que seriam atendidos. O(n log n)."""
        return sorted(self.aguardando(), key=lambda p: self._chave(p, agora))

    def nivel_efetivo(self, p: Paciente, agora: datetime) -> int:
        """Nível efetivo do paciente segundo a política atual. O(1)."""
        return self._politica.nivel_efetivo(p, agora)

    def aguardando(self) -> list[Paciente]:
        """Cópia da lista de pacientes (não expõe os deques internos). O(n)."""
        return [p for fila in self._filas.values() for p in fila]

    def contagem_por_cor(self) -> dict[ClassificacaoRisco, int]:
        """Quantidade aguardando em cada uma das 5 cores. O(1)."""
        return {cor: len(fila) for cor, fila in self._filas.items()}

    def tamanho(self) -> int:
        """Total de pacientes aguardando. O(1)."""
        return len(self._ids)

    def __len__(self) -> int:
        """Permite usar `len(fila)`."""
        return self.tamanho()
