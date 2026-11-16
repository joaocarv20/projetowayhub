"""
Arquivo: ui/motorista_view.py
Função: painel do motorista — buscar pedidos (filtros e cards estilo BlaBlaCar, com previsão da IA e
        combinações sugeridas) e acompanhar as próprias caronas com os códigos de retirada e entrega.
"""
import html

import streamlit as st

from config.settings import ANTECEDENCIA_MINIMA_MIN, TAXA_MINIMA_CARONA
from ml.previsao import item_de_pedido
from services import logistica
from ui.tema import badge
from utils.helpers import fmt_brl, fmt_dias

H = html.escape


def render(user, previsor):
    aba_buscar, aba_caronas = st.tabs(["🔎 Buscar pedidos", "🚚 Minhas caronas"])
    with aba_buscar:
        _buscar(user, previsor)
    with aba_caronas:
        _minhas_caronas(user)


# ------------------------------------------------------------------ callbacks
def _selecionar(ids):
    for pid in ids:
        st.session_state[f"sel_{pid}"] = True


def _solicitar(motorista_id, ids):
    try:
        carona_id = logistica.solicitar_carona(motorista_id, ids)
        for pid in ids:
            st.session_state[f"sel_{pid}"] = False
        st.session_state["msg_carona"] = ("ok", f"Carona #{carona_id} solicitada! Veja o código de retirada em "
                                                "**Minhas caronas**.")
    except ValueError as e:
        st.session_state["msg_carona"] = ("erro", str(e))


# ------------------------------------------------------------------ buscar
def _card_html(p, horas_ia):
    q = p["retirada_prevista"]
    dims = f'{float(p["altura_cm"]):g} × {float(p["comprimento_cm"]):g} × {float(p["largura_cm"]):g} cm'
    return (
        '<div class="wh-card">'
        f'<div class="wh-when"><b>{q:%H:%M}</b><span>{q:%d/%m}</span></div>'
        '<div class="wh-route">'
        f'<div class="wh-stop"><i class="wh-dot"></i><div><div class="wh-city">{H(p["origem_cidade"])}</div>'
        f'<div class="wh-sub">{H(p["origem_nome"])} · {H(p["origem_bairro"])}</div></div></div>'
        f'<div class="wh-stop"><i class="wh-dot"></i><div><div class="wh-city">{H(p["destino_cidade"])}</div>'
        f'<div class="wh-sub">{H(p["destino_nome"])} · {H(p["destino_bairro"])}</div></div></div>'
        '</div>'
        f'<div class="wh-meta"><span class="wh-pill">{H(p["categoria"])}</span>'
        f'<span class="wh-pill ia">Entrega prevista (IA): {fmt_dias(horas_ia)}</span>'
        f'<span class="wh-sub">{dims} · {float(p["peso_kg"]):g} kg</span>'
        f'<span class="wh-sub">{H(p["descricao"])}</span></div>'
        f'<div class="wh-price">{fmt_brl(p["taxa"])}</div>'
        '</div>'
    )


