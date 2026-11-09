# Regras de negócio — Simulador de filas de prioridade

> **Status: proposta v0.3 para validação da equipe e do docente.** Este documento traduz o Planejamento Técnico v0.3 em regras testáveis. Os parâmetros numéricos não devem ser tratados como protocolo clínico oficial.

## 1. Objetivo e limites

O sistema simula uma fila de atendimento com prioridades. Ele não realiza avaliação clínica, não recomenda classificação de risco e não substitui o Protocolo de Manchester nem a atuação de profissionais habilitados. A classificação do paciente fictício é informada manualmente pelo operador da simulação.

As cores e os tempos abaixo são parâmetros acadêmicos configuráveis (`config.py`), sujeitos à validação da equipe e do docente.

### 1.1 Fundamentação no SUS

- **Origem:** o Ministério da Saúde criou em 2004 a Política Nacional de Humanização (PNH), que inclui entre seus métodos o Acolhimento com Avaliação e Classificação de Risco (AACR). Depois, o Protocolo de Classificação de Risco de Manchester foi reconhecido e adotado no Brasil.
- **Tempos-alvo:** as 5 cores e os tempos da seção 2 são os do Protocolo de Manchester usados na rede pública — por exemplo, pela Secretaria de Saúde de Minas Gerais: vermelho imediato, laranja 10 min, amarelo 60 min, verde 120 min e azul 240 min.
- **Quem classifica:** no serviço real, a classificação de risco é atividade privativa do enfermeiro (Resolução Cofen nº 661/2021). Por isso, no simulador, a cor é informada pelo operador: o sistema não faz avaliação clínica.
- **Variações locais:** os tempos mudam entre protocolos e municípios (o POP de Classificação de Risco do Rio de Janeiro de 2024, por exemplo, usa 15 min para laranja e 30 min para amarelo; a cartilha da PNH usa 4 cores). Por isso os SLAs ficam em configuração.

**Referências**

- BRASIL. Ministério da Saúde. *HumanizaSUS: Política Nacional de Humanização*. Brasília, 2004.
- CONSELHO FEDERAL DE ENFERMAGEM. *Resolução Cofen nº 661, de 9 de março de 2021*. Disponível em: <https://www.legisweb.com.br/legislacao/?id=410743>.
- MINAS GERAIS. Agência Minas. *Saúde abre inscrições de capacitação sobre o Protocolo de Manchester*. Disponível em: <https://www.agenciaminas.mg.gov.br/noticia/saude-abre-inscricoes-de-capacitacao-sobre-o-protocolo-de-manchester-66964>.
- RIO DE JANEIRO. RioSaúde. *POP — Classificação de Risco*, 2024. Disponível em: <https://riosaude.prefeitura.rio/wp-content/uploads/sites/66/2024/09/POP-Classificacao-de-Risco.pdf>.

## 2. Classificação simulada

| Cor | Nível base | SLA simulado | Regra geral |
|---|---:|---:|---|
| Vermelho — emergência | 1 | 0 min (imediato) | Prioridade máxima; FIFO entre vermelhos; nunca é promovido nem ultrapassado |
| Laranja — muito urgente | 2 | 10 min | Segundo nível; também é o piso do aging |
| Amarelo — urgente | 3 | 60 min | Pode ser promovido até o nível 2 |
| Verde — pouco urgente | 4 | 120 min | Pode ser promovido até o nível 2 |
| Azul — não urgente | 5 | 240 min | Pode ser promovido até o nível 2 |

**Vermelho com SLA de 0 min:** com a regra "atraso se espera > SLA" (seção 8), qualquer avanço do relógio com um Vermelho na fila já é atraso. Isso é intencional (emergência não espera). Para um Vermelho atrasado não esconder o desempenho das outras cores, o dashboard mostra o **% de SLA cumprido por cor**.

**Validação de configuração:** níveis 2 a 5 precisam ter SLA maior que zero; caso contrário o cálculo do aging dividiria por zero. A aplicação recusa iniciar com uma configuração inválida.

**Pendente de confirmação:** os valores de SLA, a escala e a nomenclatura devem ser validados com o docente antes de serem apresentados como definitivos.

## 3. Cadastro e entrada na fila

