"""
Arquivo: ui/centro_view.py
Função: painel do centro logístico — aba de administração (cadastrar/cancelar pedidos, com previsão da IA)
        e aba de acompanhamento (códigos de retirada/entrega, histórico, status e pagamento).
"""
import html
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from domain.pedidos import Pedido
from ml.previsao import item_de_pedido
from ml.visao import medir_produto, perfil_da_descricao
from services import logistica
from ui.tema import colorir_status, secao
from utils.helpers import STATUS_LABEL, fmt_brl, fmt_dias, fmt_tel

H = html.escape


def render(user, previsor):
    aba_admin, aba_acomp = st.tabs(["📦 Administração de pedidos", "📍 Acompanhamento"])
    with aba_admin:
        _aba_pedidos(user, previsor)
    with aba_acomp:
        _aba_acompanhamento(user, previsor)


# ------------------------------------------------------------------ administração
def _aba_pedidos(user, previsor):
    centro = logistica.obter_centro(user["id"])
    destinos = logistica.listar_centros(user["id"])
    if not destinos:
        st.warning("Ainda não há outro centro logístico cadastrado para ser o destino.")
        return
    opcoes = {f"{d['nome']} — {d['bairro']}, {d['cidade']}": d for d in destinos}

    form, lado = st.columns([1.7, 1], gap="large")
    with form:
        st.markdown("### Novo pedido")
        with st.container(border=True):
            secao("O que vai ser enviado")
            descricao = st.text_input("Descrição do pedido", key="p_desc", placeholder="Ex.: 20 capinhas de celular")
            destino = opcoes[st.selectbox("Para onde vai", list(opcoes), key="p_dest")]

            secao("Tamanho e peso")
            for chave, padrao in (("p_alt", 10.0), ("p_comp", 20.0), ("p_larg", 15.0), ("p_peso", 0.5)):
                st.session_state.setdefault(chave, padrao)
            _medir_por_foto(descricao)
            c1, c2, c3, c4 = st.columns(4)
            altura = c1.number_input("Altura (cm)", min_value=0.1, step=1.0, key="p_alt")
            comprimento = c2.number_input("Compr. (cm)", min_value=0.1, step=1.0, key="p_comp")
            largura = c3.number_input("Largura (cm)", min_value=0.1, step=1.0, key="p_larg")
            peso = c4.number_input("Peso (kg)", min_value=0.01, step=0.1, key="p_peso")

            secao("Quando o motorista pode retirar")
            if "p_data" not in st.session_state:
                st.session_state["p_data"] = date.today()
                st.session_state["p_hora"] = (datetime.now() + timedelta(hours=2)).replace(second=0, microsecond=0).time()
            d1, d2 = st.columns(2)
            data = d1.date_input("Data", min_value=date.today(), key="p_data", format="DD/MM/YYYY")
            hora = d2.time_input("Horário", key="p_hora")
    retirada = datetime.combine(data, hora)

    pedido = Pedido(user["id"], destino["usuario_id"], descricao, altura, comprimento, largura, peso, retirada)
    with lado:
        st.markdown("### Resumo")
        try:
            categoria, taxa = pedido.classificar()
            horas = previsor.prever_horas([{"origem_cidade": centro["cidade"], "destino_cidade": destino["cidade"],
                                            "peso_kg": peso, "altura_cm": altura, "comprimento_cm": comprimento,
                                            "largura_cm": largura, "retirada": retirada}])[0]
            st.markdown(
                '<div class="wh-resumo">'
                f'<small>Sai de</small><b>{H(centro["nome"])}<span>{H(centro["cidade"])}</span></b>'
                f'<small>Vai para</small><b>{H(destino["nome"])}<span>{H(destino["cidade"])}</span></b>'
                f'<small>Tamanho</small><b>{H(categoria)}</b>'
                f'<small>Taxa paga ao motorista</small><b>{fmt_brl(taxa)}</b>'
                f'<small>Previsão de entrega (IA)</small><b>{fmt_dias(horas)}</b>'
                '</div>', unsafe_allow_html=True)
        except ValueError as e:
            st.warning(str(e))
        if st.button("Cadastrar pedido", key="btn_ped", type="primary", width="stretch"):
            try:
                codigo = pedido.salvar()
                st.success(f"Pedido **{codigo}** cadastrado e disponível para os motoristas!")
            except ValueError as e:
                for linha in str(e).splitlines():
                    st.error(linha)

    st.divider()
    _meus_pedidos(user)


