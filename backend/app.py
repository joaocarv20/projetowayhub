"""API REST do WayHub (Flask) + entrega da SPA em /frontend."""
import os
import re
import secrets
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, request, send_file
from werkzeug.security import check_password_hash, generate_password_hash

import rules
from db import close_db, get_db, init_db
from rules import RuleError
from security import (
    auth_required,
    create_jwt,
    private_file_path,
    save_private_file,
    sign_storage_key,
    unsign_storage_key,
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

CARGO_TYPES = {
    # tipo: capacidade padrão (kg) sugerida quando o motorista não informa
    "porta_malas_pequeno": 50,
    "porta_malas_medio": 100,
    "porta_malas_grande": 200,
    "cacamba": 600,
    "furgao": 1000,
}
STATUS_LABELS = {"requested": "Solicitado", "in_progress": "Em Andamento", "closed": "Encerrado"}


def create_app(config=None):
    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
    app.config.update(
        SECRET_KEY=os.environ.get("WAYHUB_SECRET", "dev-secret-troque-em-producao"),
        DATABASE=os.environ.get("WAYHUB_DB", str(BASE_DIR / "data" / "wayhub.db")),
        STORAGE_DIR=os.environ.get("WAYHUB_STORAGE", str(BASE_DIR / "data" / "private_storage")),
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    )
    if config:
        app.config.update(config)
    init_db(app.config["DATABASE"])
    app.teardown_appcontext(close_db)
    register_routes(app)
    return app


# --- Helpers ----------------------------------------------------------------
def err(message, status=400):
    return jsonify(error=message), status


def body():
    return request.get_json(silent=True) or {}


def require_fields(data, fields):
    missing = [f for f in fields if not str(data.get(f, "")).strip()]
    if missing:
        raise RuleError("Campos obrigatórios não preenchidos: " + ", ".join(missing))
    return {f: str(data[f]).strip() for f in fields}


def to_float(value, name):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        raise RuleError(f"Valor inválido para {name}.")


def only_digits(value):
    return re.sub(r"\D", "", value or "")


def valid_cnpj(cnpj):
    digits = only_digits(cnpj)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False
    def check(base, weights):
        total = sum(int(d) * w for d, w in zip(base, weights))
        rest = total % 11
        return "0" if rest < 2 else str(11 - rest)
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = check(digits[:12], w1)
    d2 = check(digits[:12] + d1, [6] + w1)
    return digits[12:] == d1 + d2


def valid_email(email):
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or "") is not None


def create_user(db, email, password, role):
    email = email.lower()
    if not valid_email(email):
        raise RuleError("E-mail inválido.")
    if len(password) < 6:
        raise RuleError("A senha deve ter pelo menos 6 caracteres.")
    try:
        cur = db.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)",
            (email, generate_password_hash(password), role),
        )
    except sqlite3.IntegrityError:
        raise RuleError("Este e-mail já está cadastrado.")
    return cur.lastrowid


def issue_token(app, user_id, role):
    return create_jwt({"sub": str(user_id), "role": role}, app.config["SECRET_KEY"])


def current_hub(db):
    hub = db.execute("SELECT * FROM logistics_hubs WHERE user_id = ?", (g.user_id,)).fetchone()
    if not hub:
        raise RuleError("Centro Logístico não encontrado.")
    return hub


def current_driver(db):
    driver = db.execute("SELECT * FROM drivers WHERE user_id = ?", (g.user_id,)).fetchone()
    if not driver:
        raise RuleError("Motorista não encontrado.")
    return driver


def hub_ref(row, prefix):
    return {
        "id": row[f"{prefix}_id"],
        "name": row[f"{prefix}_name"],
        "neighborhood": row[f"{prefix}_neighborhood"],
        "city": row[f"{prefix}_city"],
        "state": row[f"{prefix}_state"],
    }


ORDER_COLUMNS = """
    o.*,
           oh.id AS oh_id, oh.name AS oh_name, oh.neighborhood AS oh_neighborhood, oh.city AS oh_city, oh.state AS oh_state,
           dh.id AS dh_id, dh.name AS dh_name, dh.neighborhood AS dh_neighborhood, dh.city AS dh_city, dh.state AS dh_state"""
ORDER_FROM = """
      FROM orders o
      JOIN logistics_hubs oh ON oh.id = o.origin_hub_id
      JOIN logistics_hubs dh ON dh.id = o.dest_hub_id
"""
ORDER_SELECT = "SELECT" + ORDER_COLUMNS + ORDER_FROM


