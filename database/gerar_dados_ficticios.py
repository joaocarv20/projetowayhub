"""
Arquivo: database/gerar_dados_ficticios.py
Função: gera database/dados_ficticios.sql — script para rodar no MySQL Workbench (depois do schema.sql) que
        popula o banco com centros, motoristas, veículos, caronas e +600 pedidos FICTÍCIOS.
        Uso:  python -m database.gerar_dados_ficticios
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

from domain.pedidos import CalculadoraTaxa
from ml.geografia import distancia_km
from utils.helpers import hash_senha

SAIDA = Path(__file__).parent / "dados_ficticios.sql"
SENHA_PADRAO = "123456"
HASH = hash_senha(SENHA_PADRAO, salt="00" * 16)   # mesma senha p/ todos os usuários fictícios
random.seed(7)

N_ENCERRADOS_MIN = 560
CENTROS = [  # (cidade, bairro, rua)
    ("Anápolis - GO", "Jundiaí", "Av. Brasil Sul"), ("Anápolis - GO", "Centro", "Rua Engenheiro Portela"),
    ("Goiânia - GO", "Setor Bueno", "Av. T-63"), ("Goiânia - GO", "Campinas", "Av. Independência"),
    ("Brasília - DF", "SIA", "Trecho 3"), ("Brasília - DF", "Taguatinga", "QNE 12"),
    ("Aparecida de Goiânia - GO", "Papillon Park", "Av. Rio Verde"), ("Trindade - GO", "Centro", "Av. Pedro Ludovico"),
    ("Senador Canedo - GO", "Distrito Industrial", "Rod. GO-403"), ("Luziânia - GO", "Centro", "Av. Alfredo Nasser"),
    ("Catalão - GO", "Distrito Industrial", "Av. Pedro Gomes"), ("Rio Verde - GO", "Centro", "Av. Presidente Vargas"),
    ("Uberlândia - MG", "Distrito Industrial", "Av. Clodoaldo Gomes"),
]
NOMES = ["Ana", "Bruno", "Carlos", "Daniela", "Eduardo", "Fernanda", "Gustavo", "Helena", "Igor", "Juliana",
         "Kleber", "Larissa", "Marcos", "Natália", "Otávio", "Patrícia", "Rafael", "Sabrina", "Thiago", "Vanessa"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Santos", "Pereira", "Lima", "Costa", "Ribeiro", "Almeida", "Carvalho",
              "Gomes", "Martins", "Araújo", "Barbosa", "Rocha", "Dias", "Nunes", "Mendes", "Teixeira", "Moreira"]
VEICULOS = [("Moto", ["Honda CG 160", "Yamaha Factor 150"]), ("Carro", ["Fiat Uno", "VW Gol", "Chevrolet Onix", "Hyundai HB20"]),
            ("Van", ["Fiat Ducato", "Renault Master"]), ("Utilitário / Caminhonete", ["Fiat Strada", "Toyota Hilux"])]
FAIXAS_ALVO = {"Mini (tipo capinha)": 0.40, "Pequeno": 0.30, "Médio": 0.20, "Grande": 0.10}
ITENS = {"Mini (tipo capinha)": ["Capinhas de celular", "Carregadores", "Fones de ouvido", "Películas"],
         "Pequeno": ["Kit de cosméticos", "Livros", "Peças de reposição", "Camisetas"],
         "Médio": ["Caixa de calçados", "Eletroportáteis", "Material de escritório"],
         "Grande": ["Monitores", "Ferramentas", "Caixa de alimentos"]}
LIMITES = {"Mini (tipo capinha)": ((2, 8), (8, 20), (5, 12), (0.05, 0.5)),
           "Pequeno": ((5, 20), (10, 30), (8, 30), (0.5, 2.0)),
           "Médio": ((15, 35), (20, 50), (15, 40), (2.0, 10.0)),
           "Grande": ((30, 55), (40, 60), (30, 55), (10.0, 30.0))}


def sql(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, datetime):
        return f"'{v:%Y-%m-%d %H:%M:%S}'"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    return s[4:] if s.startswith("RAW:") else "'" + s.replace("'", "''") + "'"


def raw(expr):
    return "RAW:" + expr


def inserir(tabela, colunas, linhas, bloco=100):
    saida = []
    for i in range(0, len(linhas), bloco):
        corpo = ",\n".join("  (" + ", ".join(sql(v) for v in l) + ")" for l in linhas[i:i + bloco])
        saida.append(f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES\n{corpo};")
    return "\n".join(saida) + "\n"


def cnpj_valido_gerado(n):
    base = [int(d) for d in f"{10000000 + n * 137:08d}0001"]
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        r = sum(d * p for d, p in zip(base, pesos)) % 11
        base.append(0 if r < 2 else 11 - r)
    return "".join(map(str, base))


def telefone():
    return "629" + "".join(random.choice("0123456789") for _ in range(8))


def dimensoes(faixa):
    while True:
        (a1, a2), (c1, c2), (l1, l2), (p1, p2) = LIMITES[faixa]
        alt, comp, larg = round(random.uniform(a1, a2), 1), round(random.uniform(c1, c2), 1), round(random.uniform(l1, l2), 1)
        peso = round(random.uniform(p1, p2), 2)
        cat, taxa = CalculadoraTaxa.classificar(peso, alt * comp * larg) if alt * comp * larg < 200_000 else (None, None)
        if cat == faixa:
            return alt, comp, larg, peso, cat, taxa


def duracao_horas(km, peso_total, retirada):
    h = 2.5 + km / 55 + peso_total * 0.03 + random.uniform(-1, 2)
    if retirada.hour >= 16:
        h += 12
    if retirada.weekday() == 5:
        h += 18
    if retirada.weekday() == 6:
        h += 30
    return h


def main():
    centros_ids = list(range(1, len(CENTROS) + 1))
    n_mot = 20
    mot_ids = list(range(len(CENTROS) + 1, len(CENTROS) + n_mot + 1))

    usuarios, centros, motoristas, veiculos = [], [], [], []
    for i, (cidade, bairro, rua) in enumerate(CENTROS, 1):
        usuarios.append([i, "centro", f"centro{i:02d}@wayhub.test", HASH, telefone(), datetime(2026, 1, 2, 9)])
        cidade_curta = cidade.split(" - ")[0]
        centros.append([i, f"CD {cidade_curta} {bairro}", cnpj_valido_gerado(i), cidade, bairro, rua, str(random.randint(10, 2000))])
    placas = set()
    for j, uid in enumerate(mot_ids):
        usuarios.append([uid, "motorista", f"motorista{j + 1:02d}@wayhub.test", HASH, telefone(), datetime(2026, 1, 3, 10)])
        cid = random.choice([c[0] for c in CENTROS])
        motoristas.append([uid, NOMES[j], random.choice(SOBRENOMES), cid, f"Rua {random.randint(1, 80)}, {random.randint(10, 900)}, Centro"])
        while True:
            placa = "".join(random.choices("ABCDEFGHJKLMNPRSTUVXZ", k=3)) + str(random.randint(0, 9)) + random.choice("ABCDEFGHJ") + f"{random.randint(0, 99):02d}"
            if placa not in placas:
                placas.add(placa)
                break
        tipo, modelos = random.choice(VEICULOS)
        veiculos.append([j + 1, uid, tipo, random.choice(modelos), placa, random.randint(2012, 2025)])

    def rota():
        while True:
            o, d = random.sample(centros_ids, 2)
            if CENTROS[o - 1][0] != CENTROS[d - 1][0] or random.random() < 0.05:
                return o, d

    def novo_pedido(faixa=None):
        faixa = faixa or random.choices(list(FAIXAS_ALVO), weights=FAIXAS_ALVO.values())[0]
        alt, comp, larg, peso, cat, taxa = dimensoes(faixa)
        return {"desc": f"{random.randint(1, 60)} un. - {random.choice(ITENS[faixa])}" if faixa.startswith("Mini") else random.choice(ITENS[faixa]),
                "alt": alt, "comp": comp, "larg": larg, "peso": peso, "cat": cat, "taxa": taxa}

    def pedidos_da_carona(minimo=5.0):
        itens, total = [], 0.0
        while total < minimo or (random.random() < 0.3 and len(itens) < 10):
            p = novo_pedido()
            itens.append(p)
            total = round(total + p["taxa"], 2)
        return itens, total

    caronas = []  # dicts
    n_enc = 0
    inicio, fim = datetime(2026, 1, 5, 7), datetime(2026, 11, 4, 20)
    while n_enc < N_ENCERRADOS_MIN:
        o, d = rota()
        retirada = inicio + timedelta(days=random.randint(0, (fim - inicio).days), hours=random.randint(0, 13),
                                      minutes=random.choice([0, 15, 30, 45]))
        if retirada.weekday() == 6 and random.random() < 0.7:
            continue
        itens, total = pedidos_da_carona()
        km = distancia_km(CENTROS[o - 1][0], CENTROS[d - 1][0])
        retirada_real = retirada + timedelta(minutes=random.randint(-5, 12))
        entrega = retirada_real + timedelta(hours=duracao_horas(km, sum(p["peso"] for p in itens), retirada))
        caronas.append({"status": "encerrada", "o": o, "d": d, "itens": itens, "total": total, "prev": retirada,
                        "real": retirada_real, "entrega": entrega,
                        "solic": retirada - timedelta(minutes=random.randint(45, 400))})
        n_enc += len(itens)
    caronas.sort(key=lambda c: c["prev"])

    for status, qtd in (("em_andamento", 3), ("solicitada", 2)):  # estados "vivos" para a demonstração
        for k in range(qtd):
            o, d = rota()
            itens, total = pedidos_da_carona()
            c = {"status": status, "o": o, "d": d, "itens": itens, "total": total}
            if status == "em_andamento":
                h = random.randint(1, 5)
                c.update(prev=raw(f"DATE_SUB(NOW(), INTERVAL {h * 60 + 5} MINUTE)"), real=raw(f"DATE_SUB(NOW(), INTERVAL {h} HOUR)"),
                         entrega=None, solic=raw(f"DATE_SUB(NOW(), INTERVAL {h + 3} HOUR)"))
            else:
                c.update(prev=raw(f"DATE_ADD(NOW(), INTERVAL {3 + k} HOUR)"), real=None, entrega=None,
                         solic=raw(f"DATE_SUB(NOW(), INTERVAL {10 + k * 5} MINUTE)"))
            caronas.append(c)

    linhas_caronas, linhas_pedidos = [], []
    seq = {i: 0 for i in centros_ids}
    pid = 0
    for cid, c in enumerate(caronas, 1):
        mot = random.randrange(n_mot)
        enc, andamento = c["status"] == "encerrada", c["status"] == "em_andamento"
        linhas_caronas.append([cid, mot_ids[mot], mot + 1, c["o"], c["d"], f"{random.randint(0, 999999):06d}",
                               f"{random.randint(0, 999999):06d}" if (enc or andamento) else None, c["total"], c["status"],
                               c["prev"], c["solic"], c["real"], c["entrega"]])
        for p in c["itens"]:
            pid += 1
            seq[c["o"]] += 1
            st = {"encerrada": "encerrado", "em_andamento": "em_andamento", "solicitada": "solicitado"}[c["status"]]
            linhas_pedidos.append([pid, f"WH-{c['o']:03d}-{seq[c['o']]:05d}", seq[c["o"]], c["o"], c["d"], p["desc"], p["alt"], p["comp"],
                                   p["larg"], p["peso"], p["cat"], p["taxa"], c["prev"], st, cid, c["real"], c["entrega"],
                                   enc, c["entrega"] if enc else None])

    # pedidos disponíveis (aparecem na busca do motorista) e alguns cancelados
    rotas_fixas = [rota() for _ in range(5)]
    for _ in range(30):
        o, d = random.choice(rotas_fixas) if random.random() < 0.8 else rota()
        p = novo_pedido()
        pid += 1
        seq[o] += 1
        linhas_pedidos.append([pid, f"WH-{o:03d}-{seq[o]:05d}", seq[o], o, d, p["desc"], p["alt"], p["comp"], p["larg"], p["peso"], p["cat"],
                               p["taxa"], raw(f"DATE_ADD(NOW(), INTERVAL {random.randint(2, 96)} HOUR)"), "disponivel", None, None, None, False, None])
    for _ in range(5):
        o, d = rota()
        p = novo_pedido()
        pid += 1
        seq[o] += 1
        linhas_pedidos.append([pid, f"WH-{o:03d}-{seq[o]:05d}", seq[o], o, d, p["desc"], p["alt"], p["comp"], p["larg"], p["peso"], p["cat"],
                               p["taxa"], raw(f"DATE_SUB(NOW(), INTERVAL {random.randint(2, 40)} DAY)"), "cancelado", None, None, None, False, None])

    cab = f"""-- Arquivo: database/dados_ficticios.sql
