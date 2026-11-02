-- WayHub — modelo relacional (SQLite no MVP; compatível com PostgreSQL com ajustes mínimos)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('hub', 'driver')),
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS logistics_hubs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    cnpj         TEXT    NOT NULL UNIQUE,
    phone        TEXT    NOT NULL,
    cep          TEXT    NOT NULL,
    street       TEXT    NOT NULL,
    neighborhood TEXT    NOT NULL,
    city         TEXT    NOT NULL,
    state        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS drivers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    first_name   TEXT    NOT NULL,
    last_name    TEXT    NOT NULL,
    phone        TEXT    NOT NULL,
    origin_city  TEXT    NOT NULL,
    home_address TEXT    NOT NULL,
    -- pending_docs: falta veículo/documentos | active: liberado para solicitar cargas
    status       TEXT    NOT NULL DEFAULT 'pending_docs' CHECK (status IN ('pending_docs', 'active', 'blocked'))
);

CREATE TABLE IF NOT EXISTS vehicles (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id          INTEGER NOT NULL UNIQUE REFERENCES drivers(id) ON DELETE CASCADE,
    plate              TEXT    NOT NULL,
    model              TEXT    NOT NULL,
    color              TEXT    NOT NULL,
    year               INTEGER NOT NULL,
    cargo_type         TEXT    NOT NULL CHECK (cargo_type IN ('porta_malas_pequeno', 'porta_malas_medio', 'porta_malas_grande', 'cacamba', 'furgao')),
    capacity_kg        REAL    NOT NULL,
    owned_by_third_party INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS driver_documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id   INTEGER NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
    doc_type    TEXT    NOT NULL CHECK (doc_type IN ('cnh', 'crlv', 'owner_id')),
    storage_key TEXT    NOT NULL,          -- chave privada no storage (nunca exposta diretamente)
    mime_type   TEXT    NOT NULL,
    uploaded_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (driver_id, doc_type)
);

CREATE TABLE IF NOT EXISTS orders (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    code                 TEXT    NOT NULL UNIQUE,
    origin_hub_id        INTEGER NOT NULL REFERENCES logistics_hubs(id),
    dest_hub_id          INTEGER NOT NULL REFERENCES logistics_hubs(id),
    height_cm            REAL    NOT NULL CHECK (height_cm > 0),
    width_cm             REAL    NOT NULL CHECK (width_cm > 0),
    length_cm            REAL    NOT NULL CHECK (length_cm > 0),
    weight_kg            REAL    NOT NULL CHECK (weight_kg > 0),
    fee_cents            INTEGER NOT NULL CHECK (fee_cents > 0),
    pickup_at            TEXT    NOT NULL, -- ISO-8601 UTC: retirada prevista no centro de origem
    -- available -> requested (Solicitado) -> in_progress (Em Andamento) -> closed (Encerrado)
    status               TEXT    NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'requested', 'in_progress', 'closed', 'cancelled')),
    created_at           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (origin_hub_id <> dest_hub_id)
);
CREATE INDEX IF NOT EXISTS idx_orders_status_pickup ON orders(status, pickup_at);

CREATE TABLE IF NOT EXISTS trips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id       INTEGER NOT NULL REFERENCES drivers(id),
    total_fee_cents INTEGER NOT NULL,
    pickup_code     TEXT    NOT NULL,      -- Código 1 (checkout na origem)
    delivery_code   TEXT    NOT NULL,      -- Código 2 (check-in no destino), revelado após a coleta
    status          TEXT    NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'in_progress', 'closed')),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS trip_orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id      INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    order_id     INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    fee_cents    INTEGER NOT NULL,         -- taxa congelada no momento da reserva
    picked_up_at TEXT,
    delivered_at TEXT,
    paid_at      TEXT                      -- pagamento automático liberado pelo centro de origem
);
