"""Cenários T1 (starvation sem aging) e T2 (aging resolve a starvation)."""

from __future__ import annotations

from datetime import datetime

from triagem.dominio.relogio import RelogioSimulado
from triagem.fila.cenario_starvation import (
    INICIO,
    montar_fila_inicial,
    simular_starvation,
)
from triagem.fila.politicas import PoliticaAging, PoliticaSemAging


def hora(h: int) -> datetime:
    """Instante às `h`:00 do dia do cenário."""
    return datetime(2026, 11, 24, h, 0)


def test_t1_sem_aging_gera_starvation() -> None:
    resultado = simular_starvation(PoliticaSemAging(), horas=16)
    assert resultado.atendido is False
    assert resultado.tamanho_fila_final == 33
    assert resultado.promocoes == []


def test_t2_com_aging_atende_o_azul() -> None:
    resultado = simular_starvation(PoliticaAging(), horas=16)
    assert resultado.atendido is True
    assert resultado.instante == hora(20)
    assert resultado.espera_min == 720
    assert resultado.nivel_no_atendimento == 2
    assert resultado.promocoes == [(hora(12), 5, 4), (hora(16), 4, 3), (hora(20), 3, 2)]


def test_montar_fila_inicial() -> None:
    relogio = RelogioSimulado(INICIO)
    fila = montar_fila_inicial(PoliticaAging(), relogio, qtd_laranjas=6)
    assert len(fila) == 7
    assert relogio.agora() >= max(p.chegada for p in fila.aguardando())