1. O operador informa os dados do paciente fictício e seleciona uma classificação.
2. O serviço cria o paciente com identificador único e instante de chegada obtido do relógio injetado.
3. O serviço grava o paciente e o evento `ENTRADA` numa única transação.
4. **Somente após o commit**, o paciente é inserido no fim da fila FIFO da sua classificação original.
5. O evento registra o estado da fila logo após a operação (seção 9).

A camada de interface não implementa essas regras: apenas valida campos de apresentação e chama o serviço de aplicação.

## 4. Ordenação e desempate

A ordem de atendimento é determinada pela chave:

`(nível_efetivo, instante_de_chegada, id)`

Critérios, nesta ordem:

1. Menor nível efetivo tem prioridade.
2. Em caso de mesmo nível efetivo, atende primeiro quem chegou antes (FIFO).
3. Persistindo o empate, vence o menor identificador.

O nível efetivo é calculado pela política de fairness no instante consultado. A classificação original do paciente não é alterada.

**Por que basta comparar as 5 cabeças de fila:** dentro de uma mesma cor, o fator K e o SLA são iguais para todos. Quem chegou antes espera mais, logo tem nível efetivo menor ou igual e chegada menor. A cabeça de cada fila sempre vence o resto da sua própria fila.

## 5. Aging e prevenção de starvation

O sistema usa cinco filas FIFO (`collections.deque`), uma por cor, e uma política de aging que promove o nível efetivo conforme o tempo de espera.

Fórmula:

`promocoes = floor(espera_minutos / (K * SLA_da_classificacao_original))`

`nivel_efetivo = max(PISO, nivel_base - promocoes)`

Parâmetros propostos: `K = 1` e `PISO = 2` (Laranja). **Pendente de validação da equipe.**

**Exemplo numérico — Azul (SLA 240, K = 1):**

| Espera | Promoções | Nível efetivo |
|---|---:|---:|
| 0–239 min | 0 | 5 |
| 240–479 min | 1 | 4 |
| 480–719 min | 2 | 3 |
| ≥ 720 min | 3 | 2 (piso) |

O Azul chega ao piso com **3 promoções, em 720 min**. Um Verde (SLA 120) é promovido aos 120 e aos 240 min; um Amarelo (SLA 60), aos 60 min. Laranja e Vermelho nunca são promovidos.

**Desempate no piso (decisão consciente):** ao chegar ao nível 2, o paciente envelhecido disputa com os Laranjas por ordem de chegada. Exemplo: um Amarelo chega às 08:00 e um Laranja às 08:30. Às 09:10, o Amarelo (nível efetivo 2, chegou antes) é chamado primeiro, embora o Laranja já tenha passado do seu SLA de 10 min. A alternativa — desempatar pelo nível original — foi rejeitada: com fluxo contínuo de Laranjas, o paciente envelhecido nunca venceria e a starvation voltaria.

**Garantia:** todo paciente chega ao piso em tempo limitado, no máximo `(nivel_base - PISO) * K * SLA`. Daí em diante, só é ultrapassado por Vermelhos e por quem chegou antes dele ao mesmo nível. A espera é limitada **desde que a chegada de Vermelhos não ocupe toda a capacidade de atendimento**; não se promete espera máxima absoluta.

## 6. Avanço do tempo e eventos de transição

O nível efetivo é calculado sob demanda, mas a auditoria precisa registrar promoções e atrasos no instante em que ocorrem. Por isso:

1. O relógio simulado **só avança** por `SimulacaoService.avancar_relogio(minutos)`: botão, modo automático ou cenário.
2. Nesse passo, para cada paciente aguardando, o serviço calcula no intervalo `(início, fim]`:
    - as **promoções**, cujos instantes são `chegada + k * K * SLA` → evento `PROMOCAO_AGING` com esse instante exato;
    - o **vencimento do prazo** `limite_sla = chegada + SLA`, se cair em `[início, fim)` → evento `ATRASO_SLA` com instante = `limite_sla`, uma única vez por paciente.
3. Os eventos são gravados em ordem de instante, numa transação; **só depois do commit** o relógio avança.
4. Avançar 720 min de uma vez ou em vários passos gera exatamente os mesmos eventos.

## 7. Atendimento

