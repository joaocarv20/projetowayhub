"""
Arquivo: services/logistica.py
Função: regras de negócio do WayHub — listar/cancelar pedidos, solicitar carona (mínimo R$ 5 e 40 min),
        códigos de retirada e entrega, status, pagamento, expiração, tempo médio e sugestão de combinações.
"""
import secrets
from collections import defaultdict
from datetime import datetime, timedelta

from config.settings import ANTECEDENCIA_MINIMA_MIN, TAXA_MINIMA_CARONA, TOLERANCIA_ATRASO_MIN
from database.connection import query, transaction
from utils.helpers import somente_digitos

_SELECT_PEDIDO = """
SELECT p.*, o.nome AS origem_nome, o.cidade AS origem_cidade, o.bairro AS origem_bairro,
       d.nome AS destino_nome, d.cidade AS destino_cidade, d.bairro AS destino_bairro
FROM pedidos p
JOIN centros o ON o.usuario_id = p.centro_origem_id
JOIN centros d ON d.usuario_id = p.centro_destino_id
"""


def _gerar_codigo(cur, coluna):
    while True:
        codigo = f"{secrets.randbelow(10**6):06d}"
        cur.execute(f"SELECT 1 FROM caronas WHERE {coluna}=%s AND status IN ('solicitada','em_andamento')", (codigo,))
        if not cur.fetchone():
            return codigo


# ---------------------------------------------------------------- consultas
def obter_centro(centro_id):
    return query("SELECT * FROM centros WHERE usuario_id=%s", (centro_id,), one=True)


def listar_centros(excluir_id=None):
    return query("SELECT * FROM centros WHERE usuario_id <> %s ORDER BY cidade, nome", (excluir_id or 0,))


def cidades_com_centros():
    return [r["cidade"] for r in query("SELECT DISTINCT cidade FROM centros ORDER BY cidade")]


def listar_pedidos_disponiveis(origem_cidade=None, destino_cidade=None, data=None):
    """Só aparecem pedidos cuja retirada é daqui a 40 min ou mais."""
    minimo = datetime.now() + timedelta(minutes=ANTECEDENCIA_MINIMA_MIN)
    sql = _SELECT_PEDIDO + " WHERE p.status='disponivel' AND p.retirada_prevista >= %s"
    params = [minimo]
    if origem_cidade:
        sql += " AND o.cidade=%s"
        params.append(origem_cidade)
    if destino_cidade:
        sql += " AND d.cidade=%s"
        params.append(destino_cidade)
    if data:
        sql += " AND DATE(p.retirada_prevista)=%s"
        params.append(data)
    return query(sql + " ORDER BY p.retirada_prevista, p.id", params)


def listar_pedidos_centro(centro_id, status=None):
    sql = _SELECT_PEDIDO + " WHERE p.centro_origem_id=%s"
    params = [centro_id]
    if status:
        sql += " AND p.status=%s"
        params.append(status)
    return query(sql + " ORDER BY p.id DESC", params)


def cancelar_pedido(centro_id, pedido_id):
    with transaction() as cur:
        cur.execute("UPDATE pedidos SET status='cancelado' "
                    "WHERE id=%s AND centro_origem_id=%s AND status='disponivel'", (pedido_id, centro_id))
        if cur.rowcount == 0:
            raise ValueError("Só é possível cancelar pedidos que ainda estão disponíveis.")


def tempo_medio_rota(origem_id, destino_id):
    """Média histórica em HORAS (retirada -> entrega). Usa o par de centros; sem histórico, o par de cidades."""
    r = query("""SELECT AVG(TIMESTAMPDIFF(MINUTE, retirado_em, entregue_em)) / 60 AS h FROM pedidos
                 WHERE status='encerrado' AND centro_origem_id=%s AND centro_destino_id=%s""",
              (origem_id, destino_id), one=True)
    if r and r["h"] is not None:
        return float(r["h"])
    r = query("""SELECT AVG(TIMESTAMPDIFF(MINUTE, p.retirado_em, p.entregue_em)) / 60 AS h
                 FROM pedidos p
                 JOIN centros o ON o.usuario_id = p.centro_origem_id
                 JOIN centros d ON d.usuario_id = p.centro_destino_id
                 WHERE p.status='encerrado'
                   AND o.cidade = (SELECT cidade FROM centros WHERE usuario_id=%s)
                   AND d.cidade = (SELECT cidade FROM centros WHERE usuario_id=%s)""",
              (origem_id, destino_id), one=True)
    return float(r["h"]) if r and r["h"] is not None else None


