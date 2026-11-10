"""Abertura do banco SQLite a partir de sql/schema.sql."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from triagem.config import CAMINHO_SCHEMA
from triagem.dominio.enums import ClassificacaoRisco

EM_MEMORIA = ":memory:"


def abrir_conexao(caminho: str | Path = EM_MEMORIA) -> sqlite3.Connection:
    """Abre (ou cria) o banco, aplica o schema e preenche o catálogo de cores.

    `:memory:` cria um banco temporário, usado nos testes.
    """
    if caminho != EM_MEMORIA:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: o Streamlit pode usar a conexão em outra thread.
    conexao = sqlite3.connect(caminho, check_same_thread=False)
    conexao.row_factory = sqlite3.Row  # linhas acessíveis por nome de coluna
    conexao.execute("PRAGMA foreign_keys = ON")
    if caminho != EM_MEMORIA:
        # WAL + synchronous NORMAL: commits rápidos e seguros para um arquivo local.
        conexao.execute("PRAGMA journal_mode = WAL")
        conexao.execute("PRAGMA synchronous = NORMAL")
    conexao.executescript(CAMINHO_SCHEMA.read_text(encoding="utf-8"))
    preencher_catalogo(conexao)
    return conexao


def preencher_catalogo(conexao: sqlite3.Connection) -> None:
    """Grava as 5 cores e seus SLAs (de config.py) na tabela classificacao."""
    with conexao:
        conexao.executemany(
            "INSERT OR IGNORE INTO classificacao (nivel, cor, sla_minutos) "
            "VALUES (?, ?, ?)",
            [(c.nivel, c.name, c.sla_minutos) for c in ClassificacaoRisco],
        )