def _buscar(user, previsor):
    if "msg_carona" in st.session_state:
        tipo, texto = st.session_state.pop("msg_carona")
        (st.success if tipo == "ok" else st.error)(texto)

    cidades = ["Todas"] + logistica.cidades_com_centros()
    with st.container(border=True):
        f1, f2, f3 = st.columns(3)
        origem = f1.selectbox("📍 Saindo de", cidades, key="f_origem")
        destino = f2.selectbox("🏁 Indo para", cidades, key="f_destino")
        data = f3.date_input("📅 Data da retirada", value=None, format="DD/MM/YYYY", key="f_data")

    pedidos = logistica.listar_pedidos_disponiveis(
        None if origem == "Todas" else origem, None if destino == "Todas" else destino, data)

    st.caption(f"Só aparecem pedidos com retirada daqui a {ANTECEDENCIA_MINIMA_MIN} minutos ou mais. "
               f"Cada carona precisa somar no mínimo {fmt_brl(TAXA_MINIMA_CARONA)} em taxas, "
               "com o mesmo centro de origem e de destino.")

    resumo = st.container()
    horas_ia = dict(zip((p["id"] for p in pedidos), previsor.prever_horas([item_de_pedido(p) for p in pedidos])))

    sugestoes = logistica.sugerir_combinacoes(pedidos)
    if sugestoes:
        with st.expander(f"Combinações sugeridas pelo WayHub ({len(sugestoes)})"):
            st.caption("O WayHub encontra o menor número de pedidos que já alcança a taxa mínima na mesma rota.")
            for i, s in enumerate(sugestoes[:5]):
                p0 = s["pedidos"][0]
                a, b = st.columns([4, 1], vertical_alignment="center")
                a.markdown(f"**{p0['origem_cidade']} ({p0['origem_nome']}) → {p0['destino_cidade']} "
                           f"({p0['destino_nome']})** · {len(s['pedidos'])} pedido(s) · **{fmt_brl(s['total'])}**")
                b.button("Selecionar", key=f"sug_{i}", on_click=_selecionar, args=([p["id"] for p in s["pedidos"]],))

    if not pedidos:
        st.info("Nenhum pedido disponível com esses filtros.")

    if pedidos:
        st.markdown(f"**{len(pedidos)} pedido(s) disponível(is)** — marque os que vai levar")
    selecionados = []
    for p in pedidos:
        with st.container(border=True, key=f"pedido_{p['id']}"):
            c1, c2 = st.columns([0.05, 0.95], vertical_alignment="center")
            if c1.checkbox("Selecionar", key=f"sel_{p['id']}", label_visibility="collapsed"):
                selecionados.append(p)
            c2.markdown(_card_html(p, horas_ia[p["id"]]), unsafe_allow_html=True)

    with resumo:
        total = sum(float(p["taxa"]) for p in selecionados)
        with st.container(border=True):
            st.progress(min(total / TAXA_MINIMA_CARONA, 1.0),
                        text=f"{len(selecionados)} pedido(s) · {fmt_brl(total)} de {fmt_brl(TAXA_MINIMA_CARONA)} mínimos".replace("$", r"\$"))
            st.button("Solicitar carona", key="btn_solicitar", disabled=not selecionados, type="primary",
                      on_click=_solicitar, args=(user["id"], [p["id"] for p in selecionados]))


# ------------------------------------------------------------------ minhas caronas
def _minhas_caronas(user):
    caronas = logistica.listar_caronas_motorista(user["id"])
    m1, m2 = st.columns(2)
    m1.metric("Total já recebido (taxas pagas)", fmt_brl(logistica.ganhos_motorista(user["id"])), border=True)
    m2.metric("Caronas ativas", sum(c["status"] in ("solicitada", "em_andamento") for c in caronas), border=True)
    if not caronas:
        st.caption("Você ainda não solicitou nenhuma carona.")
        return

    rotulo = {"solicitada": "Solicitada", "em_andamento": "Em andamento",
              "encerrada": "Encerrada", "cancelada": "Cancelada"}
    for c in caronas:
        with st.container(border=True):
            topo, valor = st.columns([3, 1])
            topo.markdown(
                f'{badge(c["status"], rotulo[c["status"]])} &nbsp; '
                f'**{H(c["origem_cidade"])}** ({H(c["origem_nome"])}, {H(c["origem_bairro"])}) → '
                f'**{H(c["destino_cidade"])}** ({H(c["destino_nome"])}, {H(c["destino_bairro"])})',
                unsafe_allow_html=True)
            valor.markdown(f"### {fmt_brl(c['taxa_total'])}")
            st.caption(f"Retirada prevista: {c['retirada_prevista']:%d/%m às %H:%M}")
            if c["pedidos"]:
                st.write(" · ".join(f"{p['codigo_pedido']} ({p['descricao']})" for p in c["pedidos"]))

            if c["status"] == "solicitada":
                st.markdown(f'<div class="wh-code"><small>CÓDIGO DE RETIRADA — fale ao centro de origem</small>'
                            f'<b>{c["codigo_retirada"]}</b></div>', unsafe_allow_html=True)
                if st.button("Cancelar carona", key=f"cancel_{c['id']}"):
                    try:
                        logistica.cancelar_carona(user["id"], c["id"])
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            elif c["status"] == "em_andamento":
                st.markdown(f'<div class="wh-code"><small>CÓDIGO DE ENTREGA — fale ao centro de destino</small>'
                            f'<b>{c["codigo_entrega"]}</b></div>', unsafe_allow_html=True)
