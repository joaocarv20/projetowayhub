"""
Arquivo: ui/tema.py
Função: visual do WayHub estilo BlaBlaCar (azul #00A862, texto petróleo #16352B, cards arredondados)
        e o banner de topo (hero) usado em todas as telas.
"""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea { font-family: 'Inter', sans-serif !important; }
footer, #MainMenu { visibility: hidden; }
.block-container { padding-top: 1.6rem; max-width: 1180px; }

.wh-hero { background: #00A862; color: #fff;
           padding: 20px 28px; border-radius: 14px; margin-bottom: 18px; }
.wh-hero h1 { color: #fff; margin: 0; font-size: 1.7rem; font-weight: 700; letter-spacing: -0.5px; }
.wh-hero p { margin: 4px 0 0; opacity: .92; font-size: 1.02rem; }

.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 2px solid #DDE7E1; }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: 10px 18px; border-radius: 12px 12px 0 0; }
.stTabs [aria-selected="true"] { color: #00A862 !important; }

.stButton > button, .stDownloadButton > button { border-radius: 8px; font-weight: 600; padding: .5rem 1.4rem; border: 0;
        background: #00A862; color: #fff; }
.stButton > button:hover { background: #008F54; color: #fff; }
.stButton > button:disabled { background: #C5D3CB; color: #fff; }

div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="textarea"] > div { border-radius: 14px !important; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; background: #fff; }

.wh-card { background: #fff; border-radius: 12px; padding: 18px 24px; margin: 4px 0;
           box-shadow: 0 2px 10px rgba(22,53,43,.07); border: 1px solid #E3EBE6;
           display: flex; gap: 24px; align-items: center; justify-content: space-between; }
.wh-when { display: flex; flex-direction: column; min-width: 56px; color: #16352B; }
.wh-when b { font-size: 1.15rem; }
.wh-when span { font-size: .82rem; color: #5F7A6E; }
.wh-route { flex: 1.6; }
.wh-stop { display: flex; gap: 12px; position: relative; padding-bottom: 14px; }
.wh-stop:last-child { padding-bottom: 0; }
.wh-stop:not(:last-child)::before { content: ""; position: absolute; left: 6px; top: 20px; bottom: 2px;
                                    width: 2px; background: #16352B; }
.wh-dot { width: 14px; height: 14px; border: 3px solid #16352B; border-radius: 50%; background: #fff;
          margin-top: 4px; flex: none; box-sizing: border-box; }
.wh-city { font-weight: 700; color: #16352B; font-size: 1.02rem; }
.wh-sub { color: #5F7A6E; font-size: .84rem; }
.wh-meta { flex: 1; display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
.wh-pill { background: #E4F4EB; color: #007A47; font-weight: 700; font-size: .78rem; padding: 3px 12px; border-radius: 999px; }
.wh-pill.ia { background: #EEF1EF; color: #16352B; }
.wh-price { font-weight: 800; font-size: 1.5rem; color: #16352B; white-space: nowrap; }

.wh-code { background: #16352B; color: #fff; border-radius: 16px; padding: 14px 20px; text-align: center; }
.wh-code small { display: block; opacity: .8; font-size: .78rem; }
.wh-code b { font-size: 2.1rem; letter-spacing: 8px; }

.wh-badge { display: inline-block; padding: 3px 12px; border-radius: 999px; font-weight: 700; font-size: .78rem; }
.wh-badge.solicitada { background: #FFF4D6; color: #9A6B00; }
.wh-badge.em_andamento { background: #E4F4EB; color: #007A47; }
.wh-badge.encerrada { background: #DDF5E6; color: #1B7F46; }
.wh-badge.cancelada { background: #ECEFF1; color: #607D8B; }

@media (max-width: 760px) { .wh-card { flex-direction: column; align-items: flex-start; } }
</style>
"""


def aplicar_css():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(titulo="WayHub", subtitulo="Caronas de pedidos entre centros logísticos"):
    st.markdown(f'<div class="wh-hero"><h1>{titulo}</h1><p>{subtitulo}</p></div>', unsafe_allow_html=True)