def _meus_pedidos(user):
    st.markdown("### Meus pedidos")
    filtro = st.segmented_control("Filtrar por status", ["todos"] + list(STATUS_LABEL), default="todos",
                                  format_func=lambda s: "Todos" if s == "todos" else STATUS_LABEL[s],
                                  key="p_filtro", label_visibility="collapsed") or "todos"
    pedidos = logistica.listar_pedidos_centro(user["id"], None if filtro == "todos" else filtro)
    if not pedidos:
        st.caption("Nenhum pedido por aqui ainda.")
        return
    agora = datetime.now()
    linhas = []
    for p in pedidos:
        status = STATUS_LABEL[p["status"]]
        if p["status"] == "disponivel" and p["retirada_prevista"] < agora:
            status += " (vencido)"
        linhas.append({
            "Código": p["codigo_pedido"], "Descrição": p["descricao"],
            "Destino": p["destino_nome"], "Tamanho": p["categoria"],
            "Retirada": p["retirada_prevista"].strftime("%d/%m %H:%M"), "Taxa": fmt_brl(p["taxa"]), "Status": status,
        })
    ev = st.dataframe(colorir_status(pd.DataFrame(linhas)), hide_index=True, width="stretch",
                      on_select="rerun", selection_mode="single-row", key=f"tab_pedidos_{filtro}")
    if not ev.selection.rows or ev.selection.rows[0] >= len(pedidos):  # a lista pode ter encolhido
        st.caption("Clique em uma linha para ver opções do pedido.")
        return
    p = pedidos[ev.selection.rows[0]]
    if p["status"] != "disponivel":
        st.caption(f"Pedido **{p['codigo_pedido']}** está **{STATUS_LABEL[p['status']]}** — só pedidos "
                   "disponíveis podem ser cancelados.")
        return
    t, b = st.columns([3, 1], vertical_alignment="center")
    t.markdown(f"Pedido **{p['codigo_pedido']}** — {H(p['descricao'])}")
    if b.button("Cancelar este pedido", key="btn_cancel_ped", width="stretch"):
        try:
            logistica.cancelar_pedido(user["id"], p["id"])
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _medir_por_foto(descricao):
    """Visão computacional: mede o produto pela foto e preenche altura/comprimento/largura/peso abaixo."""
    with st.expander("📷 Medir o produto pela foto (visão computacional)"):
        st.caption("Coloque o produto **inteiro sobre uma folha A4 branca**, numa mesa escura, e fotografe "
                   "**de cima** mostrando a folha toda. Para medir a altura, tire a 2ª foto com o produto "
                   "**deitado de lado** na folha (também de cima).")
        produto = st.text_input("Breve descrição do produto (ex.: livro, garrafa de vinho, camiseta)",
                                key="p_foto_desc", placeholder=descricao or None)
        produto = produto.strip() or descricao       # vazio: usa a descrição do pedido
        if produto:
            st.caption(f"Reconhecido como **{perfil_da_descricao(produto)[0]}** — usado para estimar o peso "
                       "(e a altura, se não houver a 2ª foto).")
        f1, f2 = st.columns(2)
        foto_cima = f1.file_uploader("1. Produto em pé, visto de cima", type=["jpg", "jpeg", "png"], key="p_foto")
        foto_lado = f2.file_uploader("2. Produto deitado de lado (opcional)", type=["jpg", "jpeg", "png"],
                                     key="p_foto_lado")
        if foto_cima and st.button("Medir pelas fotos", key="btn_medir", type="primary"):
            try:
                r = medir_produto(foto_cima.getvalue(), produto, foto_lado and foto_lado.getvalue())
            except ValueError as e:
                st.error(str(e))
                return
            st.session_state.update(p_alt=r["altura_cm"], p_comp=r["comprimento_cm"],
                                    p_larg=r["largura_cm"], p_peso=r["peso_kg"])
            for col, img, legenda in zip(st.columns(2), r["imagens"], ["Foto 1: de cima", "Foto 2: deitado"]):
                col.image(img, caption=f"{legenda} (folha endireitada)", width=320)
            origem_altura = "medida na foto 2" if r["altura_medida"] else f"estimada como **{r['perfil']}**"
            st.success(f"{r['comprimento_cm']} × {r['largura_cm']} cm medidos na foto · altura {r['altura_cm']} cm "
                       f"{origem_altura} · peso {r['peso_kg']} kg estimado como **{r['perfil']}** "
                       f"(densidade {r['densidade']} g/cm³, volume {r['volume_cm3']:,} cm³). Ajuste abaixo se precisar.")


