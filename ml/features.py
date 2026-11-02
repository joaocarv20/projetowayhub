"""Variáveis do modelo de prazo de trânsito (OptiRoute AI).

Usado pelo treino (train.py) e pela API do WayHub, para que as duas pontas montem as entradas do mesmo jeito.
Só usa informação conhecida no momento da postagem: de onde sai, para onde vai, o pacote e a data.
"""
import numpy as np
import pandas as pd

REGION = {
    **dict.fromkeys(["AC", "AP", "AM", "PA", "RO", "RR", "TO"], "Norte"),
    **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "Nordeste"),
    **dict.fromkeys(["DF", "GO", "MT", "MS"], "Centro-Oeste"),
    **dict.fromkeys(["ES", "MG", "RJ", "SP"], "Sudeste"),
    **dict.fromkeys(["PR", "RS", "SC"], "Sul"),
}

CAT_FEATURES = ["origin_state", "dest_state", "dest_region"]
NUM_FEATURES = [
    "distance_km", "same_state",
    "origin_lat", "origin_lng", "dest_lat", "dest_lng",
    "weight_kg", "volume_cm3", "n_items",
    "month", "weekday",
]
FEATURES = CAT_FEATURES + NUM_FEATURES


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(h))


def make_features(df):
    """Recebe origem/destino (lat, lng, UF), pacote (peso, volume, itens) e posted_at; devolve a tabela X."""
    posted = pd.to_datetime(df["posted_at"])
    out = pd.DataFrame({
        "origin_state": df["origin_state"].astype(str),
        "dest_state": df["dest_state"].astype(str),
        "dest_region": df["dest_state"].map(REGION).fillna("?"),
        "distance_km": haversine_km(df["origin_lat"], df["origin_lng"], df["dest_lat"], df["dest_lng"]),
        "same_state": (df["origin_state"] == df["dest_state"]).astype(int),
        "origin_lat": df["origin_lat"], "origin_lng": df["origin_lng"],
        "dest_lat": df["dest_lat"], "dest_lng": df["dest_lng"],
        "weight_kg": df["weight_kg"].astype(float),
        "volume_cm3": df["volume_cm3"].astype(float),
        "n_items": df["n_items"].astype(int),
        "month": posted.dt.month,
        "weekday": posted.dt.weekday,
    }, index=df.index)
    return out[FEATURES]


class GeoIndex:
    """Prefixo de CEP (5 dígitos) → coordenada média e UF; cai no prefixo vizinho mais próximo se faltar."""

    def __init__(self, prefixes, lats, lngs, states):
        order = np.argsort(prefixes)
        self.prefixes = np.asarray(prefixes)[order]
        self.lats = np.asarray(lats)[order]
        self.lngs = np.asarray(lngs)[order]
        self.states = np.asarray(states)[order]

    def lookup(self, cep):
        digits = "".join(c for c in str(cep) if c.isdigit())
        if len(digits) < 5:
            raise ValueError("CEP inválido.")
        prefix = int(digits[:5])
        i = int(np.searchsorted(self.prefixes, prefix))
        candidates = [j for j in (i - 1, i) if 0 <= j < len(self.prefixes)]
        j = min(candidates, key=lambda k: abs(self.prefixes[k] - prefix))
        return float(self.lats[j]), float(self.lngs[j]), str(self.states[j])
