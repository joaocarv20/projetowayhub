"""
Arquivo: ui/login_view.py
Função: tela inicial com as abas Entrar e Cadastrar (motorista ou centro logístico).
"""
import streamlit as st

from config.settings import CIDADES, OUTRA_CIDADE, TIPOS_VEICULO
from domain.usuarios import CentroLogistico, Motorista, Usuario, Veiculo
from ui.tema import hero


def render():
    hero("WayHub", "A carona de pedidos entre centros logísticos")
    aba_login, aba_cadastro = st.tabs(["Entrar", "Cadastrar"])
    with aba_login:
        _entrar()
    with aba_cadastro:
        _cadastrar()


def _cidade(label, chave):
    escolha = st.selectbox(label, CIDADES + [OUTRA_CIDADE], key=chave)
    if escolha == OUTRA_CIDADE:
        return st.text_input("Digite a cidade (ex.: Goianésia - GO)", key=chave + "_outra").strip()
    return escolha


def _entrar():
    _, centro, _ = st.columns([1, 1.4, 1])
    with centro:
        email = st.text_input("E-mail", key="login_email")
        senha = st.text_input("Senha", type="password", key="login_senha")
        if st.button("Entrar", key="btn_entrar"):
            user = Usuario.autenticar(email, senha)
            if user:
                st.session_state["user"] = user
                st.rerun()
            st.error("E-mail ou senha incorretos.")
        st.caption("Ainda não tem conta? Vá na aba **Cadastrar**.")


def _cadastrar():
    perfil = st.radio("Quero me cadastrar como", ["Motorista", "Centro logístico"],
                      horizontal=True, key="cad_perfil")
    if perfil == "Motorista":
        _cadastro_motorista()
    else:
        _cadastro_centro()


def _mostrar_erros(e):
    for linha in str(e).splitlines():
        st.error(linha)


def _cadastro_motorista():
    st.markdown("#### Dados pessoais")
    c1, c2 = st.columns(2)
    nome = c1.text_input("Nome", key="m_nome")
    sobrenome = c2.text_input("Sobrenome", key="m_sobrenome")
    email = c1.text_input("E-mail", key="m_email")
    telefone = c2.text_input("Telefone (com DDD)", key="m_tel")
    senha = c1.text_input("Senha", type="password", key="m_senha")
    senha2 = c2.text_input("Confirmar senha", type="password", key="m_senha2")
    cidade = _cidade("Cidade de origem", "m_cidade")
    endereco = st.text_input("Endereço de moradia (rua, número, bairro)", key="m_end")

    st.markdown("#### Veículo")
    v1, v2, v3, v4 = st.columns([1.2, 1.5, 1, 0.8])
    tipo = v1.selectbox("Tipo", TIPOS_VEICULO, key="v_tipo")
    modelo = v2.text_input("Marca e modelo", key="v_modelo")
    placa = v3.text_input("Placa", max_chars=8, key="v_placa")
    ano = v4.number_input("Ano", min_value=1980, max_value=2100, value=2020, step=1, key="v_ano")

    if st.button("Criar conta de motorista", key="btn_cad_mot"):
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
    st.markdown("#### Dados do centro logístico")
    c1, c2 = st.columns(2)
    nome = c1.text_input("Nome do centro logístico", key="c_nome")
    cnpj = c2.text_input("CNPJ", key="c_cnpj")
    email = c1.text_input("E-mail", key="c_email")
    telefone = c2.text_input("Telefone (com DDD)", key="c_tel")
    senha = c1.text_input("Senha", type="password", key="c_senha")
    senha2 = c2.text_input("Confirmar senha", type="password", key="c_senha2")

    st.markdown("#### Endereço de origem")
    cidade = _cidade("Cidade", "c_cidade")
    a1, a2, a3 = st.columns([1.2, 1.6, 0.6])
    bairro = a1.text_input("Bairro", key="c_bairro")
    rua = a2.text_input("Rua / Avenida", key="c_rua")
    numero = a3.text_input("Número", key="c_num")

    if st.button("Criar conta do centro logístico", key="btn_cad_centro"):
        if senha != senha2:
            st.error("As senhas não conferem.")
            return
        try:
            CentroLogistico(email, senha, telefone, nome, cnpj, cidade, bairro, rua, numero).cadastrar()
            st.success("Centro logístico cadastrado! Já pode entrar na aba **Entrar**.")
        except ValueError as e:
            _mostrar_erros(e)
