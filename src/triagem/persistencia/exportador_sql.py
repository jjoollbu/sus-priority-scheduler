"""Gera o logs.sql: um script que recria o histórico num banco vazio.

Ordem (como pedem as regras de negócio): catálogo de cores, plantões,
pacientes, eventos e atendimentos, tudo dentro de uma transação. O script
executa em um banco recém-criado por sql/schema.sql.
"""

from __future__ import annotations

import sqlite3

# (tabela, colunas, ordenação) na ordem em que precisam ser inseridas.
TABELAS: list[tuple[str, tuple[str, ...], str]] = [
    ("classificacao", ("nivel", "cor", "sla_minutos"), "nivel"),
    (
        "plantao",
        (
            "id",
            "inicio",
            "politica",
            "chegadas_por_hora",
            "medicos",
            "duracao_consulta_min",
            "semente",
        ),
        "id",
    ),
    (
        "paciente",
        ("plantao_id", "id", "nome", "idade", "queixa", "nivel", "chegada"),
        "plantao_id, id",
    ),
    (
        "evento_fila",
        (
            "id",
            "plantao_id",
            "paciente_id",
            "tipo",
            "instante",
            "nivel_efetivo",
            "detalhes",
            "qtd_vermelho",
            "qtd_laranja",
            "qtd_amarelo",
            "qtd_verde",
            "qtd_azul",
            "total",
        ),
        "id",
    ),
    (
        "atendimento",
        (
            "plantao_id",
            "paciente_id",
            "inicio",
            "espera_min",
            "nivel_efetivo",
            "dentro_do_sla",
            "medico",
        ),
        "plantao_id, inicio, paciente_id",
    ),
]


def literal_sql(valor: object) -> str:
    """Converte um valor Python em literal SQL (texto entre aspas, NULL...)."""
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, int | float):
        return repr(valor)
    texto = str(valor).replace("'", "''")  # aspas simples são dobradas no SQL
    return f"'{texto}'"


def exportar_logs(conexao: sqlite3.Connection, plantao_id: int | None = None) -> str:
    """Devolve o texto do logs.sql (de um plantão ou de todos)."""
    linhas = [
        "-- logs.sql gerado pela aplicação de triagem.",
        "-- Execute em um banco vazio criado por sql/schema.sql.",
        "BEGIN TRANSACTION;",
    ]
    for tabela, colunas, ordem in TABELAS:
        sql = f"SELECT {', '.join(colunas)} FROM {tabela}"  # noqa: S608 (nomes fixos)
        parametros: tuple[object, ...] = ()
        if plantao_id is not None and tabela != "classificacao":
            filtro = "id" if tabela == "plantao" else "plantao_id"
            sql += f" WHERE {filtro} = ?"
            parametros = (plantao_id,)
        sql += f" ORDER BY {ordem}"
        registros = conexao.execute(sql, parametros).fetchall()
        linhas.append(f"\n-- {tabela}: {len(registros)} linha(s)")
        for registro in registros:
            valores = ", ".join(literal_sql(v) for v in registro)
            linhas.append(
                f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({valores});"
            )
    linhas.append("\nCOMMIT;")
    return "\n".join(linhas) + "\n"
