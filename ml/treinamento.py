"""
Arquivo: ml/treinamento.py
Função: treina o modelo (Random Forest) com a tabela historico_entregas + entregas encerradas do MySQL,
        mede o erro e grava as métricas em data/metricas_modelo.json.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from config.settings import DIR_DADOS, JSON_METRICAS, ML_MINIMO_LINHAS
from ml.preparacao_dados import (COLUNAS, carregar_entregas_mysql, carregar_historico_treino,
                                  montar_features)

DISTANCIA_PADRAO = 150.0


@dataclass
class ResultadoTreino:
    modelo: object          # None = poucos dados, a IA usa a estimativa simples
    n_historico: int
    n_mysql: int
    mae_horas: float        # erro médio absoluto no teste (None se poucos dados)
    r2: float
    distancia_padrao: float
    treinado_em: datetime

    @property
    def n_total(self):
        return self.n_historico + self.n_mysql


def treinar():
    vazio = pd.DataFrame(columns=COLUNAS + ["tempo_horas"])
    try:
        df_hist = carregar_historico_treino()
    except Exception as erro:  # banco indisponível ou tabela ausente
        logging.warning("IA: não consegui ler historico_entregas: %s", erro)
        df_hist = vazio
    try:
        df_sql = carregar_entregas_mysql()
    except Exception as erro:
        logging.warning("IA: não consegui ler os pedidos encerrados: %s", erro)
        df_sql = vazio
    df = pd.concat([df_hist, df_sql], ignore_index=True)

    modelo, mae, r2 = None, None, None
    distancia_padrao = float(df["distancia_km"].median()) if len(df) else DISTANCIA_PADRAO
    if len(df) >= ML_MINIMO_LINHAS:
        X, y = montar_features(df), df["tempo_horas"]
        modelo = RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=42, n_jobs=-1)
        if len(df) >= 30:  # separa 20% para medir o erro de forma honesta
            X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
            modelo.fit(X_tr, y_tr)
            pred = modelo.predict(X_te)
            mae, r2 = float(mean_absolute_error(y_te, pred)), float(r2_score(y_te, pred))
        modelo.fit(X, y)  # modelo final usa 100% dos dados

    res = ResultadoTreino(modelo, len(df_hist), len(df_sql), mae, r2, distancia_padrao, datetime.now())
    _gravar_metricas(res)
    return res


def _gravar_metricas(res):
    DIR_DADOS.mkdir(exist_ok=True)
    JSON_METRICAS.write_text(json.dumps({
        "treinado_em": res.treinado_em.isoformat(timespec="seconds"),
        "algoritmo": "RandomForestRegressor" if res.modelo is not None else "estimativa simples (poucos dados)",
        "linhas_historico": res.n_historico, "linhas_mysql": res.n_mysql, "linhas_total": res.n_total,
        "erro_medio_horas": None if res.mae_horas is None else round(res.mae_horas, 2),
        "r2": None if res.r2 is None else round(res.r2, 3),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