1. O serviço consulta o relógio e pede à fila o próximo paciente (`proximo`), **sem retirá-lo**.
2. O serviço calcula o tempo de espera entre chegada e início do atendimento e compara com o SLA da classificação original.
3. Grava o evento `ATENDIMENTO` (instante, espera, SLA, nível efetivo, estado da fila) e a linha da tabela `atendimento`, numa transação.
4. **Somente após o commit**, retira o paciente da fila (`retirar_proximo`, O(1)).
5. Fila vazia resulta em `FilaVaziaError`, tratada pela interface com mensagem compreensível.

O atendimento é instantâneo para a fila: o paciente sai dela ao ser chamado. A capacidade do serviço é modelada nos cenários como taxa de atendimentos (ex.: 1 a cada 6 min).

## 8. SLA

- Espera atual: `agora - chegada`, em minutos simulados.
- Espera final: `inicio_atendimento - chegada`.
- Um paciente aguardando está com SLA estourado quando `espera_atual > SLA_original`.
- Um atendimento descumpre o SLA quando `espera_final > SLA_original`.
- O aging não altera o SLA original.
- O comparador é sempre `>`: espera igual ao SLA está **dentro** do prazo. Testes de fronteira cobrem esse caso.

## 9. Remoção e auditoria

**Remoção:** um paciente pode sair sem atendimento, com motivo de uma lista controlada (`DESISTENCIA` ou `ERRO_CADASTRO`). A remoção identifica o paciente pelo ID, grava `REMOCAO` com instante e motivo, retira o paciente da fila após o commit e não cria registro de atendimento.

**Auditoria:** toda mudança relevante gera um evento append-only — `ENTRADA`, `PROMOCAO_AGING`, `ATENDIMENTO`, `REMOCAO` e `ATRASO_SLA`. Cada evento guarda o **estado da fila logo após ele**: a quantidade de pacientes de cada cor e o total.

O histórico nunca é apagado ou atualizado: *triggers* no `sql/schema.sql` bloqueiam `UPDATE` e `DELETE` na tabela `evento_fila`. Correções são representadas por novos eventos. Instantes são gravados em texto ISO-8601 (`YYYY-MM-DDTHH:MM:SS`), sempre do relógio simulado.

## 10. Exemplo de trilha de auditoria

Azul que chega às 08:00 e é atendido às 20:00 (cenário da seção 5):

| Instante | Evento | Nível efetivo | Detalhes | Fila após |
|---|---|---:|---|---:|
| 08:00 | `ENTRADA` | 5 | cor = AZUL | 1 |
| 12:00 | `PROMOCAO_AGING` | 4 | espera 240 min | 1 |
| 12:00 | `ATRASO_SLA` | 4 | SLA 240 min | 1 |
| 16:00 | `PROMOCAO_AGING` | 3 | espera 480 min | 1 |
| 20:00 | `PROMOCAO_AGING` | 2 | espera 720 min | 1 |
| 20:00 | `ATENDIMENTO` | 2 | espera 720 min; SLA descumprido | 0 |

O `logs.sql` gerado pela aplicação contém o catálogo de cores, os pacientes, os eventos e os atendimentos nessa ordem, dentro de uma transação, e executa em um banco vazio criado pelo `schema.sql`.

## 11. Critérios mínimos de aceite

- [ ] Vermelho é sempre priorizado sobre os demais níveis.
- [ ] FIFO é respeitado dentro do mesmo nível efetivo.
- [ ] O desempate final usa ID crescente.
- [ ] Aging altera apenas o nível efetivo, não a classificação nem o SLA original.
- [ ] Um Azul chega ao piso em 720 min (K = 1, piso = 2).
- [ ] Sem aging, com mais chegadas de Laranja do que capacidade, o Azul nunca é atendido (T1).
- [ ] Avançar o relógio em um ou vários passos gera os mesmos eventos de promoção e atraso.
- [ ] Fila vazia é tratada sem erro não controlado na interface.
- [ ] Remoção não gera atendimento e produz evento de auditoria.
- [ ] Todo evento registra o estado da fila por cor após a operação.
- [ ] Nenhuma mudança na fila em memória acontece antes do commit no banco.
- [ ] Os cálculos usam relógio injetável para testes determinísticos.
- [ ] Os parâmetros pendentes foram validados antes da entrega final.
