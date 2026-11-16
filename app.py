"""
Arquivo: app.py
Função: ponto de entrada do WayHub. Conecta ao banco, treina a IA ao iniciar e mostra a tela
        certa para cada perfil (login, centro logístico ou motorista).  Rode:  streamlit run app.py
"""
import html

import streamlit as st

from ml.preparacao_dados import versao_dados
from ml.previsao import PrevisorEntrega
from services import logistica
from ui import centro_view, login_view, motorista_view
from ui.tema import aplicar_css, marca

st.set_page_config(page_title="WayHub", page_icon="🚚", layout="wide", initial_sidebar_state="collapsed")
aplicar_css()

try:
    logistica.liberar_expirados()      # também testa a conexão com o MySQL
except Exception as erro:
    marca()
    st.error("Não consegui conectar ao banco de dados MySQL.")
    st.info("Confira: 1) o MySQL está rodando; 2) você executou o database/schema.sql no Workbench; "
            "3) usuário e senha no arquivo .env.")
    st.code(str(erro))
    st.stop()


@st.cache_resource(max_entries=1, show_spinner="A IA do WayHub está aprendendo com as novas entregas...")
def carregar_previsor(versao):
    """Aprendizado contínuo: cada entrega encerrada vira um exemplo de treino (tempo real = rótulo).
    Quando a base muda (versao), o cache expira e a IA se retreina sozinha — sem botão, sem intervenção."""
    return PrevisorEntrega.treinar_agora()


previsor = carregar_previsor(versao_dados())
usuario = st.session_state.get("user")

if not usuario:
    with st.container(key="wh_topo"):
        marca()
    login_view.render()
    st.stop()

centro = usuario["tipo"] == "centro"
with st.container(key="wh_topo"):
    c1, c2, c3, c4 = st.columns([2.2, 2.4, 1.6, 0.6], vertical_alignment="center")
    with c1:
        marca("Painel do centro logístico" if centro else "Pedidos na sua rota, dinheiro no seu bolso")
    c2.markdown(f'<div class="wh-ia">🧠 {html.escape(previsor.resumo())}</div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="wh-user"><b>{html.escape(usuario["nome"])}</b><br>'
                f'<span>{"Centro logístico" if centro else "Motorista"}</span></div>', unsafe_allow_html=True)
    if c4.button("Sair"):
        st.session_state.pop("user", None)
        st.rerun()

(centro_view if centro else motorista_view).render(usuario, previsor)
