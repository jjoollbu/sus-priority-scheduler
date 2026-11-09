# Wireframe da interface Streamlit

> **Status: wireframe v0.1 para o Marco 1.** Esboço de conteúdo e disposição, sem estética. Cada página chama apenas serviços de aplicação; nenhuma ordena a fila nem acessa o banco direto.

Navegação: menu lateral do Streamlit com as 5 páginas (`app/pages/`). Em todas as páginas, a barra lateral mostra o **relógio simulado** e os controles de tempo.

```text
┌─ Barra lateral (todas as páginas) ─┐
│ Relógio simulado: 24/11 08:40      │
│ [ +10 min ]  [ +1 h ]              │
│ Modo automático   [■ ligado]       │
│ Avanço por ciclo  [===o---] 10 min │
│ Política: Aging (K=1, piso=2)      │
└────────────────────────────────────┘
```

## 1. Dashboard

Objetivo: visão geral da fila em tempo real. Atualiza sozinho no modo automático (`st.fragment(run_every=...)`).

```text
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Aguardando   │ Em atraso    │ SLA cumprido │ Espera média │
│     12       │   3 ⚠        │    81 %      │   34 min     │
└──────────────┴──────────────┴──────────────┴──────────────┘
┌─ Pacientes aguardando por cor ─────┐ ┌─ % SLA cumprido por cor ───────────┐
│ Vermelho ▌ 0                       │ │ Vermelho ████████████ 100 %        │
│ Laranja  ██████ 5                  │ │ Laranja  ████████░░░░  70 %        │
│ Amarelo  ████ 3                    │ │ Amarelo  ██████████░░  85 %        │
│ Verde    ██ 2                      │ │ Verde    ███████████░  95 %        │
│ Azul     ██ 2                      │ │ Azul     ████████████ 100 %        │
└────────────────────────────────────┘ └────────────────────────────────────┘
```

Componentes: `st.metric`, `st.columns`, `st.bar_chart`.

## 2. Fila e Atendimento

Objetivo: cadastrar, atender e remover pacientes; ver a fila na ordem de atendimento.

```text
┌─ Novo paciente ───────────────────────────────────────────────┐
│ Nome [________________]  Idade [__]  Queixa [_______________] │
│ Classificação [ Amarelo ▾ ]                    [ Registrar ]  │
└───────────────────────────────────────────────────────────────┘
[ Atender próximo ]

Fila — ordem de atendimento atual
┌───┬────┬──────────────┬──────────┬────────────────┬────────┬──────────┐
│ # │ ID │ Nome         │ Cor orig.│ Nível efetivo  │ Espera │ SLA      │
├───┼────┼──────────────┼──────────┼────────────────┼────────┼──────────┤
│ 1 │ 7  │ Paciente 07  │ Laranja  │ 2              │ 12 min │ ⚠ atraso │
│ 2 │ 3  │ Paciente 03  │ Azul     │ 2 (promovido)  │ 730 min│ ⚠ atraso │
│ 3 │ 9  │ Paciente 09  │ Amarelo  │ 3              │ 20 min │ ok       │
└───┴────┴──────────────┴──────────┴────────────────┴────────┴──────────┘
Remover paciente: ID [__]  Motivo [ Desistência ▾ ]  [ Remover ]
```

Componentes: `st.form`, `st.selectbox`, `st.dataframe` (com `column_config`), `st.button`, `st.toast`, `st.error`.
Mensagens: fila vazia → `st.error("Não há pacientes aguardando.")`; atendimento → `st.toast` com nome, espera e SLA.

## 3. Fairness

Objetivo: mostrar o problema (starvation) e a solução (aging) lado a lado, com o mesmo cenário e a mesma semente, em simulações isoladas (não usa a fila real).

```text
Cenário [ Rajada de Laranjas ▾ ]  Semente [42]  Duração [16 h]  [ Comparar ]

┌─ Sem aging ──────────────────────┐ ┌─ Com aging (K=1, piso=2) ─────────┐
│ Azul atendido?  NÃO (starvation) │ │ Azul atendido?  SIM, aos 720 min   │
│ Espera máx. Azul: > 960 min      │ │ Espera máx. Azul: 720 min          │
│                                  │ │                                    │
│ [gráfico: espera do Azul × tempo]│ │ [gráfico: nível efetivo × tempo]   │
└──────────────────────────────────┘ └────────────────────────────────────┘
Promoções registradas: 12:00 5→4 · 16:00 4→3 · 20:00 3→2
```

Componentes: `st.columns`, `st.line_chart`, `st.table`.

## 4. Cenários de estresse

Objetivo: gerar muitas chegadas de forma reproduzível e observar as métricas.

```text
Cenário [ Horário de pico ▾ ]
Chegadas por hora [====o----] 40     Atendimentos por hora [===o-----] 30
Semente [42]     Duração [8 h]                          [ Executar ]
[████████████░░░░░░░░] 60 %

Resultado: 320 chegadas · 240 atendidos · 80 aguardando
SLA cumprido por cor: Vermelho 100 % · Laranja 62 % · Amarelo 70 % · ...
```

Componentes: `st.selectbox`, `st.slider`, `st.number_input`, `st.progress`, `st.metric`.

## 5. Histórico e Auditoria

Objetivo: rastrear qualquer paciente e exportar o `logs.sql`.

```text
Buscar paciente por ID ou nome [__________]

Eventos
┌─────────┬────────────────┬───────┬──────────────────────────┬──────────┐
│ Instante│ Evento         │ Nível │ Detalhes                 │ Fila após│
├─────────┼────────────────┼───────┼──────────────────────────┼──────────┤
│ 08:00   │ ENTRADA        │ 5     │ cor=AZUL                 │ 1        │
│ 12:00   │ PROMOCAO_AGING │ 4     │ espera=240min            │ 1        │
│ 12:00   │ ATRASO_SLA     │ 4     │ sla=240min               │ 1        │
│ 20:00   │ ATENDIMENTO    │ 2     │ espera=720min;descumprido│ 0        │
└─────────┴────────────────┴───────┴──────────────────────────┴──────────┘
Atendimentos realizados: [tabela]
[ Exportar logs.sql ]  → download do arquivo
```

Componentes: `st.text_input`, `st.dataframe`, `st.download_button`.

## Itens do planejamento cobertos

| Exigência | Onde aparece |
|---|---|
| Monitoramento em tempo real | Barra lateral (modo automático) + Dashboard |
| Inserção de dados | Fila e Atendimento |
| Tratamento contra starvation | Fairness |
| Respeito a SLAs | Dashboard (% por cor), coluna SLA da fila |
| Teste de estresse | Cenários de estresse |
| Histórico e geração do SQL | Histórico e Auditoria |
