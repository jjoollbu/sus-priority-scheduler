# Regras de negócio — Simulador de filas de prioridade

> **Status: proposta para validação da equipe e do docente.** Este documento traduz o planejamento técnico v0.2 em regras testáveis. Os parâmetros numéricos não devem ser tratados como protocolo clínico oficial.

## 1. Objetivo e limites

O sistema simula uma fila de atendimento com prioridades. Ele não realiza avaliação clínica, não recomenda classificação de risco e não substitui o Protocolo de Manchester nem a atuação de profissionais habilitados. A classificação do paciente fictício é informada manualmente pelo operador da simulação.

As cores e os tempos abaixo são parâmetros acadêmicos configuráveis, sujeitos à validação da equipe e do docente.

## 2. Classificação simulada

| Cor | Nível base | SLA simulado | Regra geral |
|---|---:|---:|---|
| Vermelho — emergência | 1 | 0 min (imediato) | Prioridade máxima; FIFO entre vermelhos |
| Laranja — muito urgente | 2 | 10 min | Segundo nível; também é o piso proposto para aging |
| Amarelo — urgente | 3 | 60 min | Pode ser promovido por aging |
| Verde — pouco urgente | 4 | 120 min | Pode ser promovido por aging |
| Azul — não urgente | 5 | 240 min | Pode ser promovido por aging |

**Pendente de confirmação:** os valores de SLA, a escala e a nomenclatura devem ser validados antes de serem apresentados como definitivos. Devem permanecer centralizados em configuração, sem espalhar números mágicos pelo código.

## 3. Cadastro e entrada na fila

1. O operador informa os dados do paciente fictício e seleciona uma classificação.
2. O serviço cria o paciente com identificador único e instante de chegada obtido do relógio injetado.
3. O paciente é inserido no fim da fila FIFO correspondente à sua classificação original.
4. A operação gera um evento `ENTRADA` na auditoria.
5. O evento deve registrar o tamanho da fila após a operação.

A camada de interface não deve implementar essas regras: deve apenas validar campos de apresentação e chamar o serviço de aplicação.

## 4. Ordenação e desempate

A ordem de atendimento é determinada pela chave:

`(nível_efetivo, instante_de_chegada, id)`

Critérios, nesta ordem:
1. Menor nível efetivo tem prioridade.
2. Em caso de mesmo nível efetivo, atende primeiro quem chegou antes (FIFO).
3. Persistindo o empate, vence o menor identificador.

O nível efetivo é calculado pela política de fairness no instante consultado. A classificação original do paciente não é alterada.

## 5. Aging e prevenção de starvation

A proposta técnica utiliza cinco filas FIFO (`collections.deque`), uma por cor, e uma política de aging que promove o nível efetivo conforme o tempo de espera.

Fórmula proposta:

`promocoes = floor(espera_minutos / (K * SLA_da_classificacao_original))`

`nivel_efetivo = max(PISO, nivel_base - promocoes)`

Restrições propostas:
- Vermelho permanece no nível 1 e não é ultrapassado.
- O piso proposto é nível 2 (Laranja).
- O paciente pode ser promovido gradualmente, mas sua classificação original e seu SLA original permanecem inalterados.
- A política e seus parâmetros devem ser configuráveis e testáveis com relógio simulado.

**Pendente de validação:** `K = 1` e `PISO = 2` são recomendações do planejamento, não decisões confirmadas. A garantia contra starvation depende também do fluxo de chegada de pacientes vermelhos; não se deve prometer espera máxima absoluta sem explicitar essa condição.

## 6. Atendimento

1. O serviço consulta o relógio e solicita à fila o próximo paciente.
2. A fila seleciona o paciente de melhor prioridade efetiva, sem a interface manipular suas estruturas internas.
3. O serviço calcula o tempo de espera entre chegada e início do atendimento.
4. O serviço compara a espera com o SLA da classificação original.
5. O paciente é retirado da fila e é registrado um evento `ATENDIMENTO`, com instante, espera, SLA, nível efetivo e tamanho da fila após a retirada.
6. Fila vazia deve resultar em exceção de domínio específica, tratada pela interface com mensagem compreensível.

## 7. SLA

- Espera atual: `agora - chegada`, em minutos simulados.
- Espera final: `inicio_atendimento - chegada`.
- Um paciente aguardando está com SLA estourado quando `espera_atual > SLA_original`.
- Um atendimento descumpre o SLA quando `espera_final > SLA_original`.
- O aging não altera o SLA original.
- O comparador (`>` ou `>=`) deve ser aplicado de forma consistente e coberto por testes de fronteira.

## 8. Remoção

Um paciente pode ser removido sem atendimento, por exemplo, em caso de desistência ou erro de cadastro. A remoção deve:
- identificar o paciente pelo ID;
- removê-lo da fila;
- registrar `REMOCAO`, com instante e motivo;
- não criar registro de atendimento.

**Recomendação:** restringir o motivo a uma lista controlada, evitando texto livre inconsistente.

## 9. Auditoria

Toda mudança relevante deve gerar evento append-only:
- `ENTRADA`;
- `PROMOCAO_AGING`;
- `ATENDIMENTO`;
- `REMOCAO`;
- `ATRASO_SLA`.

O histórico não deve ser apagado ou atualizado para “corrigir” eventos anteriores. Correções devem ser representadas por novos eventos, quando aplicável. O registro do evento e a alteração persistida relacionada devem ocorrer na mesma transação.

O tamanho da fila deve ser registrado nos eventos de entrada e atendimento, conforme exigência destacada no planejamento.

## 10. Critérios mínimos de aceite

- [ ] Vermelho é sempre priorizado sobre os demais níveis.
- [ ] FIFO é respeitado dentro do mesmo nível efetivo.
- [ ] O desempate final usa ID crescente.
- [ ] Aging altera apenas o nível efetivo, não a classificação nem o SLA original.
- [ ] Fila vazia é tratada sem erro não controlado na interface.
- [ ] Remoção não gera atendimento e produz evento de auditoria.
- [ ] Entrada e atendimento registram o tamanho da fila após a operação.
- [ ] Os cálculos usam relógio injetável para testes determinísticos.
- [ ] Os parâmetros pendentes foram validados antes da entrega final.
