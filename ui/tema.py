"""
Arquivo: ui/tema.py
Função: visual do WayHub (verde #00A862, texto petróleo #16352B, cards arredondados), o cabeçalho de topo
        usado em todas as telas e o selo colorido de status.
"""
import html

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea { font-family: 'Inter', sans-serif !important; }
footer, #MainMenu, [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 1.2rem; max-width: 1180px; }
h3 { font-size: 1.25rem !important; }

/* ---------- cabeçalho ---------- */
.st-key-wh_topo { border-bottom: 1px solid #DDE7E1; padding-bottom: 12px; margin-bottom: 6px; }
.wh-brand { display: flex; align-items: center; gap: 12px; }
.wh-logo { width: 42px; height: 42px; border-radius: 12px; background: #00A862; color: #fff; flex: none;
           display: grid; place-items: center; font-weight: 800; font-size: 1.25rem; }
.wh-brand b { display: block; font-size: 1.3rem; color: #16352B; letter-spacing: -.4px; line-height: 1.1; }
.wh-brand span { color: #5F7A6E; font-size: .88rem; }
.wh-ia { background: #EEF6F1; color: #16352B; border-radius: 10px; padding: 6px 12px; font-size: .78rem; }
.wh-user { text-align: right; line-height: 1.25; }
.wh-user b { color: #16352B; } .wh-user span { color: #5F7A6E; font-size: .82rem; }

/* ---------- abas, botões e campos ---------- */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 2px solid #DDE7E1; }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: 10px 18px; }
.stTabs [aria-selected="true"] { color: #00A862 !important; }
.stButton > button { border-radius: 8px; font-weight: 600; }
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="textarea"] > div { border-radius: 10px !important; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; background: #fff; }
.wh-section { font-size: .78rem; font-weight: 700; letter-spacing: .6px; color: #5F7A6E;
              text-transform: uppercase; margin: 4px 0 -4px; }

/* ---------- login ---------- */
.wh-pitch { background: #16352B; color: #fff; border-radius: 16px; padding: 32px 30px; }
.wh-pitch h2 { color: #fff; font-size: 1.7rem; line-height: 1.2; margin: 0 0 8px; }
.wh-pitch p { opacity: .85; margin: 0 0 22px; }
.wh-step { display: flex; gap: 14px; margin-bottom: 16px; align-items: flex-start; }
.wh-step i { font-style: normal; width: 30px; height: 30px; border-radius: 50%; background: #00A862; flex: none;
             display: grid; place-items: center; font-weight: 800; }
.wh-step b { display: block; } .wh-step span { opacity: .8; font-size: .9rem; }

/* ---------- resumo do pedido (centro) ---------- */
.wh-resumo { background: #16352B; color: #fff; border-radius: 14px; padding: 20px 22px; margin-bottom: 12px; }
.wh-resumo small { display: block; opacity: .75; font-size: .76rem; text-transform: uppercase; letter-spacing: .5px; }
.wh-resumo b { display: block; font-size: 1.35rem; margin: 2px 0 12px; }
.wh-resumo b:last-child { margin-bottom: 0; }
.wh-resumo b span { display: block; font-size: .85rem; font-weight: 500; opacity: .75; }

/* ---------- card de pedido (motorista) ---------- */
div[class*="st-key-pedido_"] { transition: border-color .15s, background .15s; }
div[class*="st-key-pedido_"]:has(input[type="checkbox"]:checked) { border-color: #00A862 !important; background: #F2FBF6; }
.wh-card { display: flex; gap: 24px; align-items: center; justify-content: space-between; }
.wh-when { display: flex; flex-direction: column; min-width: 56px; color: #16352B; }
.wh-when b { font-size: 1.15rem; }
.wh-when span { font-size: .82rem; color: #5F7A6E; }
.wh-route { flex: 1.5; }
.wh-stop { display: flex; gap: 12px; position: relative; padding-bottom: 14px; }
.wh-stop:last-child { padding-bottom: 0; }
.wh-stop:not(:last-child)::before { content: ""; position: absolute; left: 6px; top: 20px; bottom: 2px;
                                    width: 2px; background: #16352B; }
.wh-dot { width: 14px; height: 14px; border: 3px solid #16352B; border-radius: 50%; background: #fff;
          margin-top: 4px; flex: none; box-sizing: border-box; }
.wh-city { font-weight: 700; color: #16352B; font-size: 1.02rem; }
.wh-sub { color: #5F7A6E; font-size: .84rem; }
.wh-meta { flex: 1.3; display: flex; flex-direction: column; gap: 5px; align-items: flex-start; }
.wh-pill { background: #E4F4EB; color: #007A47; font-weight: 700; font-size: .78rem; padding: 3px 12px;
           border-radius: 999px; white-space: nowrap; }
.wh-pill.ia { background: #EEF1EF; color: #16352B; font-weight: 600; }
.wh-price { font-weight: 800; font-size: 1.5rem; color: #16352B; white-space: nowrap; }

.wh-code { background: #16352B; color: #fff; border-radius: 16px; padding: 14px 20px; text-align: center; }
.wh-code small { display: block; opacity: .8; font-size: .78rem; }
.wh-code b { font-size: 2.1rem; letter-spacing: 8px; }

.wh-badge { display: inline-block; padding: 3px 12px; border-radius: 999px; font-weight: 700; font-size: .78rem; }
.wh-badge.solicitada, .wh-badge.solicitado { background: #FFF4D6; color: #9A6B00; }
.wh-badge.em_andamento { background: #E1EEFB; color: #1F5FA8; }
.wh-badge.encerrada, .wh-badge.encerrado { background: #DDF5E6; color: #1B7F46; }
.wh-badge.cancelada, .wh-badge.cancelado { background: #ECEFF1; color: #607D8B; }
.wh-badge.disponivel { background: #E4F4EB; color: #007A47; }

@media (max-width: 760px) { .wh-card { flex-direction: column; align-items: flex-start; }
                            .wh-user { text-align: left; } }
</style>
"""

# Cores do status nas tabelas (mesmas dos selos .wh-badge)
CORES_STATUS = {
    "Disponível": ("#E4F4EB", "#007A47"), "Solicitado": ("#FFF4D6", "#9A6B00"),
    "Em andamento": ("#E1EEFB", "#1F5FA8"), "Encerrado": ("#DDF5E6", "#1B7F46"),
    "Cancelado": ("#ECEFF1", "#607D8B"),
}


def aplicar_css():
    st.markdown(CSS, unsafe_allow_html=True)


def marca(subtitulo="Caronas de pedidos entre centros logísticos"):
    st.markdown(f'<div class="wh-brand"><div class="wh-logo">W</div>'
                f'<div><b>WayHub</b><span>{html.escape(subtitulo)}</span></div></div>', unsafe_allow_html=True)


def secao(titulo):
    """Título pequeno em caixa alta que separa blocos de um formulário."""
    st.markdown(f'<div class="wh-section">{html.escape(titulo)}</div>', unsafe_allow_html=True)


def badge(status, texto):
    return f'<span class="wh-badge {status}">{html.escape(texto)}</span>'


def colorir_status(df, coluna="Status"):
    """Tabela com a coluna de status colorida (para st.dataframe)."""
    def cor(valor):
        fundo, texto = next((c for k, c in CORES_STATUS.items() if str(valor).startswith(k)), ("", ""))
        return f"background-color: {fundo}; color: {texto}; font-weight: 600" if fundo else ""
    return df.style.map(cor, subset=[coluna])
