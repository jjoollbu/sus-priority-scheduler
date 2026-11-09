"""Simulador de plantão: fluxo contínuo de chegadas e atendimentos.

Reproduz um pronto-atendimento em que pacientes de todas as cores chegam ao
longo do tempo e alguns médicos vão chamando o próximo da fila. Serve para
mostrar, com muitos pacientes, quem fica esperando tempo demais.

Persistência: o simulador NÃO conhece SQL. Ele avisa cada acontecimento a uma
`RegistroPlantao` (porta abstrata) e só altera a fila em memória DEPOIS que o
registro confirmou a gravação (commit). A implementação com SQLite fica em
`triagem.persistencia`.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from triagem.dominio.atendimento import Atendimento
from triagem.dominio.enums import ClassificacaoRisco, TipoEvento
from triagem.dominio.evento import EventoFila
from triagem.dominio.paciente import Paciente
from triagem.dominio.relogio import RelogioSimulado
from triagem.fila.fila_prioridade import FilaPrioridade
from triagem.fila.politicas import PoliticaFairness

INICIO = datetime(2026, 11, 24, 8, 0)
INTERVALO_AMOSTRA_MIN = 10  # de quanto em quanto tempo guardamos uma "foto" da fila

# Mistura de cores aproximada de uma UPA: a maioria é Verde/Amarelo.
PROPORCAO_PADRAO: dict[ClassificacaoRisco, float] = {
    ClassificacaoRisco.VERMELHO: 0.02,
    ClassificacaoRisco.LARANJA: 0.13,
    ClassificacaoRisco.AMARELO: 0.30,
    ClassificacaoRisco.VERDE: 0.40,
    ClassificacaoRisco.AZUL: 0.15,
}

NOMES = (
    "Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabriela", "Heitor",
    "Isabela", "João", "Karen", "Lucas", "Marina", "Nelson", "Olívia", "Paulo",
    "Quitéria", "Rafael", "Sônia", "Tiago", "Úrsula", "Vítor", "Wanda", "Yara",
)  # fmt: skip

QUEIXAS: dict[ClassificacaoRisco, str] = {
    ClassificacaoRisco.VERMELHO: "parada respiratória",
    ClassificacaoRisco.LARANJA: "dor no peito intensa",
    ClassificacaoRisco.AMARELO: "febre alta e vômitos",
    ClassificacaoRisco.VERDE: "dor de garganta",
    ClassificacaoRisco.AZUL: "troca de receita",
}


@dataclass(frozen=True)
class ConfigPlantao:
    """Parâmetros do fluxo: demanda (chegadas) e capacidade (médicos).

    Padrão: 15 chegadas/h para 12 atendimentos/h (2 médicos, 10 min cada),
    ou seja, uma UPA 25% acima da capacidade.
    """

    chegadas_por_hora: float = 15.0
    medicos: int = 2
    duracao_consulta_min: int = 10
    proporcao: dict[ClassificacaoRisco, float] = field(
        default_factory=lambda: dict(PROPORCAO_PADRAO)
    )
    semente: int = 42  # mesma semente => mesmas chegadas (reprodutível)

    def __post_init__(self) -> None:
        """Recusa parâmetros que não fazem sentido."""
        if not 0 <= self.chegadas_por_hora <= 60:
            raise ValueError("Chegadas por hora devem estar entre 0 e 60.")
        if self.medicos < 1 or self.duracao_consulta_min < 1:
            raise ValueError("É preciso ao menos 1 médico e consulta de 1 min.")
        if (
            set(self.proporcao) != set(ClassificacaoRisco)
            or sum(self.proporcao.values()) <= 0
        ):
            raise ValueError("A proporção precisa ter peso para as 5 cores.")

    @property
    def capacidade_por_hora(self) -> float:
        """Quantos pacientes a equipe consegue atender por hora."""
        return self.medicos * 60 / self.duracao_consulta_min


class RegistroPlantao(ABC):
    """Porta de gravação: quem implementa grava e faz commit (ex.: SQLite).

    Se a gravação falhar, o método levanta exceção e o simulador não altera a
    fila: memória e banco nunca ficam diferentes.
    """

    @abstractmethod
    def registrar_entrada(self, evento: EventoFila) -> None:
        """Grava o paciente novo e o evento ENTRADA numa transação."""

    @abstractmethod
    def registrar_evento(self, evento: EventoFila) -> None:
        """Grava um evento avulso (PROMOCAO_AGING, ATRASO_SLA)."""

    @abstractmethod
    def registrar_atendimento(
        self, atendimento: Atendimento, evento: EventoFila
    ) -> None:
        """Grava o atendimento e o evento ATENDIMENTO numa transação."""


@dataclass(frozen=True)
class Amostra:
    """Foto da fila num instante, usada nos gráficos."""

    instante: datetime
    aguardando_por_cor: dict[ClassificacaoRisco, int]
    maior_espera_por_cor: dict[ClassificacaoRisco, float]  # 0 se ninguém espera


@dataclass(frozen=True)
class ResumoCor:
    """Números de uma cor ao fim (ou no meio) do plantão."""

    cor: ClassificacaoRisco
    chegaram: int
    atendidos: int
    aguardando: int
    espera_media_atendidos: float | None
    maior_espera: float  # inclui quem AINDA está esperando
    pct_dentro_sla: float | None


class SimuladorPlantao:
    """Avança o relógio minuto a minuto gerando chegadas e atendimentos.

    A ordem de atendimento continua sendo decidida pela FilaPrioridade e pela
    política injetada; o simulador só produz o fluxo e registra o que houve.
    """

    def __init__(
        self,
        politica: PoliticaFairness,
        relogio: RelogioSimulado,
        config: ConfigPlantao | None = None,
        chegadas_automaticas: bool = True,
        registro: RegistroPlantao | None = None,
    ) -> None:
        """Começa um plantão vazio no instante atual do relógio.

        `registro` é opcional: sem ele, nada é gravado (útil em testes e demos).
        """
        self._config = config or ConfigPlantao()
        self._relogio = relogio
        self._fila = FilaPrioridade(politica)
        self._registro = registro
        self._sorteio = random.Random(self._config.semente)
        self._proximo_id = 1
        self._medico_livre_em = [relogio.agora()] * self._config.medicos
        self._ultimo_nivel: dict[int, int] = {}  # para detectar promoções
        self._atrasados: set[int] = set()  # quem já teve ATRASO_SLA registrado
        self._chegados: list[Paciente] = []
        self._eventos: list[EventoFila] = []
        self._atendimentos: list[Atendimento] = []
        self._amostras: list[Amostra] = []
        self._inicio = relogio.agora()
        self.chegadas_automaticas = chegadas_automaticas
        self._amostrar()

    # ----- leitura -----
    @property
    def fila(self) -> FilaPrioridade:
        """A fila de prioridade do plantão."""
        return self._fila

    @property
    def relogio(self) -> RelogioSimulado:
        """Relógio simulado do plantão."""
        return self._relogio

    @property
    def config(self) -> ConfigPlantao:
        """Parâmetros do fluxo."""
        return self._config

    @property
    def eventos(self) -> list[EventoFila]:
        """Cópia do histórico de eventos, do mais antigo ao mais recente."""
        return list(self._eventos)

    @property
    def atendimentos(self) -> list[Atendimento]:
        """Cópia dos atendimentos realizados."""
        return list(self._atendimentos)

    @property
    def amostras(self) -> list[Amostra]:
        """Cópia das fotos periódicas da fila."""
        return list(self._amostras)

    # ----- ações -----
    def novo_id(self) -> int:
        """Reserva o próximo id de paciente."""
        id_ = self._proximo_id
        self._proximo_id += 1
        return id_

    def adicionar(self, paciente: Paciente) -> None:
        """Grava a ENTRADA e, só depois do commit, coloca o paciente na fila."""
        self._fila.validar_insercao(paciente)  # erro aqui não grava nada
        agora = self._relogio.agora()
        nivel = self._fila.nivel_efetivo(paciente, agora)
        evento = self._evento(
            TipoEvento.ENTRADA,
            agora,
            paciente,
            nivel,
            f"cor = {paciente.classificacao.cor}",
            variacao=+1,
        )
        if self._registro:
            self._registro.registrar_entrada(evento)
        # --- após o commit ---
        self._fila.inserir(paciente)
        self._proximo_id = max(self._proximo_id, paciente.id + 1)
        self._chegados.append(paciente)
        self._ultimo_nivel[paciente.id] = nivel
        self._eventos.append(evento)

    def atender_proximo(self, medico: int | None = None) -> Atendimento:
        """Chama o próximo da fila; FilaVaziaError se não houver ninguém.

        Consulta o próximo SEM retirar, grava atendimento + evento e só então
        retira o paciente da fila.
        """
        agora = self._relogio.agora()
        paciente = self._fila.proximo(agora)
        atendimento = Atendimento(
            paciente=paciente,
            inicio=agora,
            espera_min=paciente.tempo_espera(agora),
            nivel_efetivo=self._fila.nivel_efetivo(paciente, agora),
            medico=medico,
        )
        quem = f"médico {medico}" if medico else "chamada manual"
        prazo = "SLA cumprido" if atendimento.dentro_do_sla else "SLA descumprido"
        evento = self._evento(
            TipoEvento.ATENDIMENTO,
            agora,
            paciente,
            atendimento.nivel_efetivo,
            f"{quem}; espera {atendimento.espera_min:.0f} min; {prazo}",
            variacao=-1,
        )
        if self._registro:
            self._registro.registrar_atendimento(atendimento, evento)
        # --- após o commit ---
        self._fila.retirar_proximo(agora)
        self._ultimo_nivel.pop(paciente.id, None)
        self._atendimentos.append(atendimento)
        self._eventos.append(evento)
        return atendimento

    def avancar(self, minutos: int) -> None:
        """Avança o plantão minuto a minuto."""
        if minutos < 0:
            raise ValueError("Não é possível voltar o relógio.")
        for _ in range(minutos):
            self._relogio.avancar(1)
            self._passo()

    # ----- funcionamento interno -----
    def _passo(self) -> None:
        """Um minuto: transições (aging/atraso), chegada e médicos livres chamam."""
        agora = self._relogio.agora()
        self._registrar_transicoes(agora)
        if self.chegadas_automaticas:
            self._sortear_chegada(agora)
        for i, livre_em in enumerate(self._medico_livre_em):
            if livre_em <= agora and len(self._fila) > 0:
                self.atender_proximo(medico=i + 1)
                self._medico_livre_em[i] = agora + timedelta(
                    minutes=self._config.duracao_consulta_min
                )
        minutos_passados = (agora - self._inicio).total_seconds() / 60
        if minutos_passados % INTERVALO_AMOSTRA_MIN == 0:
            self._amostrar()

    def _sortear_chegada(self, agora: datetime) -> None:
        """Com probabilidade chegadas_por_hora / 60, chega 1 paciente."""
        if self._sorteio.random() >= self._config.chegadas_por_hora / 60:
            return
        cores = list(self._config.proporcao)
        cor = self._sorteio.choices(
            cores, weights=list(self._config.proporcao.values())
        )[0]
        id_ = self.novo_id()
        self.adicionar(
            Paciente(
                id=id_,
                nome=NOMES[(id_ - 1) % len(NOMES)],
                idade=self._sorteio.randint(1, 90),
                queixa=QUEIXAS[cor],
                classificacao=cor,
                chegada=agora,
            )
        )

    def _registrar_transicoes(self, agora: datetime) -> None:
        """Gera PROMOCAO_AGING (nível mudou) e ATRASO_SLA (prazo venceu)."""
        for p in self._fila.aguardando():
            nivel = self._fila.nivel_efetivo(p, agora)
            anterior = self._ultimo_nivel.get(p.id, nivel)
            if nivel != anterior:
                espera = p.tempo_espera(agora)
                self._gravar(
                    self._evento(
                        TipoEvento.PROMOCAO_AGING,
                        agora,
                        p,
                        nivel,
                        f"espera {espera:.0f} min; nível {anterior} -> {nivel}",
                    )
                )
                self._ultimo_nivel[p.id] = nivel
            if p.id not in self._atrasados and p.sla_estourado(agora):
                # O instante do evento é o vencimento exato do prazo.
                self._gravar(
                    self._evento(
                        TipoEvento.ATRASO_SLA,
                        p.limite_sla(),
                        p,
                        nivel,
                        f"SLA {p.classificacao.sla_minutos} min",
                    )
                )
                self._atrasados.add(p.id)

    def _evento(
        self,
        tipo: TipoEvento,
        instante: datetime,
        paciente: Paciente,
        nivel_efetivo: int,
        detalhes: str,
        variacao: int = 0,
    ) -> EventoFila:
        """Monta o evento com a fila por cor LOGO APÓS ele (variacao = +1/-1/0)."""
        contagem = self._fila.contagem_por_cor()
        contagem[paciente.classificacao] += variacao
        return EventoFila(tipo, instante, paciente, nivel_efetivo, detalhes, contagem)

    def _gravar(self, evento: EventoFila) -> None:
        """Grava um evento avulso e, após o commit, guarda na memória."""
        if self._registro:
            self._registro.registrar_evento(evento)
        self._eventos.append(evento)

    def _amostrar(self) -> None:
        """Guarda quantos esperam e a maior espera atual de cada cor."""
        agora = self._relogio.agora()
        maior = dict.fromkeys(ClassificacaoRisco, 0.0)
        for p in self._fila.aguardando():
            cor = p.classificacao
            maior[cor] = max(maior[cor], p.tempo_espera(agora))
        self._amostras.append(Amostra(agora, self._fila.contagem_por_cor(), maior))

    # ----- relatórios -----
    def atendimento_de(self, paciente_id: int) -> Atendimento | None:
        """Atendimento do paciente, ou None se ele ainda não foi chamado."""
        for atendimento in self._atendimentos:
            if atendimento.paciente.id == paciente_id:
                return atendimento
        return None

    def resumo_por_cor(self) -> list[ResumoCor]:
        """Chegadas, atendimentos e esperas de cada cor até agora."""
        agora = self._relogio.agora()
        resumos = []
        for cor in ClassificacaoRisco:
            atendidos = [
                a for a in self._atendimentos if a.paciente.classificacao is cor
            ]
            esperando = [p for p in self._fila.aguardando() if p.classificacao is cor]
            esperas = [a.espera_min for a in atendidos]
            esperas_todas = esperas + [p.tempo_espera(agora) for p in esperando]
            resumos.append(
                ResumoCor(
                    cor=cor,
                    chegaram=sum(1 for p in self._chegados if p.classificacao is cor),
                    atendidos=len(atendidos),
                    aguardando=len(esperando),
                    espera_media_atendidos=(
                        sum(esperas) / len(esperas) if esperas else None
                    ),
                    maior_espera=max(esperas_todas, default=0.0),
                    pct_dentro_sla=(
                        100 * sum(a.dentro_do_sla for a in atendidos) / len(atendidos)
                        if atendidos
                        else None
                    ),
                )
            )
        return resumos


def rodar_plantao(
    politica: PoliticaFairness,
    horas: int = 24,
    config: ConfigPlantao | None = None,
    registro: RegistroPlantao | None = None,
) -> SimuladorPlantao:
    """Roda um plantão completo a partir de INICIO e devolve o simulador."""
    simulador = SimuladorPlantao(
        politica, RelogioSimulado(INICIO), config, registro=registro
    )
    simulador.avancar(horas * 60)
    return simulador