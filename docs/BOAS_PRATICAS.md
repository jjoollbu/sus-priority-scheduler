# Boas práticas de desenvolvimento

Este documento define um fluxo simples para colaboração no projeto A3. A proposta é usar GitHub Flow: `main` permanece estável e cada tarefa é desenvolvida em uma branch própria.

## 1. Organização do trabalho

- Cada integrante utiliza sua própria conta GitHub.
- Cada tarefa relevante deve estar associada a uma issue, quando possível.
- Evitar que duas pessoas alterem simultaneamente o mesmo arquivo sem alinhamento.
- Dividir tarefas em entregas pequenas e revisáveis.
- Não concentrar toda a implementação ou documentação em uma única pessoa.
- Cada integrante deve compreender e conseguir explicar o código que desenvolveu.

## 2. Branches

A branch `main` deve conter apenas versões integradas e revisadas.

Padrões sugeridos:

| Tipo | Prefixo | Exemplo |
|---|---|---|
| Funcionalidade | `feat/` | `feat/cadastro-paciente` |
| Correção | `fix/` | `fix/calculo-sla` |
| Testes | `test/` | `test/fila-prioridade` |
| Documentação | `docs/` | `docs/regras-negocio` |
| Manutenção | `chore/` | `chore/configura-ruff` |

Criar a branch a partir da versão atualizada de `main`:

```bash
git switch main
git pull origin main
git switch -c docs/regras-negocio
```

## 3. Commits

Usar mensagens curtas, no imperativo e com prefixo Conventional Commits:

- `feat:` nova funcionalidade;
- `fix:` correção;
- `test:` testes;
- `docs:` documentação;
- `refactor:` reorganização sem mudança de comportamento;
- `chore:` configuração e manutenção.

Exemplos:

```bash
git commit -m "docs: adiciona regras de negócio da triagem"
git commit -m "feat: implementa cadastro de pacientes"
git commit -m "test: adiciona testes para cálculo de SLA"
```

Boas práticas:
- um commit deve representar uma alteração coerente;
- evitar commits genéricos como `atualização`, `final` ou `mudanças`;
- não incluir arquivos temporários, banco local ou segredos;
- conferir `git status` e `git diff --staged` antes de confirmar.

## 4. Pull Requests

Toda alteração deve ser integrada por Pull Request, preferencialmente com revisão de pelo menos outro integrante.

Descrição mínima:

1. **O que muda:** resumo objetivo.
2. **Por que:** requisito atendido.
3. **Como testar:** comandos e cenário verificado.
4. **Evidências:** imagens ou resultados, quando fizer sentido.

Checklist:

- [ ] Alteração tem escopo claro.
- [ ] Testes relevantes foram executados.
- [ ] `ruff check .` não aponta problemas.
- [ ] `ruff format --check .` passa.
- [ ] Funções públicas possuem type hints e docstrings.
- [ ] Documentação/diagramas foram atualizados, se necessário.
- [ ] O autor consegue explicar a implementação.

## 5. Padrões Python

- Classes em `PascalCase`.
- Funções, métodos e variáveis em `snake_case`.
- Constantes em `UPPER_CASE`.
- Um conceito principal por módulo.
- Type hints nas assinaturas públicas.
- Docstrings em português, curtas e objetivas.
- Preferir composição à herança quando ambas resolverem o problema.
- Usar `dataclass` para entidades de dados quando adequado.
- Evitar classes com responsabilidades excessivas.
- Evitar imports circulares.
- Não capturar exceções com `except:` genérico.
- Criar exceções de domínio para situações esperadas, como fila vazia ou paciente inexistente.

**Idioma dos identificadores:** o planejamento ainda registra como pendente a escolha entre português e inglês. Até a equipe decidir, manter consistência dentro do projeto e registrar a decisão.

## 6. Separação de responsabilidades

- A interface Streamlit não decide regras de negócio.
- Os serviços coordenam os casos de uso.
- O domínio não importa Streamlit, SQLite ou código de interface.
- A fila não acessa banco de dados.
- O acesso SQL fica concentrado na camada de persistência.
- A auditoria é append-only: não atualizar ou apagar eventos históricos.

## 7. Testes e qualidade

Executar antes de abrir um Pull Request:

```bash
pytest
ruff check .
ruff format --check .
```

Priorizar testes unitários para:
- classificação e validação de pacientes;
- ordenação e desempate FIFO;
- política de aging;
- cálculo de espera e SLA;
- remoção e fila vazia.

Testes de integração devem verificar serviços com SQLite em memória (`:memory:`), incluindo a persistência e a exportação/reexecução dos eventos SQL.

## 8. Definição de pronto

Uma tarefa está pronta para integração quando:
- implementação e testes estão concluídos;
- revisão foi realizada;
- lint e formatação passaram;
- documentação necessária foi atualizada;
- o Pull Request foi aprovado e integrado;
- o autor consegue explicar a solução e suas decisões.

## 9. Segurança e arquivos locais

Não versionar:
- `.env` e credenciais;
- `secrets.toml`;
- ambientes virtuais;
- caches;
- bancos SQLite locais usados durante desenvolvimento;
- arquivos temporários de IDE/sistema.

Nunca incluir dados pessoais reais de pacientes. Usar exclusivamente dados fictícios na simulação.
