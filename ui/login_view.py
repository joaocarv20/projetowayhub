"""
Arquivo: ui/login_view.py
Função: tela inicial — apresentação do WayHub à esquerda e, à direita, as abas Entrar e Criar conta
        (motorista ou centro logístico).
"""
import streamlit as st

from config.settings import CIDADES, OUTRA_CIDADE, TIPOS_VEICULO
from domain.usuarios import CentroLogistico, Motorista, Usuario, Veiculo
from ui.tema import secao

PITCH = """
<div class="wh-pitch">
  <h2>A carona de pedidos entre centros logísticos</h2>
  <p>Motoristas que já vão fazer a viagem levam pedidos de um centro para outro e ganham por isso.</p>
  <div class="wh-step"><i>1</i><div><b>O centro cadastra o pedido</b>
    <span>A IA prevê o prazo de entrega e o sistema calcula a taxa.</span></div></div>
  <div class="wh-step"><i>2</i><div><b>O motorista pega carona</b>
    <span>Escolhe pedidos na sua rota e recebe um código de retirada.</span></div></div>
  <div class="wh-step"><i>3</i><div><b>A entrega é confirmada por código</b>
    <span>O centro de destino confirma e a taxa é paga ao motorista.</span></div></div>
</div>
"""


def render():
    st.write("")
    esq, dir_ = st.columns([1, 1.25], gap="large")
    esq.markdown(PITCH, unsafe_allow_html=True)
    with dir_, st.container(border=True):
        aba_login, aba_cadastro = st.tabs(["Entrar", "Criar conta"])
        with aba_login:
            _entrar()
        with aba_cadastro:
            _cadastrar()


def _cidade(label, chave, alvo=st):
    escolha = alvo.selectbox(label, CIDADES + [OUTRA_CIDADE], key=chave)
    if escolha == OUTRA_CIDADE:
        return alvo.text_input("Digite a cidade (ex.: Goianésia - GO)", key=chave + "_outra").strip()
    return escolha


def _entrar():
    with st.form("form_login", border=False):
        email = st.text_input("E-mail", key="login_email", placeholder="voce@empresa.com")
        senha = st.text_input("Senha", type="password", key="login_senha")
        if st.form_submit_button("Entrar", type="primary", width="stretch"):
            user = Usuario.autenticar(email, senha)
            if user:
                st.session_state["user"] = user
                st.rerun()
            st.error("E-mail ou senha incorretos.")
    st.caption("Ainda não tem conta? Vá na aba **Criar conta**.")


def _cadastrar():
    perfil = st.segmented_control("Quero me cadastrar como", ["Motorista", "Centro logístico"],
                                  default="Motorista", key="cad_perfil", width="stretch")
    if perfil == "Centro logístico":
        _cadastro_centro()
    else:
        _cadastro_motorista()


def _mostrar_erros(e):
    for linha in str(e).splitlines():
        st.error(linha)


def _cadastro_motorista():
    secao("Dados pessoais")
    c1, c2 = st.columns(2)
    nome = c1.text_input("Nome", key="m_nome")
    sobrenome = c2.text_input("Sobrenome", key="m_sobrenome")
    email = c1.text_input("E-mail", key="m_email")
    telefone = c2.text_input("Telefone (com DDD)", key="m_tel", placeholder="(62) 99999-0000")
    senha = c1.text_input("Senha", type="password", key="m_senha")
    senha2 = c2.text_input("Confirmar senha", type="password", key="m_senha2")
    cidade = _cidade("Cidade de origem", "m_cidade", c1)
    endereco = c2.text_input("Endereço (rua, número, bairro)", key="m_end")

    secao("Veículo")
    v1, v2 = st.columns(2)
    tipo = v1.selectbox("Tipo", TIPOS_VEICULO, key="v_tipo")
    modelo = v2.text_input("Marca e modelo", key="v_modelo", placeholder="Fiat Strada")
    placa = v1.text_input("Placa", max_chars=8, key="v_placa", placeholder="ABC1D23")
    ano = v2.number_input("Ano", min_value=1980, max_value=2100, value=2020, step=1, key="v_ano")

    if st.button("Criar conta de motorista", key="btn_cad_mot", type="primary", width="stretch"):
        if senha != senha2:
            st.error("As senhas não conferem.")
            return
        try:
            Motorista(email, senha, telefone, nome, sobrenome, cidade, endereco,
                      Veiculo(tipo, modelo, placa, ano)).cadastrar()
            st.success("Cadastro concluído! Já pode entrar na aba **Entrar**.")
        except ValueError as e:
            _mostrar_erros(e)


def _cadastro_centro():
    secao("Dados do centro logístico")
    c1, c2 = st.columns(2)
    nome = c1.text_input("Nome do centro logístico", key="c_nome")
    cnpj = c2.text_input("CNPJ", key="c_cnpj", placeholder="00.000.000/0000-00")
    email = c1.text_input("E-mail", key="c_email")
    telefone = c2.text_input("Telefone (com DDD)", key="c_tel", placeholder="(62) 3333-0000")
    senha = c1.text_input("Senha", type="password", key="c_senha")
    senha2 = c2.text_input("Confirmar senha", type="password", key="c_senha2")

    secao("Endereço de origem")
    a1, a2 = st.columns(2)
    cidade = _cidade("Cidade", "c_cidade", a1)
    bairro = a2.text_input("Bairro", key="c_bairro")
    b1, b2 = st.columns([3, 1])
    rua = b1.text_input("Rua / Avenida", key="c_rua")
    numero = b2.text_input("Número", key="c_num")

    if st.button("Criar conta do centro logístico", key="btn_cad_centro", type="primary", width="stretch"):
        if senha != senha2:
            st.error("As senhas não conferem.")
            return
        try:
            CentroLogistico(email, senha, telefone, nome, cnpj, cidade, bairro, rua, numero).cadastrar()
            st.success("Centro logístico cadastrado! Já pode entrar na aba **Entrar**.")
        except ValueError as e:
            _mostrar_erros(e)