def serialize_order(row):
    pickup_at = rules.parse_iso(row["pickup_at"])
    return {
        "id": row["id"],
        "code": row["code"],
        "origin": hub_ref(row, "oh"),
        "destination": hub_ref(row, "dh"),
        "height_cm": row["height_cm"],
        "width_cm": row["width_cm"],
        "length_cm": row["length_cm"],
        "weight_kg": row["weight_kg"],
        "size": rules.size_label(row["height_cm"], row["width_cm"], row["length_cm"]),
        "fee_cents": row["fee_cents"],
        "pickup_at": row["pickup_at"],
        "request_deadline": rules.to_iso(rules.request_deadline(pickup_at)),
        "eta_minutes": rules.estimate_travel_minutes(row["oh_city"], row["dh_city"]),
        "status": row["status"],
    }


def unique_trip_codes(db):
    """Gera Código 1 e Código 2 distintos e sem colisão com viagens ainda abertas."""
    active = {
        code
        for r in db.execute("SELECT pickup_code, delivery_code FROM trips WHERE status <> 'closed'")
        for code in (r["pickup_code"], r["delivery_code"])
    }
    codes = []
    while len(codes) < 2:
        code = rules.generate_otp()
        if code not in active and code not in codes:
            codes.append(code)
    return codes


