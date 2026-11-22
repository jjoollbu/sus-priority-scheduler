# Interface Streamlit — tela do plantão

> **Status: v1.0, alinhada a `app/main.py` (22/11/2026).** Substitui o wireframe v0.1, que previa 5 páginas; a implementação reúne tudo numa página só, "Triagem — Plantão". Esboço de conteúdo e disposição, sem estética; os números são apenas exemplos.

Executar: `streamlit run app/main.py`.

A tela só exibe e dispara ações. A ordem de chamada vem da `FilaPrioridade`, o fluxo de chegadas e atendimentos vem do `SimuladorPlantao`, e o histórico é lido do banco (`dados/triagem.db`).

## 1. Barra lateral

```text
┌─ Parâmetros do plantão ──────────────────────┐
│ Chegadas por hora (demanda)  [====o----] 15  │
│ Médicos atendendo            [==o------]  2  │
│ Semente do sorteio           [ 42 ]          │
│ Cada consulta dura um tempo sorteado entre   │
│ 5 e 15 min (média 10 min).                   │
│ ⚠️ Demanda 15/h × capacidade média 12/h      │
│    (2 médicos, consulta média de 10 min) —   │
│    125% de ocupação: plantão sobrecarregado. │
├─ Regra da fila ──────────────────────────────┤
│ Usar aging (anti-starvation)      [ ○ ]      │
│ Chegadas automáticas              [ ● ]      │
│ [ Reiniciar plantão ]                        │
│ [ Carregar cenário de starvation ]           │
│ O cenário coloca 1 Azul e 6 Laranjas na fila.│
│ Regra atual: sem aging                       │
└──────────────────────────────────────────────┘
```

- Mudar a chave de aging ou qualquer parâmetro **reinicia** o plantão e cria uma linha nova na tabela `plantao`.
- A ocupação aparece em verde (✅ a equipe dá conta) ou amarelo (⚠️ sobrecarregado).

Componentes: `st.slider`, `st.number_input`, `st.toggle`, `st.button`, `st.success` / `st.warning`.

## 2. Corpo da página

### 2.1 Cabeçalho e relógio

```text
Triagem — Plantão
Os pacientes chegam sozinhos e os médicos chamam sempre o mais grave. [...]
Depois ligue o aging na barra lateral e compare.

┌─────────────────┬──────────────────┬──────────────────────┐
│ Hora simulada   │ Pacientes na fila│ Pacientes atendidos  │
│ 24/11 14:00     │       31         │        66            │
└─────────────────┴──────────────────┴──────────────────────┘
Avançar o relógio
[ +10 min ]  [ +1 hora ]  [ +4 horas ]  [ +12 horas ]
```

Componentes: `st.title`, `st.metric`, `st.columns`, `st.button` + `st.rerun`.

### 2.2 Quem está esperando

```text
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│🔴Vermelho│🟠 Laranja│🟡 Amarelo│🟢 Verde  │🔵 Azul   │
│    0     │    1     │    6     │   15     │    9     │
│ na fila  │ na fila ·│ na fila ·│ na fila ·│ na fila ·│
│          │ mais     │ mais     │ mais     │ mais     │
│          │ antigo há│ antigo há│ antigo há│ antigo há│
│          │ 4 min    │ 22 min   │ 2h10     │ 5h40     │
│          │          │          │⚠️ Prazo  │⚠️ Prazo  │
│          │          │          │estourado │estourado │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

Componentes: `st.columns(5)`, `st.container(border=True)`, `st.metric`.

### 2.3 Fila de atendimento — ordem de chamada

```text
Próximo a ser chamado: Lucas (🟠 Laranja), esperando há 4 min.

┌──────┬──────────────┬───────────┬────────────────┬────────┬──────────────────────┬────────────┬──────────┐
│Ordem │ Paciente     │Classific. │Prioridade atual│ Espera │ Situação             │Prazo usado │Chegou às │
├──────┼──────────────┼───────────┼────────────────┼────────┼──────────────────────┼────────────┼──────────┤
│ 1    │ Lucas (nº 58)│🟠 Laranja │ 2              │ 4 min  │✅ No prazo (faltam 6)│ ████░  40% │ 13:56    │
│ 2    │ Ana (nº 21)  │🔵 Azul    │ ⬆️ 3 (era 5)   │ 8h05   │⚠️ Atrasado há 4h05   │ █████ 202% │ 05:55    │ ← fundo amarelo
│ 3    │ Yara (nº 49) │🟡 Amarelo │ 3              │ 22 min │✅ No prazo (faltam 38)│ ██░░░  37% │ 13:38    │
└──────┴──────────────┴───────────┴────────────────┴────────┴──────────────────────┴────────────┴──────────┘
Linhas com fundo amarelo e ⬆️ na coluna Prioridade atual: pacientes promovidos pelo aging.
```

- Fila vazia: `st.info("Ninguém aguardando. Avance o relógio para chegarem pacientes.")`.
- "Prazo usado" = espera ÷ SLA da cor; acima de 100% o prazo estourou.

Componentes: `st.dataframe` com `Styler` (destaque das linhas promovidas) e `column_config` (`ProgressColumn`).

### 2.4 Gráfico de espera

```text
Há quanto tempo o paciente mais antigo de cada cor espera
 horas │                                   ╱ Azul
       │                         ╱────────╱
       │               ╱────────╱      ___ Verde
       │     ╱────────╱   ____────────
       │____╱____────────────────────────── Amarelo / Laranja / Vermelho
       └──────────────────────────────────── hora do plantão
