# Projeto A3 — Simulador de Filas de Prioridade

Simulador acadêmico de filas de prioridade baseado em um cenário de triagem
hospitalar inspirado no SUS. Pacientes fictícios de 5
cores chegam a um plantão, médicos chamam sempre o mais urgente e uma política
de **aging** impede que os de prioridade baixa esperem para sempre
(*starvation*). Toda mudança na fila é gravada numa trilha de auditoria SQL.

> Cores, tempos e parâmetros são acadêmicos e configuráveis em
> `src/triagem/config.py`. Só são usados dados fictícios.

## Tecnologias

- Python 3.12+ com Programação Orientada a Objetos
- Streamlit (interface) e pandas (tabelas e gráficos)
- SQLite (banco de auditoria)
- pytest e ruff (testes, lint e formatação)
- Git e GitHub (GitHub Flow com Pull Requests)

## Como executar

```bash
# 1. Ambiente virtual (opcional, recomendado)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Instala o pacote e as ferramentas de desenvolvimento
pip install -e ".[dev]"

# 3. Abre a tela do plantão
streamlit run app/main.py

# 4. Testes e qualidade
pytest
ruff check .
ruff format --check .

# 5. Demonstração em terminal dos cenários T1 (sem aging) e T2 (com aging)
python script/demo_starvatio.py
```

O banco é criado automaticamente em `dados/triagem.db` (fora do Git). O
`logs.sql` de cada plantão pode ser baixado na seção *Banco de dados e
auditoria* da tela e executado num banco vazio criado por `sql/schema.sql`.

## Como usar a tela

1. Na barra lateral, ajuste chegadas por hora, número de médicos e semente.
2. Avance o relógio (+10 min, +1 h, +4 h, +12 h) e observe a fila, a coluna
   **Situação** e o gráfico de espera.
3. Ligue **Usar aging** e compare: pacientes promovidos aparecem com ⬆️ e fundo
   amarelo.
4. **Carregar cenário de starvation** coloca 1 Azul e 6 Laranjas na fila;
   desligue as chegadas automáticas para ver o caso isolado.

## Estrutura

```text
app/main.py              tela Streamlit do plantão
docs/                    regras de negócio, arquitetura/UML, wireframe, boas práticas
script/demo_starvatio.py demo de terminal T1/T2
sql/schema.sql           estrutura do banco (somente DDL)
src/triagem/
  config.py              SLAs, K, piso, duração da consulta, caminhos
  dominio/               Paciente, Atendimento, EventoFila, enums, relógios, exceções
  fila/                  FilaPrioridade, políticas, cenário de starvation, simulador
  persistencia/          conexão, repositório SQLite, exportador do logs.sql
tests/                   unit, integration e cenarios (T1–T4)
```

## Documentação

- [Regras de negócio](docs/regras_de_negocio.md)
- [Arquitetura e UML](docs/arquitetura_e_uml.md)
- [Interface](docs/wireframe.md)
- [Boas práticas de desenvolvimento](docs/BOAS_PRATICAS.md)

## Status

Núcleo, simulador, persistência e tela implementados; 84 testes passando.
Entrega final: 24/11/2026.
