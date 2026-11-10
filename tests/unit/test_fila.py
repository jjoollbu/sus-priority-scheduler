"""Testes da fila de prioridade e das políticas de fairness."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from triagem.dominio.enums import ClassificacaoRisco as Cor
from triagem.dominio.excecoes import (
    FilaVaziaError,
    PacienteInvalidoError,
    PacienteNaoEncontradoError,
)
from triagem.dominio.paciente import Paciente
from triagem.fila.fila_prioridade import FilaPrioridade
from triagem.fila.politicas import PoliticaAging, PoliticaSemAging

INICIO = datetime(2026, 11, 24, 8, 0)


def depois(minutos: float) -> datetime:
    """Instante `minutos` após o início."""
    return INICIO + timedelta(minutes=minutos)


def paciente(id: int, cor: Cor, chegada_min: float = 0) -> Paciente:
    """Paciente de teste chegando `chegada_min` minutos após o início."""
    return Paciente(id, f"P{id}", 40, "teste", cor, depois(chegada_min))


@pytest.fixture
def fila() -> FilaPrioridade:
    return FilaPrioridade(PoliticaSemAging())


class TestFilaBasica:
    def test_fila_vazia(self, fila: FilaPrioridade) -> None:
        with pytest.raises(FilaVaziaError):
            fila.proximo(INICIO)
        with pytest.raises(FilaVaziaError):
            fila.retirar_proximo(INICIO)

    def test_prioridade_vence_ordem_de_chegada(self, fila: FilaPrioridade) -> None:
        fila.inserir(paciente(1, Cor.VERDE, 0))
        fila.inserir(paciente(2, Cor.VERMELHO, 5))
        assert fila.retirar_proximo(depois(10)).id == 2
        assert fila.retirar_proximo(depois(10)).id == 1

    def test_fifo_na_mesma_cor(self, fila: FilaPrioridade) -> None:
        fila.inserir(paciente(1, Cor.AMARELO, 0))
        fila.inserir(paciente(2, Cor.AMARELO, 3))
        assert [fila.retirar_proximo(depois(5)).id for _ in range(2)] == [1, 2]

    def test_desempate_por_id_com_mesma_chegada(self) -> None:
        # Com aging, aos 720 min Azul e Verde estão ambos no piso (nível 2) e
        # chegaram juntos: decide o menor id.
        fila = FilaPrioridade(PoliticaAging())
        fila.inserir(paciente(2, Cor.VERDE, 0))
        fila.inserir(paciente(1, Cor.AZUL, 0))
        assert fila.proximo(depois(720)).id == 1

    def test_proximo_nao_retira(self, fila: FilaPrioridade) -> None:
        fila.inserir(paciente(1, Cor.AZUL))
        fila.proximo(INICIO)
        assert fila.tamanho() == 1
        assert len(fila) == 1

    def test_remover_existente(self, fila: FilaPrioridade) -> None:
        fila.inserir(paciente(1, Cor.AZUL))
        fila.inserir(paciente(2, Cor.VERDE))
        assert fila.remover(1).id == 1
        assert [p.id for p in fila.aguardando()] == [2]

    def test_remover_inexistente(self, fila: FilaPrioridade) -> None:
        with pytest.raises(PacienteNaoEncontradoError):
            fila.remover(99)

    def test_id_repetido(self, fila: FilaPrioridade) -> None:
        fila.inserir(paciente(1, Cor.AZUL))
        with pytest.raises(PacienteInvalidoError):
            fila.inserir(paciente(1, Cor.VERDE))

    def test_id_pode_voltar_depois_de_atendido(self, fila: FilaPrioridade) -> None:
        fila.inserir(paciente(1, Cor.AZUL))
        fila.retirar_proximo(INICIO)
        fila.inserir(paciente(1, Cor.AZUL, 10))
        assert len(fila) == 1

    def test_chegada_fora_de_ordem_na_mesma_cor(self, fila: FilaPrioridade) -> None:
        fila.inserir(paciente(1, Cor.AZUL, 10))
        with pytest.raises(PacienteInvalidoError):
            fila.inserir(paciente(2, Cor.AZUL, 5))

    def test_contagem_e_listagem(self, fila: FilaPrioridade) -> None:
        fila.inserir(paciente(1, Cor.AZUL, 0))
        fila.inserir(paciente(2, Cor.AMARELO, 1))
        fila.inserir(paciente(3, Cor.AMARELO, 2))
        fila.inserir(paciente(4, Cor.VERMELHO, 3))
        contagem = fila.contagem_por_cor()
        assert len(contagem) == 5
        assert contagem[Cor.AMARELO] == 2
        assert contagem[Cor.LARANJA] == 0
        ids = [p.id for p in fila.listar_ordenada(depois(5))]
        assert ids == [4, 2, 3, 1]

    def test_aguardando_devolve_copia(self, fila: FilaPrioridade) -> None:
        fila.inserir(paciente(1, Cor.AZUL))
        fila.aguardando().clear()
        assert len(fila) == 1


class TestPoliticaAging:
    @pytest.mark.parametrize(
        ("espera", "esperado"), [(239, 5), (240, 4), (720, 2), (2000, 2)]
    )
    def test_azul(self, espera: int, esperado: int) -> None:
        assert PoliticaAging().nivel_efetivo(paciente(1, Cor.AZUL), depois(espera)) == (
            esperado
        )

    def test_vermelho_sempre_1(self) -> None:
        p = paciente(1, Cor.VERMELHO)
        assert PoliticaAging().nivel_efetivo(p, depois(10_000)) == 1

    def test_laranja_nunca_abaixo_de_2(self) -> None:
        p = paciente(1, Cor.LARANJA)
        assert PoliticaAging().nivel_efetivo(p, depois(10_000)) == 2

    def test_parametros_invalidos(self) -> None:
        with pytest.raises(ValueError):
            PoliticaAging(fator=0)
        with pytest.raises(ValueError):
            PoliticaAging(piso=6)

    def test_instante_de_promocao(self) -> None:
        politica = PoliticaAging()
        p = paciente(1, Cor.AZUL)
        assert politica.instante_de_promocao(p, 4) == depois(240)
        assert politica.instante_de_promocao(p, 2) == depois(720)
        assert politica.instante_de_promocao(p, 1) is None  # abaixo do piso
        assert politica.instante_de_promocao(p, 5) is None  # já está nele
        assert PoliticaSemAging().instante_de_promocao(p, 4) is None


def test_polimorfismo_mesma_fila_ordens_diferentes() -> None:
    agora = depois(300)
    ordens = []
    for politica in (PoliticaSemAging(), PoliticaAging()):
        fila = FilaPrioridade(politica)
        fila.inserir(paciente(1, Cor.AMARELO, 0))  # com aging, aos 300 min: nível 2
        fila.inserir(paciente(2, Cor.LARANJA, 290))
        ordens.append([p.id for p in fila.listar_ordenada(agora)])
    assert ordens == [[2, 1], [1, 2]]
