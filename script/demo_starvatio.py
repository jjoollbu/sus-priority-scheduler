"""Demonstração em terminal dos cenários T1 (sem aging) e T2 (com aging).

Uso: python scripts/demo_starvation.py [--horas 16]
"""

from __future__ import annotations

import argparse

from triagem.config import FATOR_AGING, PISO_AGING
from triagem.dominio.enums import ClassificacaoRisco
from triagem.fila.cenario_starvation import ResultadoCenario, simular_starvation
from triagem.fila.politicas import PoliticaAging, PoliticaSemAging


def imprimir(titulo: str, resultado: ResultadoCenario, horas: int) -> None:
    """Mostra as promoções e o desfecho do Azul em um cenário."""
    print(f"=== {titulo} ===")
    for instante, de, para in resultado.promocoes:
        print(f"{instante:%H:%M}  Azul promovido: nível {de} -> {para}")
    if resultado.atendido and resultado.instante is not None:
        print(
            f"{resultado.instante:%H:%M}  >>> Azul ATENDIDO com nível efetivo "
            f"{resultado.nivel_no_atendimento}, após {resultado.espera_min:.0f} min "
            "de espera"
        )
    else:
        print(
            f">>> Azul NUNCA foi atendido em {horas} h: STARVATION. "
            f"Fila com {resultado.tamanho_fila_final} pacientes."
        )


def main() -> None:
    """Lê os argumentos e roda T1 e T2."""
    parser = argparse.ArgumentParser(description="Demonstração de starvation")
    parser.add_argument("--horas", type=int, default=16, help="duração simulada")
    args = parser.parse_args()

    t1 = simular_starvation(PoliticaSemAging(), args.horas)
    imprimir("T1: prioridade estrita (sem aging)", t1, args.horas)
    print()

    piso = ClassificacaoRisco.from_nivel(PISO_AGING).cor
    t2 = simular_starvation(PoliticaAging(), args.horas)
    imprimir(f"T2: com aging (K = {FATOR_AGING:g}, piso = {piso})", t2, args.horas)


if __name__ == "__main__":
    main()