# ------------------------------------------------------------------ acompanhamento
def _aba_acompanhamento(user, previsor):
    st.markdown("### Códigos da carona")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**📤 Retirada** — o motorista chegou para buscar pedidos")
        cod_ret = st.text_input("Código de retirada falado pelo motorista", max_chars=6, key="cod_ret",
                                placeholder="6 dígitos")
        if st.button("Iniciar acompanhamento", key="btn_ret", type="primary", width="stretch"):
            try:
                r = logistica.validar_retirada(user["id"], cod_ret)
                st.success(f"Acompanhamento iniciado! Motorista: **{r['motorista']}** · {fmt_tel(r['telefone'])}")
                st.write("Entregue ao motorista: " + ", ".join(
                    f"**{i['codigo_pedido']}** ({i['descricao']})" for i in r["itens"]))
            except ValueError as e:
                st.error(str(e))
    with c2, st.container(border=True):
        st.markdown("**📥 Recebimento** — o motorista chegou com pedidos para este centro")
        cod_ent = st.text_input("Código de entrega falado pelo motorista", max_chars=6, key="cod_ent",
                                placeholder="6 dígitos")
        if st.button("Confirmar entrega", key="btn_ent", type="primary", width="stretch"):
            try:
                r = logistica.validar_entrega(user["id"], cod_ent)
                st.success(f"Entrega confirmada: {r['qtd']} pedido(s) recebido(s). "
                           f"Taxa de {fmt_brl(r['total'])} marcada como paga ao motorista.")
            except ValueError as e:
                st.error(str(e))

    rows = logistica.acompanhamento_centro(user["id"])
    chegando = logistica.a_receber_centro(user["id"])
    st.write("")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Solicitados", sum(r["status"] == "solicitado" for r in rows), border=True)
    m2.metric("Em andamento", sum(r["status"] == "em_andamento" for r in rows), border=True)
    m3.metric("Encerrados", sum(r["status"] == "encerrado" for r in rows), border=True)
    m4.metric("A caminho daqui", len(chegando), border=True)

    if chegando:
        st.markdown("### A caminho deste centro")
        st.dataframe(pd.DataFrame([{
            "Código": p["codigo_pedido"], "Descrição": p["descricao"],
            "Origem": f"{p['origem_cidade']} · {p['origem_nome']}",
            "Saiu às": p["retirado_em"].strftime("%d/%m %H:%M")} for p in chegando]),
            hide_index=True, width="stretch")

    st.markdown("### Pedidos enviados")
    if not rows:
        st.caption("Quando um motorista solicitar um pedido seu, ele aparece aqui como **Solicitado**.")
        return
    previsoes = previsor.prever_horas([item_de_pedido(r) for r in rows])
    linhas = [{
        "Código": r["codigo_pedido"], "Descrição": r["descricao"],
        "Rota": f"{r['origem_cidade']} → {r['destino_cidade']}",
        "Retirada": r["retirado_em"].strftime("%d/%m %H:%M") if r["retirado_em"] else "aguardando",
        "Previsão IA": "—" if r["status"] == "encerrado" else fmt_dias(h),
        "Motorista": f"{r['mot_nome']} {r['mot_sobrenome']}",
        "Pagamento": "Pago" if r["pago"] else "Pendente", "Status": STATUS_LABEL[r["status"]],
    } for r, h in zip(rows, previsoes)]
    ev = st.dataframe(colorir_status(pd.DataFrame(linhas)), hide_index=True, width="stretch",
                      on_select="rerun", selection_mode="single-row", key="tab_acomp")
    if not ev.selection.rows or ev.selection.rows[0] >= len(rows):
        st.caption("Clique em uma linha para ver os detalhes do pedido.")
        return
    i = ev.selection.rows[0]
    r = rows[i]
    with st.container(border=True):
        st.markdown(f"**{r['codigo_pedido']}** — {H(r['descricao'])}")
        d1, d2, d3 = st.columns(3)
        d1.markdown(f"**De:** {H(r['origem_cidade'])} ({H(r['origem_bairro'])})  \n"
                    f"**Para:** {H(r['destino_nome'])} — {H(r['destino_bairro'])}, {H(r['destino_cidade'])}")
        d2.markdown(f"**Motorista:** {H(linhas[i]['Motorista'])}  \n**Telefone:** {fmt_tel(r['mot_tel'])}")
        d3.markdown(f"**Taxa:** {fmt_brl(r['taxa'])} ({linhas[i]['Pagamento'].lower()})  \n"
                    f"**Tempo médio da rota:** {fmt_dias(logistica.tempo_medio_rota(r['centro_origem_id'], r['centro_destino_id']))}  \n"
                    f"**Previsão da IA:** {fmt_dias(previsoes[i])}")
