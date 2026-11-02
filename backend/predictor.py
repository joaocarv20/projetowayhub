"""Carrega o modelo de prazo de trânsito (OptiRoute AI) treinado em ml/train.py e faz previsões para a API."""
import sys
from pathlib import Path

import pandas as pd

ML_DIR = Path(__file__).resolve().parent.parent / "ml"
MODEL_PATH = ML_DIR / "models" / "transit_model.joblib"
sys.path.insert(0, str(ML_DIR))

from features import REGION, GeoIndex, haversine_km, make_features  # noqa: E402

from rules import RuleError, parse_iso, utcnow  # noqa: E402

_bundle = None


def load():
    global _bundle
    if _bundle is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError("Modelo ainda não treinado. Rode: cd ml && python train.py")
        import joblib
        _bundle = joblib.load(MODEL_PATH)
        _bundle["geo_index"] = GeoIndex(**_bundle["geo"])
    return _bundle


def predict_transit(origin_cep, dest_cep, weight_kg, height_cm, width_cm, length_cm, posted_at=None):
    b = load()
    try:
        o_lat, o_lng, o_uf = b["geo_index"].lookup(origin_cep)
        d_lat, d_lng, d_uf = b["geo_index"].lookup(dest_cep)
    except ValueError:
        raise RuleError("Informe CEPs de origem e destino válidos (8 dígitos).")
    if min(weight_kg, height_cm, width_cm, length_cm) <= 0:
        raise RuleError("Dimensões e peso devem ser maiores que zero.")
    posted = parse_iso(posted_at) if posted_at else utcnow()
    row = pd.DataFrame([{
        "origin_lat": o_lat, "origin_lng": o_lng, "origin_state": o_uf,
        "dest_lat": d_lat, "dest_lng": d_lng, "dest_state": d_uf,
        "weight_kg": weight_kg, "volume_cm3": height_cm * width_cm * length_cm, "n_items": 1,
        "posted_at": posted.replace(tzinfo=None),
    }])
    X = make_features(row)
    expected = max(0.5, float(b["model"].predict(X)[0]))
    safe = max(expected, float(b["q90"].predict(X)[0]))
    route_avg = b["b2_means"].get(f"{o_uf}-{d_uf}", b["b2_global"])
    return {
        "expected_days": round(expected, 1),
        "safe_days": round(safe, 1),
        "route_avg_days": round(route_avg, 1),
        "origin": {"state": o_uf, "region": REGION.get(o_uf)},
        "destination": {"state": d_uf, "region": REGION.get(d_uf)},
        "distance_km": round(float(haversine_km(o_lat, o_lng, d_lat, d_lng))),
        "model": b["model_name"],
        "model_mae_days": round(b["test_metrics"]["MAE"], 2),
        "trained_at": b["trained_at"],
    }
