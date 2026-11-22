"""Parâmetros configuráveis da triagem (SLA por cor, aging e banco de dados)."""

from __future__ import annotations

from pathlib import Path

# Nível de risco (1 = Vermelho ... 5 = Azul) -> tempo-alvo de atendimento em minutos.
SLA_MINUTOS: dict[int, int] = {1: 0, 2: 10, 3: 60, 4: 120, 5: 240}

# K: o paciente sobe 1 nível a cada K x SLA (da cor original) de espera.
FATOR_AGING: float = 1.0

# Nível mínimo que o aging pode atingir (2 = Laranja): nunca vira Vermelho.
PISO_AGING: int = 2

# Duração de cada consulta: sorteada (inteira, uniforme) entre estes limites, em
# minutos. Não é escolhida na tela; média de 10 min.
CONSULTA_MIN_MINUTOS: int = 5
CONSULTA_MAX_MINUTOS: int = 15

# Banco de dados (SQLite). Caminhos a partir da raiz do repositório.
RAIZ_PROJETO = Path(__file__).resolve().parents[2]
CAMINHO_SCHEMA = RAIZ_PROJETO / "sql" / "schema.sql"
CAMINHO_BANCO = RAIZ_PROJETO / "dados" / "triagem.db"