-- Função: popula o banco wayhub com dados FICTÍCIOS ({len(linhas_pedidos)} pedidos, {len(caronas)} caronas, {len(CENTROS)} centros e {n_mot} motoristas).
-- Como usar no MySQL Workbench: 1) rode database/schema.sql  2) abra e rode ESTE arquivo (⚡).
-- ATENÇÃO: apaga o conteúdo atual das tabelas do wayhub antes de inserir.
-- Logins fictícios (senha de todos: {SENHA_PADRAO}):  centro01@wayhub.test ... centro{len(CENTROS):02d}@wayhub.test
--                                                    motorista01@wayhub.test ... motorista{n_mot:02d}@wayhub.test
SET NAMES utf8mb4;
USE wayhub;
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE pedidos; TRUNCATE TABLE caronas; TRUNCATE TABLE veiculos; TRUNCATE TABLE centros;
TRUNCATE TABLE motoristas; TRUNCATE TABLE usuarios;
SET FOREIGN_KEY_CHECKS = 1;

"""
    corpo = (inserir("usuarios", ["id", "tipo", "email", "senha_hash", "telefone", "criado_em"], usuarios)
             + inserir("centros", ["usuario_id", "nome", "cnpj", "cidade", "bairro", "logradouro", "numero"], centros)
             + inserir("motoristas", ["usuario_id", "nome", "sobrenome", "cidade_origem", "endereco"], motoristas)
             + inserir("veiculos", ["id", "motorista_id", "tipo", "modelo", "placa", "ano"], veiculos)
             + inserir("caronas", ["id", "motorista_id", "veiculo_id", "centro_origem_id", "centro_destino_id", "codigo_retirada",
                                   "codigo_entrega", "taxa_total", "status", "retirada_prevista", "solicitada_em", "retirada_em", "entrega_em"], linhas_caronas)
             + inserir("pedidos", ["id", "codigo_pedido", "seq_centro", "centro_origem_id", "centro_destino_id", "descricao", "altura_cm",
                                   "comprimento_cm", "largura_cm", "peso_kg", "categoria", "taxa", "retirada_prevista", "status", "carona_id",
                                   "retirado_em", "entregue_em", "pago", "pago_em"], linhas_pedidos))
    SAIDA.write_text(cab + corpo, encoding="utf-8")
    print(f"{SAIDA}: {len(linhas_pedidos)} pedidos ({n_enc} encerrados), {len(caronas)} caronas")


if __name__ == "__main__":
    main()
