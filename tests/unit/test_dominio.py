"""Testes do domínio: cores, paciente e relógio."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from triagem.dominio.enums import ClassificacaoRisco
from triagem.dominio.excecoes import PacienteInvalidoError
from triagem.dominio.paciente import Paciente
from triagem.dominio.relogio import RelogioSimulado

INICIO = datetime(2026, 11, 24, 8, 0)


def criar_paciente(**alteracoes: object) -> Paciente:
    """Paciente Azul válido; `alteracoes` sobrescreve campos."""
    dados: dict[str, object] = {
        "id": 1,
        "nome": "Ana",
        "idade": 30,
        "queixa": "dor de cabeça",
        "classificacao": ClassificacaoRisco.AZUL,
        "chegada": INICIO,
    }
    dados.update(alteracoes)
    return Paciente(**dados)  # type: ignore[arg-type]


def depois(minutos: float) -> datetime:
    """Instante `minutos` após o início."""
    return INICIO + timedelta(minutes=minutos)


class TestClassificacaoRisco:
    def test_from_cor_aceita_minusculas_e_espacos(self) -> None:
        assert ClassificacaoRisco.from_cor("azul") is ClassificacaoRisco.AZUL
        assert ClassificacaoRisco.from_cor(" Laranja ") is ClassificacaoRisco.LARANJA

    def test_from_cor_invalida(self) -> None:
        with pytest.raises(ValueError):
            ClassificacaoRisco.from_cor("roxo")

    def test_from_nivel(self) -> None:
        assert ClassificacaoRisco.from_nivel(1) is ClassificacaoRisco.VERMELHO
        with pytest.raises(ValueError):
            ClassificacaoRisco.from_nivel(9)

    def test_sla_minutos(self) -> None:
        assert ClassificacaoRisco.AZUL.sla_minutos == 240
        assert ClassificacaoRisco.VERMELHO.sla_minutos == 0

    def test_nivel_e_cor(self) -> None:
        assert ClassificacaoRisco.VERDE.nivel == 4
        assert ClassificacaoRisco.VERDE.cor == "Verde"


class TestPaciente:
    def test_nome_vazio_invalido(self) -> None:
        with pytest.raises(PacienteInvalidoError):
            criar_paciente(nome="   ")

    def test_idade_negativa_invalida(self) -> None:
        with pytest.raises(PacienteInvalidoError):
            criar_paciente(idade=-1)

    def test_classificacao_precisa_ser_enum(self) -> None:
        with pytest.raises(PacienteInvalidoError):
            criar_paciente(classificacao="Azul")

    def test_tempo_espera(self) -> None:
        assert criar_paciente().tempo_espera(depois(90)) == 90.0

    def test_tempo_espera_nunca_negativo(self) -> None:
        assert criar_paciente().tempo_espera(depois(-10)) == 0.0

    def test_limite_sla(self) -> None:
        assert criar_paciente().limite_sla() == depois(240)

    def test_sla_estourado_na_fronteira(self) -> None:
        p = criar_paciente()
        assert p.sla_estourado(depois(240)) is False
        assert p.sla_estourado(depois(241)) is True

    def test_repr(self) -> None:
        assert repr(criar_paciente(id=3)) == "Paciente(id=3, nome='Ana', cor=Azul)"


class TestRelogioSimulado:
    def test_avancar(self) -> None:
        relogio = RelogioSimulado(INICIO)
        relogio.avancar(30)
        assert relogio.agora() == depois(30)

    def test_avancar_negativo(self) -> None:
        with pytest.raises(ValueError):
            RelogioSimulado(INICIO).avancar(-1)