# --- Rotas ------------------------------------------------------------------
def register_routes(app):
    @app.errorhandler(RuleError)
    def handle_rule_error(e):
        return err(str(e), 422)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    # ---------- Autenticação & cadastro ----------
    @app.post("/api/auth/register/hub")
    def register_hub():
        data = body()
        f = require_fields(data, ["name", "cnpj", "email", "password", "phone", "cep", "street", "neighborhood", "city", "state"])
        if not valid_cnpj(f["cnpj"]):
            raise RuleError("CNPJ inválido.")
        db = get_db()
        db.execute("BEGIN")
        try:
            user_id = create_user(db, f["email"], f["password"], "hub")
            db.execute(
                """INSERT INTO logistics_hubs (user_id, name, cnpj, phone, cep, street, neighborhood, city, state)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, f["name"], only_digits(f["cnpj"]), f["phone"], only_digits(f["cep"]), f["street"],
                 f["neighborhood"], f["city"], f["state"].upper()[:2]),
            )
            db.execute("COMMIT")
        except sqlite3.IntegrityError:
            db.execute("ROLLBACK")
            raise RuleError("CNPJ já cadastrado.")
        except Exception:
            db.execute("ROLLBACK")
            raise
        return jsonify(token=issue_token(app, user_id, "hub"), role="hub"), 201

    @app.post("/api/auth/register/driver")
    def register_driver():
        data = body()
        f = require_fields(data, ["email", "password", "first_name", "last_name", "phone", "origin_city", "home_address"])
        db = get_db()
        db.execute("BEGIN")
        try:
            user_id = create_user(db, f["email"], f["password"], "driver")
            db.execute(
                """INSERT INTO drivers (user_id, first_name, last_name, phone, origin_city, home_address)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, f["first_name"], f["last_name"], f["phone"], f["origin_city"], f["home_address"]),
            )
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        return jsonify(token=issue_token(app, user_id, "driver"), role="driver"), 201

    @app.post("/api/auth/login")
    def login():
        data = body()
        email = str(data.get("email", "")).strip().lower()
        role = data.get("role")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], str(data.get("password", ""))):
            return err("E-mail ou senha incorretos.", 401)
        if role and role != user["role"]:
            perfil = "Centro Logístico" if user["role"] == "hub" else "Motorista"
            return err(f"Esta conta está cadastrada como {perfil}.", 403)
        return jsonify(token=issue_token(app, user["id"], user["role"]), role=user["role"])

    @app.get("/api/me")
    @auth_required()
    def me():
        db = get_db()
        if g.role == "hub":
            hub = dict(current_hub(db))
            return jsonify(role="hub", hub=hub)
        driver = dict(current_driver(db))
        vehicle = db.execute("SELECT * FROM vehicles WHERE driver_id = ?", (driver["id"],)).fetchone()
        return jsonify(role="driver", driver=driver, vehicle=dict(vehicle) if vehicle else None)

    # ---------- Dados auxiliares ----------
    @app.get("/api/hubs")
    @auth_required()
    def list_hubs():
        rows = get_db().execute(
            "SELECT id, name, neighborhood, city, state FROM logistics_hubs ORDER BY city, name"
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/cities")
    def list_cities():
        rows = get_db().execute("SELECT DISTINCT city FROM logistics_hubs ORDER BY city").fetchall()
        return jsonify([r["city"] for r in rows])

    @app.get("/api/pricing/quote")
    def quote():
        args = request.args
        h, w, l, kg = (to_float(args.get(k), k) for k in ("height_cm", "width_cm", "length_cm", "weight_kg"))
        return jsonify(
            fee_cents=rules.calculate_fee_cents(h, w, l, kg),
            size=rules.size_label(h, w, l),
            cubic_weight_kg=round(rules.cubic_weight_kg(h, w, l), 3),
        )

    @app.post("/api/predict/transit")
    def predict_transit():
        """Previsão de prazo de trânsito (dias) pelo modelo supervisionado treinado em ml/train.py."""
        import predictor
        data = body()
        h, w, l, kg = (to_float(data.get(k), k) for k in ("height_cm", "width_cm", "length_cm", "weight_kg"))
        try:
            result = predictor.predict_transit(data.get("origin_cep"), data.get("dest_cep"), kg, h, w, l, data.get("posted_at"))
        except FileNotFoundError as e:
            return err(str(e), 503)
        return jsonify(result)

    # ---------- Motorista: onboarding de segurança ----------
    @app.post("/api/driver/onboarding")
    @auth_required("driver")
    def driver_onboarding():
        db = get_db()
        driver = current_driver(db)
        form = request.form
        f = require_fields(form, ["plate", "model", "color", "year", "cargo_type"])
        plate = re.sub(r"[^A-Z0-9]", "", f["plate"].upper())
        if not re.fullmatch(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", plate):
            raise RuleError("Placa inválida (use o padrão ABC1234 ou Mercosul ABC1D23).")
        if f["cargo_type"] not in CARGO_TYPES:
            raise RuleError("Tipo de porta-malas/caçamba inválido.")
        year = int(to_float(f["year"], "ano"))
        if not 1980 <= year <= rules.utcnow().year + 1:
            raise RuleError("Ano do veículo inválido.")
        capacity = to_float(form.get("capacity_kg") or CARGO_TYPES[f["cargo_type"]], "capacidade")
        third_party = form.get("owned_by_third_party") in ("1", "true", "on")

        existing = {r["doc_type"] for r in db.execute("SELECT doc_type FROM driver_documents WHERE driver_id = ?", (driver["id"],))}
        required = ["cnh", "crlv"] + (["owner_id"] if third_party else [])
        missing = [d for d in required if d not in existing and not request.files.get(d)]
        if missing:
            labels = {"cnh": "foto da CNH", "crlv": "foto do CRLV", "owner_id": "documento (RG/CPF) do proprietário"}
            raise RuleError("Envie: " + ", ".join(labels[m] for m in missing))

        saved = []
        try:
            for doc_type in ("cnh", "crlv", "owner_id"):
                file = request.files.get(doc_type)
                if file and file.filename:
                    key, mime = save_private_file(file)
                    saved.append((doc_type, key, mime))
        except ValueError as e:
            raise RuleError(str(e))

        db.execute("BEGIN")
        db.execute(
            """INSERT INTO vehicles (driver_id, plate, model, color, year, cargo_type, capacity_kg, owned_by_third_party)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(driver_id) DO UPDATE SET plate=excluded.plate, model=excluded.model, color=excluded.color,
                 year=excluded.year, cargo_type=excluded.cargo_type, capacity_kg=excluded.capacity_kg,
                 owned_by_third_party=excluded.owned_by_third_party""",
            (driver["id"], plate, f["model"], f["color"], year, f["cargo_type"], capacity, int(third_party)),
        )
        for doc_type, key, mime in saved:
            db.execute(
                """INSERT INTO driver_documents (driver_id, doc_type, storage_key, mime_type) VALUES (?, ?, ?, ?)
                   ON CONFLICT(driver_id, doc_type) DO UPDATE SET storage_key=excluded.storage_key,
                     mime_type=excluded.mime_type, uploaded_at=strftime('%Y-%m-%dT%H:%M:%SZ', 'now')""",
                (driver["id"], doc_type, key, mime),
            )
        # MVP: aprovação automática após envio completo. Produção: fila de análise manual/OCR antes de 'active'.
        db.execute("UPDATE drivers SET status = 'active' WHERE id = ?", (driver["id"],))
        db.execute("COMMIT")
        return jsonify(status="active")

    @app.get("/api/driver/documents")
    @auth_required("driver")
    def driver_documents():
        db = get_db()
        driver = current_driver(db)
        rows = db.execute("SELECT doc_type, uploaded_at, storage_key FROM driver_documents WHERE driver_id = ?", (driver["id"],))
        return jsonify([
            {"doc_type": r["doc_type"], "uploaded_at": r["uploaded_at"], "url": f"/api/files/{sign_storage_key(r['storage_key'])}"}
            for r in rows
        ])

    @app.get("/api/files/<token>")
    def signed_file(token):
        key = unsign_storage_key(token)
        path = private_file_path(key) if key else None
        if not path:
            return err("Link expirado ou inválido.", 403)
        return send_file(path, max_age=0)

    # ---------- Motorista: busca e reserva (estilo BlaBlaCar) ----------
    @app.get("/api/driver/orders/search")
    @auth_required("driver")
    def search_orders():
        args = request.args
        origin = rules.normalize_city(args.get("origin"))
        dest = rules.normalize_city(args.get("destination"))
        min_pickup = rules.utcnow() + rules.MIN_LEAD_TIME
        if args.get("from"):
            min_pickup = max(min_pickup, rules.parse_iso(args["from"]))
        sql = ORDER_SELECT + " WHERE o.status = 'available' AND o.pickup_at >= ?"
        params = [rules.to_iso(min_pickup)]
        if args.get("to"):
            sql += " AND o.pickup_at <= ?"
            params.append(rules.to_iso(rules.parse_iso(args["to"])))
        rows = get_db().execute(sql + " ORDER BY o.pickup_at, o.fee_cents DESC", params).fetchall()
        result = [
            serialize_order(r) for r in rows
            if (not origin or rules.normalize_city(r["oh_city"]) == origin)
            and (not dest or rules.normalize_city(r["dh_city"]) == dest)
        ]
        return jsonify(result)

    @app.post("/api/driver/trips")
    @auth_required("driver")
    def create_trip():
        db = get_db()
        driver = current_driver(db)
        if driver["status"] != "active":
            raise RuleError("Conclua o cadastro do veículo e envie seus documentos antes de solicitar cargas.")
        vehicle = db.execute("SELECT * FROM vehicles WHERE driver_id = ?", (driver["id"],)).fetchone()
        order_ids = sorted({int(i) for i in body().get("order_ids", [])})
        if not order_ids:
            raise RuleError("Selecione ao menos um pedido.")

        db.execute("BEGIN IMMEDIATE")  # trava de escrita: evita dois motoristas reservando o mesmo pedido
        try:
            marks = ",".join("?" * len(order_ids))
            rows = db.execute(ORDER_SELECT + f" WHERE o.id IN ({marks})", order_ids).fetchall()
            if len(rows) != len(order_ids):
                raise RuleError("Um ou mais pedidos não existem.")
            now = rules.utcnow()
            for r in rows:
                if r["status"] != "available":
                    raise RuleError(f"O pedido {r['code']} já foi reservado por outro motorista.")
                try:
                    rules.validate_lead_time(rules.parse_iso(r["pickup_at"]), now)
                except RuleError:
                    raise RuleError(f"O pedido {r['code']} não pode mais ser solicitado (antecedência mínima de 40 min).")
            total = rules.validate_min_trip_fee([r["fee_cents"] for r in rows])
            total_weight = sum(r["weight_kg"] for r in rows)
            if total_weight > vehicle["capacity_kg"]:
                raise RuleError(f"Peso total ({total_weight:.1f} kg) excede a capacidade do veículo ({vehicle['capacity_kg']:.0f} kg).")

            pickup_code, delivery_code = unique_trip_codes(db)
            trip_id = db.execute(
                "INSERT INTO trips (driver_id, total_fee_cents, pickup_code, delivery_code) VALUES (?, ?, ?, ?)",
                (driver["id"], total, pickup_code, delivery_code),
            ).lastrowid
            for r in rows:
                db.execute("INSERT INTO trip_orders (trip_id, order_id, fee_cents) VALUES (?, ?, ?)", (trip_id, r["id"], r["fee_cents"]))
                db.execute("UPDATE orders SET status = 'requested' WHERE id = ?", (r["id"],))
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        return jsonify(trip_id=trip_id, pickup_code=pickup_code, total_fee_cents=total), 201

    @app.get("/api/driver/trips")
    @auth_required("driver")
    def driver_trips():
        db = get_db()
        driver = current_driver(db)
        trips = db.execute("SELECT * FROM trips WHERE driver_id = ? ORDER BY id DESC", (driver["id"],)).fetchall()
        result = []
        for t in trips:
            orders = db.execute(
                ORDER_SELECT + " JOIN trip_orders tor ON tor.order_id = o.id WHERE tor.trip_id = ? ORDER BY o.pickup_at",
                (t["id"],),
            ).fetchall()
            picked = any(o["status"] in ("in_progress", "closed") for o in orders)
            result.append({
                "id": t["id"],
                "status": t["status"],
                "status_label": STATUS_LABELS[t["status"]],
                "total_fee_cents": t["total_fee_cents"],
                "created_at": t["created_at"],
                "pickup_code": t["pickup_code"] if t["status"] != "closed" else None,
                # Código 2 só é revelado após a coleta (Código 1 validado)
                "delivery_code": t["delivery_code"] if picked and t["status"] != "closed" else None,
                "orders": [{**serialize_order(o), "status_label": STATUS_LABELS.get(o["status"], o["status"])} for o in orders],
            })
        return jsonify(result)

    # ---------- Centro Logístico: pedidos ----------
    @app.post("/api/hub/orders")
    @auth_required("hub")
    def create_order():
        db = get_db()
        hub = current_hub(db)
        data = body()
        h, w, l, kg = (to_float(data.get(k), k) for k in ("height_cm", "width_cm", "length_cm", "weight_kg"))
        fee = rules.calculate_fee_cents(h, w, l, kg)
        dest_id = int(to_float(data.get("dest_hub_id"), "centro de destino"))
        if dest_id == hub["id"]:
            raise RuleError("O destino deve ser outro Centro Logístico.")
        if not db.execute("SELECT 1 FROM logistics_hubs WHERE id = ?", (dest_id,)).fetchone():
            raise RuleError("Centro Logístico de destino não encontrado.")
        pickup_at = rules.parse_iso(data.get("pickup_at"))
        if pickup_at <= rules.utcnow() + rules.MIN_LEAD_TIME:
            raise RuleError("A retirada deve ser agendada com mais de 40 minutos de antecedência.")
        code = str(data.get("code") or "").strip().upper() or f"WH-{rules.utcnow():%y%m%d}-{secrets.token_hex(2).upper()}"
        try:
            order_id = db.execute(
                """INSERT INTO orders (code, origin_hub_id, dest_hub_id, height_cm, width_cm, length_cm, weight_kg, fee_cents, pickup_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (code, hub["id"], dest_id, h, w, l, kg, fee, rules.to_iso(pickup_at)),
            ).lastrowid
        except sqlite3.IntegrityError:
            raise RuleError(f"Já existe um pedido com o código {code}.")
        row = db.execute(ORDER_SELECT + " WHERE o.id = ?", (order_id,)).fetchone()
        return jsonify(serialize_order(row)), 201

    @app.get("/api/hub/orders")
    @auth_required("hub")
    def hub_orders():
        db = get_db()
        hub = current_hub(db)
        rows = db.execute(ORDER_SELECT + " WHERE o.origin_hub_id = ? ORDER BY o.id DESC", (hub["id"],)).fetchall()
        return jsonify([serialize_order(r) for r in rows])

    @app.post("/api/hub/orders/<int:order_id>/cancel")
    @auth_required("hub")
    def cancel_order(order_id):
        db = get_db()
        hub = current_hub(db)
        cur = db.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = ? AND origin_hub_id = ? AND status = 'available'",
            (order_id, hub["id"]),
        )
        if not cur.rowcount:
            raise RuleError("Apenas pedidos ainda não solicitados podem ser cancelados.")
        return jsonify(ok=True)

    # ---------- Centro Logístico: acompanhamento & handshake OTP ----------
    @app.get("/api/hub/monitoring")
    @auth_required("hub")
    def monitoring():
        db = get_db()
        hub = current_hub(db)
        rows = db.execute(
            "SELECT" + ORDER_COLUMNS + """, d.first_name, d.last_name, d.phone AS driver_phone,
                   tor.picked_up_at, tor.delivered_at, tor.paid_at""" + ORDER_FROM + """
              JOIN trip_orders tor ON tor.order_id = o.id
              JOIN trips t ON t.id = tor.trip_id
              JOIN drivers d ON d.id = t.driver_id
             WHERE o.origin_hub_id = ? OR o.dest_hub_id = ?
             ORDER BY CASE o.status WHEN 'requested' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, o.pickup_at DESC""",
            (hub["id"], hub["id"]),
        ).fetchall()
        return jsonify([
            {
                **serialize_order(r),
                "status_label": STATUS_LABELS[r["status"]],
                "direction": "outbound" if r["origin_hub_id"] == hub["id"] else "inbound",
                "driver": {"name": f"{r['first_name']} {r['last_name']}", "phone": r["driver_phone"]},
                "picked_up_at": r["picked_up_at"],
                "delivered_at": r["delivered_at"],
                "paid_at": r["paid_at"],
            }
            for r in rows
        ])

    @app.post("/api/hub/validate-code")
    @auth_required("hub")
    def validate_code():
        """Código 1 libera a carga na origem (Em Andamento); Código 2 confirma a entrega no destino (Encerrado + pagamento)."""
        db = get_db()
        hub = current_hub(db)
        code = only_digits(str(body().get("code", "")))
        if len(code) != 6:
            raise RuleError("Informe o código de 6 dígitos fornecido pelo motorista.")
        now = rules.to_iso(rules.utcnow())
        db.execute("BEGIN IMMEDIATE")
        try:
            pickup = db.execute(
                """SELECT o.id, o.code, t.id AS trip_id FROM orders o
                     JOIN trip_orders tor ON tor.order_id = o.id JOIN trips t ON t.id = tor.trip_id
                    WHERE t.pickup_code = ? AND o.origin_hub_id = ? AND o.status = 'requested'""",
                (code, hub["id"]),
            ).fetchall()
            if pickup:
                ids = [r["id"] for r in pickup]
                marks = ",".join("?" * len(ids))
                db.execute(f"UPDATE orders SET status = 'in_progress' WHERE id IN ({marks})", ids)
                db.execute(f"UPDATE trip_orders SET picked_up_at = ? WHERE order_id IN ({marks})", [now, *ids])
                db.execute("UPDATE trips SET status = 'in_progress' WHERE id = ? AND status = 'requested'", (pickup[0]["trip_id"],))
                db.execute("COMMIT")
                return jsonify(action="pickup", status_label="Em Andamento", orders=[r["code"] for r in pickup],
                               message=f"Carga liberada: {len(ids)} pedido(s) em andamento.")

            delivery = db.execute(
                """SELECT o.id, o.code, t.id AS trip_id FROM orders o
                     JOIN trip_orders tor ON tor.order_id = o.id JOIN trips t ON t.id = tor.trip_id
                    WHERE t.delivery_code = ? AND o.dest_hub_id = ? AND o.status = 'in_progress'""",
                (code, hub["id"]),
            ).fetchall()
            if delivery:
                ids = [r["id"] for r in delivery]
                marks = ",".join("?" * len(ids))
                db.execute(f"UPDATE orders SET status = 'closed' WHERE id IN ({marks})", ids)
                # Pagamento automático da taxa autorizado em nome do Centro de origem (gateway real fica fora do MVP)
                db.execute(f"UPDATE trip_orders SET delivered_at = ?, paid_at = ? WHERE order_id IN ({marks})", [now, now, *ids])
                trip_id = delivery[0]["trip_id"]
                pending = db.execute(
                    "SELECT COUNT(*) FROM trip_orders tor JOIN orders o ON o.id = tor.order_id WHERE tor.trip_id = ? AND o.status <> 'closed'",
                    (trip_id,),
                ).fetchone()[0]
                if not pending:
                    db.execute("UPDATE trips SET status = 'closed' WHERE id = ?", (trip_id,))
                db.execute("COMMIT")
                return jsonify(action="delivery", status_label="Encerrado", orders=[r["code"] for r in delivery],
                               message=f"Entrega confirmada: {len(ids)} pedido(s) encerrado(s) e pagamento liberado.")
            db.execute("ROLLBACK")
        except Exception:
            db.execute("ROLLBACK")
            raise
        raise RuleError("Código inválido para este Centro Logístico ou já utilizado.")


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
