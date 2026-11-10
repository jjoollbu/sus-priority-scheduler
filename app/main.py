"""Tela do plantão: fila de prioridade com chegadas e atendimentos automáticos.

Executar: streamlit run app/main.py
A tela só exibe e dispara ações; toda regra de ordenação vem da FilaPrioridade
e todo o fluxo de chegadas/atendimentos vem do SimuladorPlantao.

Banco de dados: cada plantão é gravado em dados/triagem.db (SQLite). A fila
fica em memória (rápida), mas cada mudança é gravada ANTES de acontecer na
memória. O histórico mostrado na tela é lido do banco.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from triagem.config import CAMINHO_BANCO, RAIZ_PROJETO
from triagem.dominio.enums import ClassificacaoRisco
from triagem.dominio.paciente import Paciente
from triagem.dominio.relogio import RelogioSimulado
from triagem.fila.cenario_starvation import montar_fila_inicial
from triagem.fila.plantao import INICIO, ConfigPlantao, SimuladorPlantao
from triagem.fila.politicas import PoliticaAging, PoliticaFairness, PoliticaSemAging
from triagem.persistencia import repositorio
from triagem.persistencia.conexao import abrir_conexao
from triagem.persistencia.exportador_sql import exportar_logs
from triagem.persistencia.repositorio import RepositorioPlantao

FORMATO_HORA = "%d/%m %H:%M"

# A cor nunca aparece sozinha: o símbolo vem sempre acompanhado do nome.
SIMBOLO_COR = {
    ClassificacaoRisco.VERMELHO: "🔴",
    ClassificacaoRisco.LARANJA: "🟠",
    ClassificacaoRisco.AMARELO: "🟡",
    ClassificacaoRisco.VERDE: "🟢",
    ClassificacaoRisco.AZUL: "🔵",
}
# Cores das linhas do gráfico: contraste >= 3:1 no tema claro e no escuro.
COR_LINHA = {
    ClassificacaoRisco.VERMELHO: "#e5484d",
    ClassificacaoRisco.LARANJA: "#dd5a10",
    ClassificacaoRisco.AMARELO: "#b58200",
    ClassificacaoRisco.VERDE: "#2f9a63",
    ClassificacaoRisco.AZUL: "#3e8ee5",
}
# Linhas promovidas pelo aging: texto escuro sobre amarelo-claro (contraste 9,9:1).
COR_DESTAQUE = "background-color: #fff3cd; color: #4d3a00"
NOME_EVENTO = {
    "ENTRADA": "➕ Entrada",
    "PROMOCAO_AGING": "⬆️ Promoção (aging)",
    "ATRASO_SLA": "⚠️ Prazo estourado",
    "ATENDIMENTO": "🩺 Atendimento",
    "REMOCAO": "✖️ Remoção",
}


# ---------------------------------------------------------------- utilidades
def criar_politica(com_aging: bool) -> PoliticaFairness:
    """Escolhe a política de fairness conforme o toggle."""
    return PoliticaAging() if com_aging else PoliticaSemAging()


def horas_e_minutos(minutos: float) -> str:
    """Formata minutos como '9h36'."""
    total = round(minutos)
    return f"{total // 60}h{total % 60:02d}"


def rotulo_cor(cor: ClassificacaoRisco) -> str:
    """Símbolo + nome da cor, ex.: '🔵 Azul'."""
    return f"{SIMBOLO_COR[cor]} {cor.cor}"


def declarar_idioma() -> None:
    """Marca a página como pt-BR (o Streamlit declara "en").

    Sem isso, o leitor de tela lê o texto em português com pronúncia inglesa
    (WCAG 3.1.1). O componente roda num iframe invisível da mesma origem.
    """
    components.html(
        "<script>window.parent.document.documentElement.lang = 'pt-BR';</script>",
        height=0,
    )


def rotulo_cor_banco(cor: str) -> str:
    """Rótulo a partir do nome gravado no banco ('AZUL' -> '🔵 Azul')."""
    return rotulo_cor(ClassificacaoRisco[cor])


def conexao() -> sqlite3.Connection:
    """Conexão com o banco da sessão (aberta uma vez e reaproveitada)."""
    if "conexao" not in st.session_state:
        st.session_state.conexao = abrir_conexao(CAMINHO_BANCO)
    return st.session_state.conexao


def iniciar_estado(com_aging: bool, config: ConfigPlantao) -> None:
    """(Re)cria o plantão: uma linha nova em `plantao` e um simulador ligado a ela."""
    politica = criar_politica(com_aging)
    repo = RepositorioPlantao.novo_plantao(conexao(), politica, config, INICIO)
    st.session_state.sim = SimuladorPlantao(
        politica, RelogioSimulado(INICIO), config, registro=repo
    )
    st.session_state.plantao_id = repo.plantao_id
    st.session_state.com_aging = com_aging
    st.session_state.config = config


# ------------------------------------------------------------ barra lateral
def parametros_plantao() -> ConfigPlantao:
    """Sliders que definem demanda e capacidade do plantão."""
    with st.sidebar:
        st.header("Parâmetros do plantão")
        chegadas = st.slider("Chegadas por hora (demanda)", 4, 30, 15)
        medicos = st.slider("Médicos atendendo", 1, 5, 2)
        consulta = st.slider("Minutos por consulta", 5, 30, 10)
        semente = st.number_input("Semente do sorteio", 0, 9999, 42, step=1)
        config = ConfigPlantao(
            chegadas_por_hora=chegadas,
            medicos=medicos,
            duracao_consulta_min=consulta,
            semente=int(semente),
        )
        carga = config.chegadas_por_hora / config.capacidade_por_hora
        # Repete os valores dos sliders em texto de alto contraste: o número
        # sobre o slider usa a cor do tema, com contraste baixo no modo escuro.
        texto = (
            f"Demanda **{config.chegadas_por_hora:g}/h** × capacidade "
            f"**{config.capacidade_por_hora:g}/h** ({config.medicos} médicos, "
            f"{config.duracao_consulta_min} min por consulta) — {carga:.0%} de ocupação"
        )
        if carga > 1:
            st.warning(f"⚠️ {texto}: plantão **sobrecarregado**.")
        else:
            st.success(f"✅ {texto}: a equipe dá conta.")
    return config


def barra_lateral(config: ConfigPlantao) -> None:
    """Política da fila, fluxo automático e cenários."""
    with st.sidebar:
        st.header("Regra da fila")
        com_aging = st.toggle(
            "Usar aging (anti-starvation)",
            help="Promove um nível a cada K × SLA de espera, até o Laranja.",
        )
        if com_aging != st.session_state.com_aging or config != st.session_state.config:
            iniciar_estado(com_aging, config)

        sim: SimuladorPlantao = st.session_state.sim
        sim.chegadas_automaticas = st.toggle(
            "Chegadas automáticas", value=True, help="Sorteia chegadas a cada minuto."
        )

        if st.button("Reiniciar plantão", width="stretch"):
            iniciar_estado(st.session_state.com_aging, config)

        if st.button("Carregar cenário de starvation", width="stretch"):
            iniciar_estado(st.session_state.com_aging, config)
            sim = st.session_state.sim
            # Usa o relógio do plantão: ele avança até a chegada do último Laranja.
            fila = montar_fila_inicial(sim.fila.politica, sim.relogio)
            for paciente in sorted(fila.aguardando(), key=lambda p: p.chegada):
                sim.adicionar(paciente)
        st.caption(
            "O cenário coloca 1 Azul e 6 Laranjas na fila. Desligue as chegadas "
            "automáticas para ver o caso isolado."
        )

        politica = "com aging" if st.session_state.com_aging else "sem aging"
        st.markdown(f"Regra atual: **{politica}**")


# ----------------------------------------------------------------- página
def explicacao() -> None:
    """Texto curto com o problema que a tela demonstra."""
    st.markdown(
        "Os pacientes chegam sozinhos e os médicos chamam sempre o **mais grave**. "
        "Quando chegam mais pacientes do que a equipe atende, quem tem prioridade "
        "baixa (🟢 Verde, 🔵 Azul) pode **nunca ser chamado**: isso é "
        "*starvation*. Avance o relógio e observe a coluna **Situação** e o "
        "gráfico de espera. Depois ligue o **aging** na barra lateral e compare."
    )


def painel_relogio() -> None:
    """Hora simulada, totais e botões para avançar o tempo."""
    sim: SimuladorPlantao = st.session_state.sim
    col_hora, col_fila, col_atendidos = st.columns(3)
    col_hora.metric("Hora simulada", sim.relogio.agora().strftime(FORMATO_HORA))
    col_fila.metric("Pacientes na fila", len(sim.fila))
    col_atendidos.metric("Pacientes atendidos", len(sim.atendimentos))

    st.markdown("**Avançar o relógio**")
    botoes = st.columns(4)
    opcoes = [("+10 min", 10), ("+1 hora", 60), ("+4 horas", 240), ("+12 horas", 720)]
    for coluna, (rotulo, minutos) in zip(botoes, opcoes, strict=True):
        if coluna.button(rotulo, width="stretch"):
            sim.avancar(minutos)
            st.rerun()


def resumo_por_cor() -> None:
    """Uma coluna por cor: quantos aguardam e há quanto tempo espera o mais antigo."""
    sim: SimuladorPlantao = st.session_state.sim
    agora = sim.relogio.agora()
    st.subheader("Quem está esperando")
    colunas = st.columns(5)
    for coluna, cor in zip(colunas, ClassificacaoRisco, strict=True):
        esperas = [
            p.tempo_espera(agora)
            for p in sim.fila.aguardando()
            if p.classificacao is cor
        ]
        with coluna.container(border=True):
            # Nome em texto comum (quebra linha em tela estreita, não é cortado);
            # o rótulo da métrica fica oculto na tela mas é lido pelo leitor de tela.
            st.markdown(f"**{rotulo_cor(cor)}**")
            st.metric(
                f"{cor.cor}: pacientes na fila",
                len(esperas),
                label_visibility="collapsed",
            )
            if esperas:
                maior = max(esperas)
                st.markdown(f"na fila · mais antigo há **{horas_e_minutos(maior)}**")
                if maior > cor.sla_minutos:
                    st.markdown("⚠️ Prazo estourado")
            else:
                st.markdown("na fila")


def linha_da_fila(
    posicao: int, p: Paciente, nivel_efetivo: int, agora: datetime
) -> dict[str, object]:
    """Converte um paciente numa linha legível da tabela."""
    espera = p.tempo_espera(agora)
    sla = p.classificacao.sla_minutos
    nivel = p.classificacao.nivel
    if nivel_efetivo != nivel:
        prioridade = f"⬆️ {nivel_efetivo} (era {nivel})"
    else:
        prioridade = str(nivel)
    if p.sla_estourado(agora):
        situacao = f"⚠️ Atrasado há {horas_e_minutos(espera - sla)}"
    else:
        situacao = f"✅ No prazo (faltam {horas_e_minutos(sla - espera)})"
    return {
        "Ordem": posicao,
        "Paciente": f"{p.nome} (nº {p.id})",
        "Classificação": rotulo_cor(p.classificacao),
        "Prioridade atual": prioridade,
        "Espera": horas_e_minutos(espera),
        "Situação": situacao,
        "Prazo usado": 100 * espera / sla if sla else (100.0 if espera else 0.0),
        "Chegou às": p.chegada.strftime("%H:%M"),
    }


def tabela_fila() -> None:
    """Fila na ordem de chamada, com destaque para quem foi promovido."""
    sim: SimuladorPlantao = st.session_state.sim
    agora = sim.relogio.agora()
    st.subheader("Fila de atendimento — ordem de chamada")

    pacientes = sim.fila.listar_ordenada(agora)
    if not pacientes:
        st.info("Ninguém aguardando. Avance o relógio para chegarem pacientes.")
        return

    primeiro = pacientes[0]
    st.markdown(
        f"**Próximo a ser chamado:** {primeiro.nome} "
        f"({rotulo_cor(primeiro.classificacao)}), esperando há "
        f"{horas_e_minutos(primeiro.tempo_espera(agora))}."
    )

    niveis = [sim.fila.nivel_efetivo(p, agora) for p in pacientes]
    tabela = pd.DataFrame(
        [
            linha_da_fila(i, p, n, agora)
            for i, (p, n) in enumerate(zip(pacientes, niveis, strict=True), start=1)
        ]
    )
    promovidos = [
        n != p.classificacao.nivel for p, n in zip(pacientes, niveis, strict=True)
    ]
    estilo = tabela.style.apply(
        lambda linha: [COR_DESTAQUE if promovidos[linha.name] else ""] * len(linha),
        axis=1,
    )
    st.dataframe(
        estilo,
        hide_index=True,
        width="stretch",
        height=min(38 + 35 * len(tabela), 460),
        column_config={
            "Ordem": st.column_config.NumberColumn(
                "Ordem",
                help="Posição na fila: 1 é o próximo a ser chamado.",
                width="small",
            ),
            "Prioridade atual": st.column_config.TextColumn(
                help="1 = mais urgente. ⬆️ indica promoção pelo aging."
            ),
            "Prazo usado": st.column_config.ProgressColumn(
                "Prazo usado",
                help="Espera dividida pelo tempo-alvo (SLA) da cor. Acima de 100% "
                "o prazo estourou.",
                min_value=0,
                max_value=100,
                format="%.0f%%",
            ),
        },
    )
    st.caption(
        "Linhas com fundo amarelo e ⬆️ na coluna Prioridade atual: pacientes "
        "promovidos pelo aging. Role a tabela para ver o fim da fila."
    )


def grafico_espera() -> None:
    """Espera do paciente mais antigo de cada cor ao longo do plantão."""
    sim: SimuladorPlantao = st.session_state.sim
    if len(sim.amostras) < 2:
        return
    st.subheader("Há quanto tempo o paciente mais antigo de cada cor espera")
    dados = pd.DataFrame(
        {
            cor.cor: {
                a.instante: a.maior_espera_por_cor[cor] / 60 for a in sim.amostras
            }
            for cor in ClassificacaoRisco
        }
    )
    st.line_chart(
        dados,
        color=[COR_LINHA[c] for c in ClassificacaoRisco],
        x_label="Hora do plantão",
        y_label="Horas de espera",
    )
    st.caption(
        "Uma linha que sobe sem parar indica um paciente que nunca é chamado "
        "(starvation). Com aging, as linhas param de subir."
    )
    # Alternativa em texto ao gráfico, para leitor de tela e para quem não
    # distingue as cores das linhas.
    with st.expander("Ver os dados do gráfico em tabela"):
        tabela = dados.iloc[::6].map(horas_e_minutos_de_horas)
        tabela.index = tabela.index.strftime(FORMATO_HORA)
        st.dataframe(tabela.rename_axis("Hora"), width="stretch")


def horas_e_minutos_de_horas(horas: float) -> str:
    """Formata horas decimais como '9h36' (usado na tabela do gráfico)."""
    return horas_e_minutos(horas * 60)


def tabela_eventos(linhas: list[sqlite3.Row]) -> pd.DataFrame:
    """Linhas de evento_fila (lidas do banco) no formato da tela."""
    return pd.DataFrame(
        [
            {
                "Instante": r["instante"][8:10]
                + "/"
                + r["instante"][5:7]
                + " "
                + r["instante"][11:16],
                "Evento": NOME_EVENTO[r["tipo"]],
                "Paciente": f"{r['nome']} (nº {r['paciente_id']})",
                "Classificação": rotulo_cor_banco(r["cor"]),
                "Nível efetivo": r["nivel_efetivo"],
                "Detalhes": r["detalhes"],
                "Fila após": r["total"],
            }
            for r in linhas
        ]
    )


def ultimos_eventos() -> None:
    """Os eventos mais recentes do plantão, lidos da tabela evento_fila."""
    st.subheader("Últimos acontecimentos")
    linhas = repositorio.eventos(
        conexao(), st.session_state.plantao_id, limite=40, mais_recentes_primeiro=True
    )
    if not linhas:
        st.write("Nada aconteceu ainda. Avance o relógio.")
        return
    st.dataframe(tabela_eventos(linhas), hide_index=True, width="stretch", height=320)
    st.caption(
        "Lido do banco de dados (tabela evento_fila), do mais novo ao mais antigo."
    )


def historico() -> None:
    """Todos os atendimentos do plantão, lidos da tabela atendimento."""
    linhas = repositorio.atendimentos(conexao(), st.session_state.plantao_id)
    with st.expander(f"Todos os atendidos ({len(linhas)})"):
        if not linhas:
            st.write("Nenhum atendimento ainda.")
            return
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Início": r["inicio"][11:16],
                        "Médico": r["medico"],
                        "Paciente": f"{r['nome']} (nº {r['paciente_id']})",
                        "Classificação": rotulo_cor_banco(r["cor"]),
                        "Prioridade no atendimento": r["nivel_efetivo"],
                        "Espera": horas_e_minutos(r["espera_min"]),
                        "Situação": (
                            "✅ No prazo" if r["dentro_do_sla"] else "⚠️ Atrasado"
                        ),
                    }
                    for r in linhas
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def auditoria() -> None:
    """Plantões gravados, trilha de um paciente e exportação do logs.sql."""
    st.subheader("Banco de dados e auditoria")
    caminho = CAMINHO_BANCO.relative_to(RAIZ_PROJETO).as_posix()
    st.markdown(
        f"Tudo é gravado em `{caminho}` (SQLite). O histórico é *append-only*: "
        "o banco recusa alterar ou apagar eventos. Este é o plantão "
        f"**nº {st.session_state.plantao_id}**."
    )

    plantoes = [
        p
        for p in repositorio.listar_plantoes(conexao())
        if p["pacientes"] > 0 or p["id"] == st.session_state.plantao_id
    ]
    st.markdown("**Plantões gravados**")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Plantão": p["id"],
                    "Regra da fila": (
                        "com aging" if p["politica"] == "AGING" else "sem aging"
                    ),
                    "Chegadas/h": p["chegadas_por_hora"],
                    "Médicos": p["medicos"],
                    "Consulta (min)": p["duracao_consulta_min"],
                    "Pacientes": p["pacientes"],
                    "Atendidos": p["atendidos"],
                    "Eventos": p["eventos"],
                }
                for p in plantoes
            ]
        ),
        hide_index=True,
        width="stretch",
        height=min(38 + 35 * len(plantoes), 250),
    )

    col_plantao, col_busca = st.columns([1, 2])
    escolhido = col_plantao.selectbox(
        "Plantão", [p["id"] for p in plantoes], format_func=lambda i: f"nº {i}"
    )
    texto = col_busca.text_input(
        "Buscar paciente por número ou nome", placeholder="ex.: 7 ou Gabriela"
    )
    if texto.strip():
        encontrados = repositorio.buscar_pacientes(conexao(), escolhido, texto)
        if not encontrados:
            st.info("Nenhum paciente encontrado nesse plantão.")
        for p in encontrados[:5]:
            st.markdown(
                f"**{p['nome']} (nº {p['id']})** — {rotulo_cor_banco(p['cor'])}, "
                f"chegou às {p['chegada'][11:16]}"
            )
            trilha = repositorio.eventos(conexao(), escolhido, paciente_id=p["id"])
            st.dataframe(tabela_eventos(trilha), hide_index=True, width="stretch")

    st.download_button(
        f"Exportar logs.sql do plantão nº {escolhido}",
        data=exportar_logs(conexao(), escolhido),
        file_name=f"logs_plantao_{escolhido}.sql",
        mime="application/sql",
        help="Script SQL que recria este plantão num banco vazio criado por "
        "sql/schema.sql.",
    )


# --------------------------------------------------------------------- main
def main() -> None:
    """Monta a página do plantão na ordem de leitura."""
    st.set_page_config(page_title="Triagem — Plantão", layout="wide")
    declarar_idioma()
    config = parametros_plantao()
    if "sim" not in st.session_state:
        iniciar_estado(com_aging=False, config=config)
    barra_lateral(config)

    st.title("Triagem — Plantão")
    explicacao()
    painel_relogio()
    resumo_por_cor()
    tabela_fila()
    grafico_espera()
    ultimos_eventos()
    historico()
    auditoria()


main()
