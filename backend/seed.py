"""Popula o banco com dados de demonstração. Uso: python seed.py  (senha de todas as contas: wayhub123)"""
import random
from datetime import timedelta

from werkzeug.security import generate_password_hash

import rules
from app import create_app
from db import connect

PASSWORD = "wayhub123"

HUBS = [
    ("hub.anapolis@wayhub.com", "CD Anápolis Centro", "Jundiaí", "Anápolis", "75110-000", "Av. Brasil Sul, 1200"),
    ("hub.anapolis2@wayhub.com", "Hub DAIA Anápolis", "Distrito Agroindustrial", "Anápolis", "75132-000", "Via Primária 4, Quadra 2"),
    ("hub.goiania@wayhub.com", "CD Goiânia Campinas", "Setor Campinas", "Goiânia", "74513-000", "Av. 24 de Outubro, 850"),
    ("hub.goiania2@wayhub.com", "Hub Goiânia Setor Bueno", "Setor Bueno", "Goiânia", "74230-000", "Av. T-9, 2300"),
    ("hub.brasilia@wayhub.com", "CD Brasília SIA", "SIA", "Brasília", "71200-000", "SIA Trecho 3, Lote 625"),
    ("hub.aparecida@wayhub.com", "Hub Aparecida Polo", "Polo Empresarial", "Aparecida de Goiânia", "74993-000", "Rua VPR-1, Qd. 5"),
]

# (descrição, altura, largura, comprimento, peso)
ITEMS = [
    ("Capinha de celular", 15, 8, 2, 0.05),
    ("Fone de ouvido", 12, 10, 5, 0.2),
    ("Livro", 23, 16, 3, 0.45),
    ("Tênis", 33, 22, 12, 0.9),
    ("Caixa P", 20, 20, 15, 1.5),
    ("Caixa M", 40, 30, 25, 4.0),
    ("Liquidificador", 45, 25, 25, 3.2),
    ("Caixa G", 60, 40, 40, 9.0),
]


def make_cnpj(seed):
    base = [int(d) for d in f"{seed:08d}0001"]
    def dv(digits, weights):
        rest = sum(d * w for d, w in zip(digits, weights)) % 11
        return 0 if rest < 2 else 11 - rest
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    base.append(dv(base, w1))
    base.append(dv(base, [6] + w1))
    return "".join(map(str, base))


def main():
    app = create_app()
    db = connect(app.config["DATABASE"])
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        print("Banco já possui dados — seed ignorado. Apague backend/data/wayhub.db para recriar.")
        return
    pw = generate_password_hash(PASSWORD)
    db.execute("BEGIN")
    hub_ids = []
    for i, (email, name, hood, city, cep, street) in enumerate(HUBS, start=1):
        uid = db.execute("INSERT INTO users (email, password_hash, role) VALUES (?, ?, 'hub')", (email, pw)).lastrowid
        hub_ids.append((db.execute(
            """INSERT INTO logistics_hubs (user_id, name, cnpj, phone, cep, street, neighborhood, city, state)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, name, make_cnpj(12345670 + i), f"(62) 9{8000 + i}-{1000 + i}", cep.replace("-", ""), street, hood, city,
             "DF" if city == "Brasília" else "GO"),
        ).lastrowid, city))

    uid = db.execute("INSERT INTO users (email, password_hash, role) VALUES ('motorista@wayhub.com', ?, 'driver')", (pw,)).lastrowid
    driver_id = db.execute(
        """INSERT INTO drivers (user_id, first_name, last_name, phone, origin_city, home_address, status)
           VALUES (?, 'Carlos', 'Andrade', '(62) 99876-5432', 'Anápolis', 'Rua 15, 230 - Jundiaí, Anápolis/GO', 'active')""",
        (uid,),
    ).lastrowid
    db.execute(
        """INSERT INTO vehicles (driver_id, plate, model, color, year, cargo_type, capacity_kg)
           VALUES (?, 'BRA2E19', 'Fiat Strada', 'Branca', 2022, 'cacamba', 600)""",
        (driver_id,),
    )
    for doc in ("cnh", "crlv"):  # documentos fictícios para o motorista demo
        db.execute("INSERT INTO driver_documents (driver_id, doc_type, storage_key, mime_type) VALUES (?, ?, 'demo', 'image/png')",
                   (driver_id, doc))

    random.seed(42)
    now = rules.utcnow()
    count = 0
    for origin_id, origin_city in hub_ids:
        for dest_id, dest_city in hub_ids:
            if origin_id == dest_id or origin_city == dest_city:
                continue
            for _ in range(random.randint(2, 4)):
                _, h, w, l, kg = random.choice(ITEMS)
                pickup = now + timedelta(hours=random.randint(1, 72), minutes=random.choice([0, 15, 30, 45]))
                count += 1
                db.execute(
                    """INSERT INTO orders (code, origin_hub_id, dest_hub_id, height_cm, width_cm, length_cm, weight_kg, fee_cents, pickup_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (f"WH-DEMO-{count:04d}", origin_id, dest_id, h, w, l, kg, rules.calculate_fee_cents(h, w, l, kg),
                     rules.to_iso(pickup)),
                )
    db.execute("COMMIT")
    print(f"Seed concluído: {len(HUBS)} centros, 1 motorista, {count} pedidos. Senha das contas: {PASSWORD}")
    print("Centro: hub.anapolis@wayhub.com | Motorista: motorista@wayhub.com")


if __name__ == "__main__":
    main()