Uma linha que sobe sem parar indica um paciente que nunca é chamado (starvation).
▸ Ver os dados do gráfico em tabela
```

- Uma "foto" da fila a cada 10 min simulados (`Amostra`).
- Cores das linhas com contraste ≥ 3:1 nos temas claro e escuro; tabela alternativa no expansor para leitor de tela.

Componentes: `st.line_chart`, `st.expander`, `st.dataframe`.

### 2.5 Últimos acontecimentos e atendidos

```text
Últimos acontecimentos
┌─────────────┬──────────────────────┬───────────────┬──────────┬──────┬──────────────────────────────┬──────────┐
│ Instante    │ Evento               │ Paciente      │ Classif. │Nível │ Detalhes                     │ Fila após│
├─────────────┼──────────────────────┼───────────────┼──────────┼──────┼──────────────────────────────┼──────────┤
│ 24/11 14:00 │ 🩺 Atendimento       │ Lucas (nº 57) │🟠 Laranja│ 2    │ médico 1; espera 3 min; ...  │ 31       │
│ 24/11 13:55 │ ⬆️ Promoção (aging)  │ Ana (nº 21)   │🔵 Azul   │ 3    │ espera 480 min; nível 4 -> 3 │ 32       │
│ 24/11 13:50 │ ⚠️ Prazo estourado   │ Ivo (nº 40)   │🟢 Verde  │ 4    │ SLA 120 min                  │ 32       │
└─────────────┴──────────────────────┴───────────────┴──────────┴──────┴──────────────────────────────┴──────────┘
Lido do banco de dados (tabela evento_fila), do mais novo ao mais antigo.

▸ Todos os atendidos (66)
  Início · Médico · Paciente · Classificação · Prioridade no atendimento · Espera · Consulta · Situação
```

Componentes: `st.dataframe`, `st.expander`.

### 2.6 Banco de dados e auditoria

```text
Banco de dados e auditoria
Tudo é gravado em dados/triagem.db (SQLite). O histórico é append-only. Este é o plantão nº 3.

Plantões gravados
┌────────┬──────────────┬───────────┬────────┬───────────────┬──────────┬──────────┬─────────┐
│Plantão │ Regra da fila│Chegadas/h │Médicos │Consulta (min) │Pacientes │Atendidos │ Eventos │
│ 3      │ com aging    │ 15        │ 2      │ 5–15          │ 97       │ 66       │ 312     │
│ 2      │ sem aging    │ 15        │ 2      │ 5–15          │ 97       │ 70       │ 280     │
└────────┴──────────────┴───────────┴────────┴───────────────┴──────────┴──────────┴─────────┘
Plantão [ nº 3 ▾ ]   Buscar paciente por número ou nome [ ex.: 7 ou Gabriela ]

Ana (nº 21) — 🔵 Azul, chegou às 05:55
[trilha de eventos do paciente: Entrada → Promoção → Prazo estourado → ... ]

[ Exportar logs.sql do plantão nº 3 ]  → download de logs_plantao_3.sql
```

Componentes: `st.dataframe`, `st.selectbox`, `st.text_input`, `st.download_button`.

## 3. Acessibilidade

- A cor nunca aparece sozinha: o símbolo (🔴🟠🟡🟢🔵) vem sempre com o nome.
- Destaque das linhas promovidas: texto escuro sobre amarelo-claro (contraste 9,9:1).
- Valores dos sliders repetidos em texto de alto contraste na mensagem de ocupação.
- Gráfico com alternativa em tabela; rótulos de métrica ocultos na tela, mas lidos por leitor de tela.
- Idioma da página declarado como português.

## 4. Exigências cobertas

| Exigência | Onde aparece |
|---|---|
| Monitoramento em tempo real | Relógio, "Quem está esperando", fila e gráfico, atualizados a cada avanço do relógio |
| Inserção de dados | Chegadas sorteadas pelo plantão e cenário de starvation (cadastro manual: pendente) |
| Tratamento contra starvation | Chave "Usar aging" + "Carregar cenário de starvation"; linhas promovidas destacadas |
| Respeito a SLAs | Colunas "Situação" e "Prazo usado"; aviso "Prazo estourado" por cor; eventos `ATRASO_SLA` |
| Teste de estresse | Sliders de demanda e médicos; avanço de até 12 h por clique |
| Histórico e geração do SQL | "Últimos acontecimentos", "Todos os atendidos" e "Banco de dados e auditoria" com exportação do `logs.sql` |

## 5. Mudanças em relação ao wireframe v0.1

| Wireframe v0.1 | Tela atual |
|---|---|
| 5 páginas (`app/pages/`) | Uma página com 6 seções |
| Modo automático com avanço por ciclo | Botões de avanço (+10 min a +12 h); chegadas automáticas ligáveis |
| Formulário de novo paciente e botão "Atender próximo" | Chegadas sorteadas e médicos que chamam sozinhos |
| Remoção por ID e motivo | Pendente |
| Página Fairness com "sem aging" e "com aging" lado a lado | Mesma tela; a comparação é feita alternando a chave de aging (cada execução vira um plantão gravado, comparável na tabela de plantões) |