# ---------------------------------------------------------------- caronas
def solicitar_carona(motorista_id, pedido_ids):
    if not pedido_ids:
        raise ValueError("Selecione ao menos um pedido.")
    veic = query("SELECT id FROM veiculos WHERE motorista_id=%s", (motorista_id,), one=True)
    marcas = ",".join(["%s"] * len(pedido_ids))
    with transaction() as cur:
        cur.execute(f"SELECT * FROM pedidos WHERE id IN ({marcas}) FOR UPDATE", list(pedido_ids))
        pedidos = cur.fetchall()
        if len(pedidos) != len(pedido_ids) or any(p["status"] != "disponivel" for p in pedidos):
            raise ValueError("Algum pedido não está mais disponível. Atualize a lista.")
        if len({p["centro_origem_id"] for p in pedidos}) > 1 or len({p["centro_destino_id"] for p in pedidos}) > 1:
            raise ValueError("Todos os pedidos da carona precisam ter o mesmo centro de origem "
                             "e o mesmo centro de destino.")
        total = round(sum(float(p["taxa"]) for p in pedidos), 2)
        if total < TAXA_MINIMA_CARONA:
            raise ValueError(f"A carona precisa somar no mínimo R$ {TAXA_MINIMA_CARONA:.2f} em taxas "
                             f"(selecionado: R$ {total:.2f}).")
        primeira = min(p["retirada_prevista"] for p in pedidos)
        agora = datetime.now()
        if primeira - agora < timedelta(minutes=ANTECEDENCIA_MINIMA_MIN):
            raise ValueError(f"A solicitação precisa ser feita com pelo menos {ANTECEDENCIA_MINIMA_MIN} "
                             "minutos de antecedência da retirada.")
        cur.execute(
            """INSERT INTO caronas (motorista_id, veiculo_id, centro_origem_id, centro_destino_id,
                                    codigo_retirada, taxa_total, retirada_prevista, solicitada_em)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (motorista_id, veic["id"], pedidos[0]["centro_origem_id"], pedidos[0]["centro_destino_id"],
             _gerar_codigo(cur, "codigo_retirada"), total, primeira, agora))
        carona_id = cur.lastrowid
        cur.execute(f"UPDATE pedidos SET status='solicitado', carona_id=%s WHERE id IN ({marcas})",
                    [carona_id] + list(pedido_ids))
    return carona_id


def cancelar_carona(motorista_id, carona_id):
    with transaction() as cur:
        cur.execute("UPDATE caronas SET status='cancelada' "
                    "WHERE id=%s AND motorista_id=%s AND status='solicitada'", (carona_id, motorista_id))
        if cur.rowcount == 0:
            raise ValueError("Só é possível cancelar caronas que ainda não foram retiradas.")
        cur.execute("UPDATE pedidos SET status='disponivel', carona_id=NULL WHERE carona_id=%s", (carona_id,))


def liberar_expirados():
    """Carona solicitada e não retirada (retirada prevista + tolerância) volta a ficar disponível."""
    limite = datetime.now() - timedelta(minutes=TOLERANCIA_ATRASO_MIN)
    with transaction() as cur:
        cur.execute("SELECT id FROM caronas WHERE status='solicitada' AND retirada_prevista < %s", (limite,))
        for c in cur.fetchall():
            cur.execute("UPDATE pedidos SET status='disponivel', carona_id=NULL "
                        "WHERE carona_id=%s AND status='solicitado'", (c["id"],))
            cur.execute("UPDATE caronas SET status='cancelada' WHERE id=%s", (c["id"],))


def listar_caronas_motorista(motorista_id):
    caronas = query(
        """SELECT c.*, o.nome AS origem_nome, o.cidade AS origem_cidade, o.bairro AS origem_bairro,
                  d.nome AS destino_nome, d.cidade AS destino_cidade, d.bairro AS destino_bairro
           FROM caronas c
           JOIN centros o ON o.usuario_id = c.centro_origem_id
           JOIN centros d ON d.usuario_id = c.centro_destino_id
           WHERE c.motorista_id=%s ORDER BY c.solicitada_em DESC""", (motorista_id,))
    for c in caronas:
        c["pedidos"] = query("SELECT codigo_pedido, descricao, categoria, taxa FROM pedidos WHERE carona_id=%s",
                             (c["id"],))
    return caronas


def ganhos_motorista(motorista_id):
    r = query("SELECT COALESCE(SUM(taxa_total),0) AS t FROM caronas WHERE motorista_id=%s AND status='encerrada'",
              (motorista_id,), one=True)
    return float(r["t"])


def sugerir_combinacoes(pedidos, minimo=TAXA_MINIMA_CARONA):
    """Por rota (centro A -> centro B), escolhe o MENOR número de pedidos que já atinge a taxa mínima."""
    rotas = defaultdict(list)
    for p in pedidos:
        rotas[(p["centro_origem_id"], p["centro_destino_id"])].append(p)
    sugestoes = []
    for lista in rotas.values():
        total, escolhidos = 0.0, []
        for p in sorted(lista, key=lambda x: -float(x["taxa"])):
            escolhidos.append(p)
            total += float(p["taxa"])
            if total >= minimo:
                break
        if total >= minimo:
            sugestoes.append({"pedidos": escolhidos, "total": total})
    sugestoes.sort(key=lambda s: (len(s["pedidos"]), -s["total"]))
    return sugestoes


# ---------------------------------------------------------------- acompanhamento (centro)
def validar_retirada(centro_id, codigo):
    """O motorista diz o código ao centro de origem -> começa o acompanhamento e nasce o código de entrega."""
    codigo = somente_digitos(codigo)
    with transaction() as cur:
        cur.execute("SELECT * FROM caronas WHERE centro_origem_id=%s AND codigo_retirada=%s "
                    "AND status='solicitada' FOR UPDATE", (centro_id, codigo))
        c = cur.fetchone()
        if not c:
            raise ValueError("Código inválido, já utilizado ou de outro centro.")
        agora = datetime.now()
        cur.execute("UPDATE caronas SET status='em_andamento', retirada_em=%s, codigo_entrega=%s WHERE id=%s",
                    (agora, _gerar_codigo(cur, "codigo_entrega"), c["id"]))
        cur.execute("UPDATE pedidos SET status='em_andamento', retirado_em=%s "
                    "WHERE carona_id=%s AND status='solicitado'", (agora, c["id"]))
        cur.execute("SELECT codigo_pedido, descricao FROM pedidos WHERE carona_id=%s", (c["id"],))
        itens = cur.fetchall()
        cur.execute("SELECT m.nome, m.sobrenome, u.telefone FROM motoristas m "
                    "JOIN usuarios u ON u.id=m.usuario_id WHERE m.usuario_id=%s", (c["motorista_id"],))
        mot = cur.fetchone()
    return {"itens": itens, "motorista": f"{mot['nome']} {mot['sobrenome']}", "telefone": mot["telefone"]}


def validar_entrega(centro_id, codigo):
    """O motorista diz o código ao centro de destino -> carona encerrada e taxa marcada como paga."""
    codigo = somente_digitos(codigo)
    with transaction() as cur:
        cur.execute("SELECT * FROM caronas WHERE centro_destino_id=%s AND codigo_entrega=%s "
                    "AND status='em_andamento' FOR UPDATE", (centro_id, codigo))
        c = cur.fetchone()
        if not c:
            raise ValueError("Código inválido, já utilizado ou de outro centro.")
        agora = datetime.now()
        cur.execute("UPDATE caronas SET status='encerrada', entrega_em=%s WHERE id=%s", (agora, c["id"]))
        cur.execute("UPDATE pedidos SET status='encerrado', entregue_em=%s, pago=TRUE, pago_em=%s "
                    "WHERE carona_id=%s AND status='em_andamento'", (agora, agora, c["id"]))
        cur.execute("SELECT COUNT(*) AS n FROM pedidos WHERE carona_id=%s", (c["id"],))
        n = cur.fetchone()["n"]
    return {"qtd": n, "total": float(c["taxa_total"])}


def acompanhamento_centro(centro_id):
    return query(
        _SELECT_PEDIDO.replace("FROM pedidos p", ", m.nome AS mot_nome, m.sobrenome AS mot_sobrenome, "
                               "u.telefone AS mot_tel FROM pedidos p", 1)
        + """ JOIN caronas c ON c.id = p.carona_id
              JOIN motoristas m ON m.usuario_id = c.motorista_id
              JOIN usuarios u ON u.id = c.motorista_id
              WHERE p.centro_origem_id=%s AND p.status IN ('solicitado','em_andamento','encerrado')
              ORDER BY FIELD(p.status,'solicitado','em_andamento','encerrado'),
                       COALESCE(p.entregue_em, p.retirado_em, p.retirada_prevista) DESC""",
        (centro_id,))


def a_receber_centro(centro_id):
    """Pedidos em andamento que estão a caminho deste centro."""
    return query(_SELECT_PEDIDO + " WHERE p.centro_destino_id=%s AND p.status='em_andamento' "
                 "ORDER BY p.retirado_em", (centro_id,))
