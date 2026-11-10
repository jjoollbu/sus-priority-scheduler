-- Estrutura do banco da triagem (SQLite). Somente DDL: nenhum dado aqui.
-- O catálogo de cores é preenchido pela aplicação a partir de config.py,
-- e o histórico (logs.sql) é gerado pela aplicação.
--
-- Regras garantidas pelo próprio banco:
--   * evento_fila e atendimento são append-only (triggers bloqueiam UPDATE/DELETE);
--   * instantes em texto ISO-8601 'YYYY-MM-DDTHH:MM:SS', sempre do relógio simulado;
--   * chaves estrangeiras ligam evento e atendimento ao paciente do mesmo plantão.

PRAGMA foreign_keys = ON;

-- Catálogo das 5 cores do Protocolo de Manchester.
CREATE TABLE IF NOT EXISTS classificacao (
    nivel        INTEGER PRIMARY KEY CHECK (nivel BETWEEN 1 AND 5),
    cor          TEXT    NOT NULL UNIQUE,
    sla_minutos  INTEGER NOT NULL CHECK (sla_minutos >= 0)
);

-- Cada execução da simulação é um plantão, com a regra da fila usada.
CREATE TABLE IF NOT EXISTS plantao (
    id                    INTEGER PRIMARY KEY,
    inicio                TEXT    NOT NULL,
    politica              TEXT    NOT NULL CHECK (politica IN ('SEM_AGING', 'AGING')),
    chegadas_por_hora     REAL    NOT NULL CHECK (chegadas_por_hora >= 0),
    medicos               INTEGER NOT NULL CHECK (medicos >= 1),
    duracao_consulta_min  INTEGER NOT NULL CHECK (duracao_consulta_min >= 1),
    semente               INTEGER NOT NULL
);

-- Pacientes que entraram na fila (o id é único dentro do plantão).
CREATE TABLE IF NOT EXISTS paciente (
    plantao_id  INTEGER NOT NULL REFERENCES plantao (id),
    id          INTEGER NOT NULL CHECK (id >= 0),
    nome        TEXT    NOT NULL CHECK (length(trim(nome)) > 0),
    idade       INTEGER NOT NULL CHECK (idade BETWEEN 0 AND 130),
    queixa      TEXT    NOT NULL,
    nivel       INTEGER NOT NULL REFERENCES classificacao (nivel),
    chegada     TEXT    NOT NULL,
    PRIMARY KEY (plantao_id, id)
);

-- Trilha de auditoria: tudo o que aconteceu com cada paciente.
-- qtd_* e total guardam o estado da fila LOGO APÓS o evento.
CREATE TABLE IF NOT EXISTS evento_fila (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    plantao_id     INTEGER NOT NULL,
    paciente_id    INTEGER NOT NULL,
    tipo           TEXT    NOT NULL CHECK (
                       tipo IN ('ENTRADA', 'PROMOCAO_AGING', 'ATENDIMENTO',
                                'REMOCAO', 'ATRASO_SLA')
                   ),
    instante       TEXT    NOT NULL,
    nivel_efetivo  INTEGER NOT NULL CHECK (nivel_efetivo BETWEEN 1 AND 5),
    detalhes       TEXT    NOT NULL,
    qtd_vermelho   INTEGER NOT NULL CHECK (qtd_vermelho >= 0),
    qtd_laranja    INTEGER NOT NULL CHECK (qtd_laranja >= 0),
    qtd_amarelo    INTEGER NOT NULL CHECK (qtd_amarelo >= 0),
    qtd_verde      INTEGER NOT NULL CHECK (qtd_verde >= 0),
    qtd_azul       INTEGER NOT NULL CHECK (qtd_azul >= 0),
    total          INTEGER NOT NULL CHECK (
                       total = qtd_vermelho + qtd_laranja + qtd_amarelo
                               + qtd_verde + qtd_azul
                   ),
    FOREIGN KEY (plantao_id, paciente_id) REFERENCES paciente (plantao_id, id)
);

CREATE INDEX IF NOT EXISTS idx_evento_paciente
    ON evento_fila (plantao_id, paciente_id);

-- Um paciente é atendido no máximo uma vez.
CREATE TABLE IF NOT EXISTS atendimento (
    plantao_id     INTEGER NOT NULL,
    paciente_id    INTEGER NOT NULL,
    inicio         TEXT    NOT NULL,
    espera_min     REAL    NOT NULL CHECK (espera_min >= 0),
    nivel_efetivo  INTEGER NOT NULL CHECK (nivel_efetivo BETWEEN 1 AND 5),
    dentro_do_sla  INTEGER NOT NULL CHECK (dentro_do_sla IN (0, 1)),
    medico         INTEGER,  -- NULL quando a chamada é manual
    PRIMARY KEY (plantao_id, paciente_id),
    FOREIGN KEY (plantao_id, paciente_id) REFERENCES paciente (plantao_id, id)
);

-- Histórico append-only: correções viram novos eventos, nunca edições.
CREATE TRIGGER IF NOT EXISTS evento_fila_sem_update
BEFORE UPDATE ON evento_fila
BEGIN
    SELECT RAISE(ABORT, 'evento_fila é append-only: UPDATE proibido');
END;

CREATE TRIGGER IF NOT EXISTS evento_fila_sem_delete
BEFORE DELETE ON evento_fila
BEGIN
    SELECT RAISE(ABORT, 'evento_fila é append-only: DELETE proibido');
END;

CREATE TRIGGER IF NOT EXISTS atendimento_sem_update
BEFORE UPDATE ON atendimento
BEGIN
    SELECT RAISE(ABORT, 'atendimento é append-only: UPDATE proibido');
END;

CREATE TRIGGER IF NOT EXISTS atendimento_sem_delete
BEFORE DELETE ON atendimento
BEGIN
    SELECT RAISE(ABORT, 'atendimento é append-only: DELETE proibido');
END;
