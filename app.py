"""
Arquivo: app.py
Função: ponto de entrada do WayHub. Conecta ao banco, treina a IA ao iniciar e mostra a tela
        certa para cada perfil (login, centro logístico ou motorista).  Rode:  streamlit run app.py
"""
import streamlit as st

from ml.preparacao_dados import versao_dados
from ml.previsao import PrevisorEntrega
from services import logistica
from ui import centro_view, login_view, motorista_view
from ui.tema import aplicar_css, hero

st.set_page_config(page_title="WayHub", layout="wide")
aplicar_css()

try:
    logistica.liberar_expirados()      # também testa a conexão com o MySQL
except Exception as erro:
    hero()
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
    login_view.render()
else:
    with st.sidebar:
        st.markdown(f"### Olá, {usuario['nome']}")
        st.caption("Motorista" if usuario["tipo"] == "motorista" else "Centro logístico")
        st.caption(previsor.resumo())
        if st.button("Sair"):
            st.session_state.pop("user", None)
            st.rerun()

    if usuario["tipo"] == "centro":
        hero("WayHub", "Painel do centro logístico")
        centro_view.render(usuario, previsor)
    else:
        hero("WayHub", "Encontre pedidos na sua rota e ganhe com cada carona")
        motorista_view.render(usuario, previsor)
