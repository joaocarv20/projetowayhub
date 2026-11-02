"""Módulo de regras de negócio do WayHub (precificação, taxa mínima, lock-in, códigos OTP, ETA)."""
import math
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone

# --- Precificação ---------------------------------------------------------
BASE_FEE_CENTS = 50            # tarifa base por volume
PER_KG_CENTS = 120             # por kg taxável
CUBIC_FACTOR_KG_PER_M3 = 300   # fator de cubagem rodoviário (300 kg/m³)
ULTRA_SMALL_MAX_VOLUME_CM3 = 1000
ULTRA_SMALL_MAX_WEIGHT_KG = 0.3
ULTRA_SMALL_CAP_CENTS = 70     # itens ultra-pequenos (ex.: capinha de celular) custam no máximo R$ 0,70

# --- Regras de reserva ----------------------------------------------------
MIN_TRIP_FEE_CENTS = 500       # soma mínima de R$ 5,00 por viagem
MIN_LEAD_TIME = timedelta(minutes=40)


class RuleError(ValueError):
    """Violação de regra de negócio; a mensagem é exibida ao usuário."""


def cubic_weight_kg(height_cm, width_cm, length_cm):
    volume_m3 = (height_cm * width_cm * length_cm) / 1_000_000
    return volume_m3 * CUBIC_FACTOR_KG_PER_M3


def calculate_fee_cents(height_cm, width_cm, length_cm, weight_kg):
    """Taxa paga ao motorista: base + valor por kg taxável (maior entre peso real e cubado)."""
    for value in (height_cm, width_cm, length_cm, weight_kg):
        if value is None or value <= 0:
            raise RuleError("Dimensões e peso devem ser maiores que zero.")
    taxable_kg = max(weight_kg, cubic_weight_kg(height_cm, width_cm, length_cm))
    fee = BASE_FEE_CENTS + math.ceil(taxable_kg * PER_KG_CENTS)
    volume_cm3 = height_cm * width_cm * length_cm
    if volume_cm3 <= ULTRA_SMALL_MAX_VOLUME_CM3 and weight_kg <= ULTRA_SMALL_MAX_WEIGHT_KG:
        fee = min(fee, ULTRA_SMALL_CAP_CENTS)
    return fee


def size_label(height_cm, width_cm, length_cm):
    volume = height_cm * width_cm * length_cm
    if volume <= ULTRA_SMALL_MAX_VOLUME_CM3:
        return "PP"
    if volume <= 10_000:
        return "P"
    if volume <= 50_000:
        return "M"
    if volume <= 150_000:
        return "G"
    return "GG"


def validate_min_trip_fee(fees_cents):
    total = sum(fees_cents)
    if total < MIN_TRIP_FEE_CENTS:
        missing = (MIN_TRIP_FEE_CENTS - total) / 100
        raise RuleError(
            f"A soma das taxas precisa atingir R$ 5,00 para iniciar a rota. Faltam R$ {missing:.2f}".replace(".", ",")
        )
    return total


def validate_lead_time(pickup_at, now=None):
    """A solicitação deve ocorrer no mínimo 40 minutos antes da retirada."""
    now = now or utcnow()
    if pickup_at - now < MIN_LEAD_TIME:
        raise RuleError("Solicitações devem ser feitas com no mínimo 40 minutos de antecedência da retirada.")


def request_deadline(pickup_at):
    return pickup_at - MIN_LEAD_TIME


def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


# --- Datas ----------------------------------------------------------------
def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_iso(value):
    if not value:
        raise RuleError("Data/hora inválida.")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Tempo médio estimado de percurso -------------------------------------
# Coordenadas aproximadas de cidades atendidas no MVP. Em produção: API de rotas (Google/OSRM).
CITY_COORDS = {
    "anapolis": (-16.3281, -48.9530),
    "goiania": (-16.6869, -49.2648),
    "aparecida de goiania": (-16.8198, -49.2469),
    "brasilia": (-15.7939, -47.8828),
    "senador canedo": (-16.7084, -49.0914),
    "trindade": (-16.6517, -49.4927),
    "rio verde": (-17.7923, -50.9192),
    "itumbiara": (-18.4093, -49.2158),
    "catalao": (-18.1656, -47.9440),
    "luziania": (-16.2525, -47.9500),
    "uberlandia": (-18.9186, -48.2772),
    "sao paulo": (-23.5505, -46.6333),
    "campinas": (-22.9099, -47.0626),
    "belo horizonte": (-19.9167, -43.9345),
    "rio de janeiro": (-22.9068, -43.1729),
    "curitiba": (-25.4284, -49.2733),
    "cuiaba": (-15.6014, -56.0979),
    "palmas": (-10.1840, -48.3336),
}
ROAD_FACTOR = 1.3          # distância rodoviária ≈ 1,3 × linha reta
AVG_SPEED_KMH = 70
URBAN_TRIP_MINUTES = 35    # mesma cidade


def normalize_city(name):
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def estimate_travel_minutes(origin_city, dest_city):
    a, b = normalize_city(origin_city), normalize_city(dest_city)
    if a == b:
        return URBAN_TRIP_MINUTES
    if a not in CITY_COORDS or b not in CITY_COORDS:
        return None
    (lat1, lon1), (lat2, lon2) = CITY_COORDS[a], CITY_COORDS[b]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 2 * 6371 * math.asin(math.sqrt(h)) * ROAD_FACTOR
    return round(km / AVG_SPEED_KMH * 60 + 10)  # +10 min de manobra/entrada nos centros
