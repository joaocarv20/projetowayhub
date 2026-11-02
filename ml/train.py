"""Treino e validação do modelo de prazo de trânsito (OptiRoute AI · Entrega 2).

Uso (na pasta ml/):  python train.py
Entrada: CSVs da Olist em ml/data/
Saída:   models/transit_model.joblib, reports/relatorio.md, reports/metrics.json, reports/figs/*.png
"""
import json
import time
from datetime import datetime
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder

from features import CAT_FEATURES, FEATURES, NUM_FEATURES, REGION, make_features

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
FIGS = REPORTS / "figs"
MODELS = ROOT / "models"
SEED = 42

# Divisão temporal pela data de postagem: o modelo nunca vê o futuro
TRAIN_END = "2018-03-01"   # treino:    out/2016 – fev/2018
VAL_END = "2018-06-01"     # validação: mar/2018 – mai/2018
TEST_END = "2018-09-01"    # teste:     jun/2018 – ago/2018 (set/2018 tem só 2 pedidos e sofre censura)


# --- Dados ----------------------------------------------------------------
def load_geo():
    geo = pd.read_csv(DATA / "olist_geolocation_dataset.csv")
    # remove coordenadas fora do Brasil (há erros de digitação na base)
    geo = geo[geo.geolocation_lat.between(-34, 5.5) & geo.geolocation_lng.between(-74, -34)]
    coords = geo.groupby("geolocation_zip_code_prefix")[["geolocation_lat", "geolocation_lng"]].mean()
    state = (geo.groupby(["geolocation_zip_code_prefix", "geolocation_state"]).size()
             .reset_index().sort_values(0).drop_duplicates("geolocation_zip_code_prefix", keep="last")
             .set_index("geolocation_zip_code_prefix")["geolocation_state"])
    coords["state"] = state
    coords.columns = ["lat", "lng", "state"]
    return coords


def load_dataset(geo):
    dates = ["order_purchase_timestamp", "order_delivered_carrier_date",
             "order_delivered_customer_date", "order_estimated_delivery_date"]
    orders = pd.read_csv(DATA / "olist_orders_dataset.csv", parse_dates=dates)
    items = pd.read_csv(DATA / "olist_order_items_dataset.csv")
    products = pd.read_csv(DATA / "olist_products_dataset.csv")
    sellers = pd.read_csv(DATA / "olist_sellers_dataset.csv")
    customers = pd.read_csv(DATA / "olist_customers_dataset.csv")
    log = {"pedidos_na_base": len(orders)}

    orders = orders[orders.order_status == "delivered"].dropna(
        subset=["order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"])
    log["entregues_com_datas"] = len(orders)

    products["volume_cm3"] = products.product_length_cm * products.product_height_cm * products.product_width_cm
    items = items.merge(products[["product_id", "product_weight_g", "volume_cm3"]], on="product_id", how="left")
    per_order = items.groupby("order_id").agg(
        n_sellers=("seller_id", "nunique"), seller_id=("seller_id", "first"), n_items=("order_item_id", "count"),
        weight_g=("product_weight_g", lambda s: s.sum(min_count=len(s))),
        volume_cm3=("volume_cm3", lambda s: s.sum(min_count=len(s))),
    )
    # pedidos com mais de um vendedor saem de lugares diferentes: ficam de fora (~1,3%)
    per_order = per_order[per_order.n_sellers == 1].dropna(subset=["weight_g", "volume_cm3"])

    df = (orders.merge(per_order, on="order_id")
          .merge(sellers[["seller_id", "seller_zip_code_prefix", "seller_state"]], on="seller_id")
          .merge(customers[["customer_id", "customer_zip_code_prefix", "customer_state"]], on="customer_id"))
    log["um_vendedor_e_pacote_completo"] = len(df)

    df = df.join(geo[["lat", "lng"]].add_prefix("origin_"), on="seller_zip_code_prefix")
    df = df.join(geo[["lat", "lng"]].add_prefix("dest_"), on="customer_zip_code_prefix")
    df = df.dropna(subset=["origin_lat", "dest_lat"])
    log["com_coordenadas"] = len(df)

    day = pd.Timedelta(days=1)
    df["transit_days"] = (df.order_delivered_customer_date - df.order_delivered_carrier_date) / day
    # B0: o prazo que a loja prometeu, contado a partir da postagem
    df["b0_days"] = (df.order_estimated_delivery_date - df.order_delivered_carrier_date) / day
    # erros do sistema (entrega antes da postagem) saem; atrasos longos ficam, porque são o que queremos prever
    df = df[df.transit_days >= 0]
    log["sem_tempos_negativos"] = len(df)

    df = df.rename(columns={"seller_state": "origin_state", "customer_state": "dest_state",
                            "order_delivered_carrier_date": "posted_at"})
    df["weight_kg"] = df.weight_g / 1000
    return df.sort_values("posted_at").reset_index(drop=True), log


# --- Modelos --------------------------------------------------------------
def metrics(y, pred):
    err = np.asarray(pred) - np.asarray(y)
    return {
        "MAE": float(np.mean(np.abs(err))),
        "ME": float(np.mean(err)),          # > 0: folga demais (defensivo) · < 0: promete rápido demais (otimista)
        "RMSE": float(np.sqrt(np.mean(err ** 2))),
        "atraso_pct": float(np.mean(err < 0) * 100),  # % das entregas que chegariam depois do prazo previsto
    }


class MeanBaseline:  # B1
    def fit(self, X, y):
        self.mean = float(np.mean(y))
        return self

    def predict(self, X):
        return np.full(len(X), self.mean)


class StatePairBaseline:  # B2
    def fit(self, X, y):
        self.global_mean = float(np.mean(y))
        self.means = pd.Series(np.asarray(y), index=X.index).groupby([X.origin_state, X.dest_state]).mean().to_dict()
        return self

    def predict(self, X):
        return np.array([self.means.get(k, self.global_mean) for k in zip(X.origin_state, X.dest_state)])


def linear_baseline():  # B3: distância, peso e mês do ano
    pre = ColumnTransformer([
        ("mes", OneHotEncoder(handle_unknown="ignore"), ["month"]),
        ("num", "passthrough", ["distance_km", "weight_kg"]),
    ])
    return Pipeline([("pre", pre), ("model", LinearRegression())])


def tree_pre():
    return ColumnTransformer([
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CAT_FEATURES),
        ("num", "passthrough", NUM_FEATURES),
    ])


def random_forest(**p):
    model = RandomForestRegressor(n_estimators=150, max_features=0.5, n_jobs=-1, random_state=SEED, **p)
    return Pipeline([("pre", tree_pre()), ("model", model)])


def gradient_boosting(**p):
    model = HistGradientBoostingRegressor(max_iter=300, categorical_features=list(range(len(CAT_FEATURES))),
                                          random_state=SEED, **p)
    return Pipeline([("pre", tree_pre()), ("model", model)])


RF_GRID = [{"max_depth": d, "min_samples_leaf": l} for d in (12, 20) for l in (5, 20)]
GB_GRID = [{"loss": loss, "learning_rate": lr, "max_leaf_nodes": n}
           for loss in ("squared_error", "absolute_error") for lr in (0.05, 0.1) for n in (31, 63)]


# --- Relatório ------------------------------------------------------------
def md_table(rows, cols):
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    fmt = lambda v: f"{v:.2f}" if isinstance(v, float) else str(v)
    return head + "".join("| " + " | ".join(fmt(r[c]) for c in cols) + " |\n" for r in rows)


def savefig(name):
    plt.tight_layout()
    plt.savefig(FIGS / name, dpi=130)
    plt.close()


def main():
    t0 = time.time()
    FIGS.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(exist_ok=True)

    print("Carregando dados…")
    geo = load_geo()
    df, log = load_dataset(geo)
    X_all, y_all = make_features(df), df.transit_days.to_numpy()

    tr = (df.posted_at < TRAIN_END).to_numpy()
    va = ((df.posted_at >= TRAIN_END) & (df.posted_at < VAL_END)).to_numpy()
    te = ((df.posted_at >= VAL_END) & (df.posted_at < TEST_END)).to_numpy()
    split = {name: {"n": int(m.sum()), "de": str(df.posted_at[m].min().date()), "ate": str(df.posted_at[m].max().date()),
                    "media_dias": float(y_all[m].mean())}
             for name, m in (("treino", tr), ("validacao", va), ("teste", te))}
    print(log, split, sep="\n")

    X_tr, y_tr, X_va, y_va = X_all[tr], y_all[tr], X_all[va], y_all[va]
    trva = tr | va

    # 1) Seleção de hiperparâmetros: treina no treino, compara na validação
    tuning = []
    for family, build, grid in (("Random Forest", random_forest, RF_GRID), ("Gradient Boosting", gradient_boosting, GB_GRID)):
        for params in grid:
            m = build(**params).fit(X_tr, y_tr)
            row = {"modelo": family, "params": ", ".join(f"{k}={v}" for k, v in params.items()),
                   "MAE_treino": metrics(y_tr, m.predict(X_tr))["MAE"], "MAE_validacao": metrics(y_va, m.predict(X_va))["MAE"]}
            row["gap"] = row["MAE_validacao"] - row["MAE_treino"]
            tuning.append({**row, "_params": params})
            print(f"  {family:18s} {row['params']:60s} treino {row['MAE_treino']:.2f}  val {row['MAE_validacao']:.2f}")
    best = {fam: min((r for r in tuning if r["modelo"] == fam), key=lambda r: r["MAE_validacao"])
            for fam in ("Random Forest", "Gradient Boosting")}
    chosen_family = min(best, key=lambda f: best[f]["MAE_validacao"])

    # Linhas de base também avaliadas na validação, para a comparação justa na mesma etapa
    baselines = {"B1 · média geral": MeanBaseline, "B2 · média por par de UFs": StatePairBaseline, "B3 · regressão linear": linear_baseline}
    val_rows = [{"modelo": "B0 · prazo prometido (atual)", **metrics(y_va, df.b0_days[va])}]
    for name, build in baselines.items():
        val_rows.append({"modelo": name, **metrics(y_va, build().fit(X_tr, y_tr).predict(X_va))})
    for fam in best:
        val_rows.append({"modelo": fam, **metrics(y_va, (random_forest if fam == "Random Forest" else gradient_boosting)(
            **best[fam]["_params"]).fit(X_tr, y_tr).predict(X_va))})

    # 2) Teste final: re-treina em treino+validação e avalia uma única vez no teste
    X_trva, y_trva, X_te, y_te = X_all[trva], y_all[trva], X_all[te], y_all[te]
    final = {"B0 · prazo prometido (atual)": None}
    test_preds = {"B0 · prazo prometido (atual)": df.b0_days[te].to_numpy()}
    for name, build in baselines.items():
        final[name] = build().fit(X_trva, y_trva)
        test_preds[name] = final[name].predict(X_te)
    for fam in best:
        final[fam] = (random_forest if fam == "Random Forest" else gradient_boosting)(**best[fam]["_params"]).fit(X_trva, y_trva)
        test_preds[fam] = final[fam].predict(X_te)
    test_rows = [{"modelo": k, **metrics(y_te, p)} for k, p in test_preds.items()]
    model = final[chosen_family]
    pred = test_preds[chosen_family]

    # Prazo seguro: quantil 90% (o pacote chega antes desse prazo em ~9 de cada 10 casos)
    gb_params = {k: v for k, v in best["Gradient Boosting"]["_params"].items() if k != "loss"}
    q90 = gradient_boosting(loss="quantile", quantile=0.9, **gb_params).fit(X_trva, y_trva)
    p90 = q90.predict(X_te)
    b0 = test_preds["B0 · prazo prometido (atual)"]
    safe_rows = [
        {"prazo": "B0 · prazo prometido (atual)", "chega_no_prazo_pct": float(np.mean(y_te <= b0) * 100),
         "folga_media_dias": float(np.mean(b0 - y_te)), "prazo_medio_dias": float(np.mean(b0))},
        {"prazo": "Modelo · prazo seguro (P90)", "chega_no_prazo_pct": float(np.mean(y_te <= p90) * 100),
         "folga_media_dias": float(np.mean(p90 - y_te)), "prazo_medio_dias": float(np.mean(p90))},
    ]

    # 3) Análise de erros no teste
    ev = df[te][["dest_state", "origin_state", "posted_at"]].copy()
    ev["region"] = ev.dest_state.map(REGION)
    ev["distance_km"] = X_te.distance_km.to_numpy()
    ev["real"], ev["pred"], ev["b2"] = y_te, pred, test_preds["B2 · média por par de UFs"]
    ev["abs_err"], ev["err"] = np.abs(pred - y_te), pred - y_te
    ev["b2_abs_err"] = np.abs(ev.b2 - y_te)
    ev["dist_bin"] = pd.cut(ev.distance_km, [-1, 100, 300, 700, 1500, 5000],
                            labels=["até 100 km", "100–300 km", "300–700 km", "700–1500 km", "> 1500 km"])
    ev["mes"] = ev.posted_at.dt.strftime("%Y-%m")
    ev["mesma_uf"] = np.where(ev.origin_state == ev.dest_state, "mesma UF", "UFs diferentes")

    def by(col):
        g = ev.groupby(col, observed=True)
        return [{col: k, "n": int(len(x)), "MAE_modelo": float(x.abs_err.mean()), "MAE_B2": float(x.b2_abs_err.mean()),
                 "ME_modelo": float(x.err.mean())} for k, x in g]

    by_region, by_dist, by_month, by_same = by("region"), by("dist_bin"), by("mes"), by("mesma_uf")
    worst = ev[ev.abs_err >= ev.abs_err.quantile(0.95)]
    worst_share = (worst.region.value_counts(normalize=True) * 100).round(1).to_dict()
    all_share = (ev.region.value_counts(normalize=True) * 100).round(1).to_dict()
    big_delay = float(np.mean(y_te > 30) * 100)

    rng = np.random.default_rng(SEED)
    sample = rng.choice(len(X_te), size=min(4000, len(X_te)), replace=False)
    imp = permutation_importance(model, X_te.iloc[sample], y_te[sample], scoring="neg_mean_absolute_error",
                                 n_repeats=3, random_state=SEED, n_jobs=-1)
    importance = sorted(({"variavel": f, "aumento_MAE": float(v)} for f, v in zip(FEATURES, imp.importances_mean)),
                        key=lambda r: -r["aumento_MAE"])

    # 4) Gráficos
    names = [r["modelo"] for r in test_rows]
    plt.figure(figsize=(8, 4))
    colors = ["#c0392b" if n.startswith("B0") else "#95a5a6" if n.startswith("B") else "#0b8a4a" for n in names]
    bars = plt.barh(names[::-1], [r["MAE"] for r in test_rows][::-1], color=colors[::-1])
    plt.bar_label(bars, fmt="%.2f dias", padding=3)
    plt.xlabel("MAE no teste (dias) · menor é melhor")
    plt.title("Erro médio por modelo (jun–ago/2018)")
    plt.xlim(0, max(r["MAE"] for r in test_rows) * 1.25)
    savefig("01_mae_modelos.png")

    plt.figure(figsize=(8, 4))
    regs = [r["region"] for r in by_region]
    x = np.arange(len(regs))
    plt.bar(x - 0.2, [r["MAE_B2"] for r in by_region], 0.4, label="B2 · média por UFs", color="#95a5a6")
    plt.bar(x + 0.2, [r["MAE_modelo"] for r in by_region], 0.4, label=chosen_family, color="#0b8a4a")
    plt.xticks(x, regs)
    plt.ylabel("MAE (dias)")
    plt.title("Erro por região de destino")
    plt.legend()
    savefig("02_mae_regiao.png")

    plt.figure(figsize=(5.5, 5))
    s = rng.choice(len(y_te), size=min(3000, len(y_te)), replace=False)
    plt.scatter(y_te[s], pred[s], s=6, alpha=0.35, color="#0b8a4a")
    plt.plot([0, 40], [0, 40], "--", color="#555")
    plt.xlim(0, 40); plt.ylim(0, 40)
    plt.xlabel("Dias reais"); plt.ylabel("Dias previstos")
    plt.title("Previsto × real (amostra do teste)")
    savefig("03_previsto_vs_real.png")

    plt.figure(figsize=(8, 4))
    plt.hist(np.clip(pred - y_te, -30, 15), bins=60, color="#0b8a4a", alpha=0.85)
    plt.axvline(0, color="#333", lw=1)
    plt.xlabel("Previsto − real (dias)  ·  à esquerda: atrasou em relação à previsão")
    plt.ylabel("Pedidos")
    plt.title("Distribuição dos erros")
    savefig("04_distribuicao_erros.png")

    plt.figure(figsize=(8, 4.5))
    top = importance[:10][::-1]
    plt.barh([r["variavel"] for r in top], [r["aumento_MAE"] for r in top], color="#0b8a4a")
    plt.xlabel("Quanto o MAE piora ao embaralhar a variável (dias)")
    plt.title("Importância das variáveis")
    savefig("05_importancia.png")

    plt.figure(figsize=(8, 4))
    plt.plot([r["mes"] for r in by_month], [r["MAE_modelo"] for r in by_month], "o-", color="#0b8a4a", label=chosen_family)
    plt.plot([r["mes"] for r in by_month], [r["MAE_B2"] for r in by_month], "o--", color="#95a5a6", label="B2")
    plt.ylabel("MAE (dias)"); plt.title("Erro por mês de postagem (teste)"); plt.legend()
    savefig("06_mae_mes.png")

    # 5) Artefatos
    bundle = {
        "model": model, "q90": q90, "model_name": chosen_family, "features": FEATURES,
        "geo": {"prefixes": geo.index.to_numpy(), "lats": geo.lat.to_numpy(), "lngs": geo.lng.to_numpy(),
                "states": geo.state.to_numpy()},
        "b2_means": {f"{a}-{b}": v for (a, b), v in final["B2 · média por par de UFs"].means.items()},
        "b2_global": final["B2 · média por par de UFs"].global_mean,
        "test_metrics": next(r for r in test_rows if r["modelo"] == chosen_family),
        "trained_at": datetime.now().isoformat(timespec="seconds"), "sklearn_version": sklearn.__version__,
    }
    joblib.dump(bundle, MODELS / "transit_model.joblib", compress=3)

    results = {"filtros": log, "divisao": split, "tuning": [{k: v for k, v in r.items() if k != "_params"} for r in tuning],
               "escolhido": chosen_family, "melhores_params": {f: best[f]["params"] for f in best},
               "validacao": val_rows, "teste": test_rows, "prazo_seguro": safe_rows, "por_regiao": by_region,
               "por_distancia": by_dist, "por_mes": by_month, "por_mesma_uf": by_same, "importancia": importance,
               "piores_5pct_regiao": worst_share, "todas_regiao": all_share, "atrasos_acima_30_dias_pct": big_delay}
    (REPORTS / "metrics.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    write_report(results)
    print(f"\nModelo escolhido: {chosen_family}. Concluído em {time.time() - t0:.0f}s. Veja reports/relatorio.md")


def pct_dict(d):
    return ", ".join(f"{k} {v:.0f}%".replace(".", ",") for k, v in d.items())


def write_report(r):
    test = {row["modelo"]: row for row in r["teste"]}
    chosen = test[r["escolhido"]]
    b0, b2 = test["B0 · prazo prometido (atual)"], test["B2 · média por par de UFs"]
    best_base = min((v for k, v in test.items() if k.startswith("B")), key=lambda v: v["MAE"])
    best_base_name = next(k for k, v in test.items() if v is best_base)
    gain = (1 - chosen["MAE"] / best_base["MAE"]) * 100
    gain_b0 = (1 - chosen["MAE"] / b0["MAE"]) * 100
    tuned = sorted(r["tuning"], key=lambda x: x["MAE_validacao"])
    d = r["divisao"]
    f = r["filtros"]
    reg = sorted(r["por_regiao"], key=lambda x: -x["MAE_modelo"])
    n = lambda v: f"{v:,}".replace(",", ".")

    text = f"""# OptiRoute AI · Entrega 2: modelo supervisionado e validação

**Grupo:** Isadora Marques Gonçalves · João Pedro Propércio · Bruno Ambrósio

> Gerado automaticamente por `ml/train.py`. Os números abaixo vêm do último treino.

## 1. Problema e alvo

Prever o **tempo de trânsito** de um pedido, em dias, entre a **postagem** (entrega à transportadora) e a **chegada ao cliente**.
É uma **regressão supervisionada**: cada pedido histórico da Olist já tem a resposta certa (quantos dias levou).

Só usamos o que se sabe no momento da postagem: UF e coordenadas de origem e destino (pelo prefixo do CEP), distância,
peso, volume, quantidade de itens, mês e dia da semana. O prazo prometido, a data de entrega e a avaliação do cliente
**não entram** como variáveis, porque seriam informação do futuro (vazamento).

## 2. Organização dos dados

| Etapa | Pedidos |
|---|---|
| Pedidos na base | {n(f['pedidos_na_base'])} |
| Entregues e com todas as datas | {n(f['entregues_com_datas'])} |
| Um único vendedor e peso/volume conhecidos | {n(f['um_vendedor_e_pacote_completo'])} |
| CEP de origem e destino com coordenada | {n(f['com_coordenadas'])} |
| Sem tempos negativos (erro de sistema) | {n(f['sem_tempos_negativos'])} |

Mantivemos os atrasos muito longos (outliers): entender por que uma entrega demora é justamente o objetivo.

**Divisão temporal** (pela data de postagem, nunca aleatória):

| Conjunto | Período | Pedidos | Média real (dias) | Uso |
|---|---|---|---|---|
| Treino | {d['treino']['de']} a {d['treino']['ate']} | {n(d['treino']['n'])} | {d['treino']['media_dias']:.1f} | o modelo aprende |
| Validação | {d['validacao']['de']} a {d['validacao']['ate']} | {n(d['validacao']['n'])} | {d['validacao']['media_dias']:.1f} | escolher algoritmo e hiperparâmetros |
| Teste | {d['teste']['de']} a {d['teste']['ate']} | {n(d['teste']['n'])} | {d['teste']['media_dias']:.1f} | nota final, usado **uma única vez** |

Depois de escolher o modelo na validação, ele é re-treinado com treino + validação e avaliado no teste.
Assim simulamos a vida real: o modelo prevê meses que nunca viu.

**Atenção à mudança no tempo:** no período de teste as entregas ficaram bem mais rápidas (média de
{d['teste']['media_dias']:.1f} dias, contra {d['treino']['media_dias']:.1f} no treino). A Olist melhorou a logística em meados de 2018, e a
validação inclui a greve dos caminhoneiros (maio/2018), que deixou tudo mais lento. Por isso o MAE do teste é *menor* que o da validação:
o período é mais "fácil", não é o modelo que piorou ou melhorou. **Os modelos só devem ser comparados dentro do mesmo período.**
Uma divisão aleatória esconderia esse efeito e daria uma nota otimista demais.

## 3. Modelos e justificativa

- **Random Forest**: média de muitas árvores de decisão. É robusto a outliers e captura relações não lineares,
  como "a mesma distância demora mais para o Norte que para o Sul".
- **Gradient Boosting (HistGradientBoosting)**: árvores em sequência, cada uma corrigindo o erro da anterior.
  Costuma ser o mais preciso em dados tabulares, trata as UFs como categoria e treina rápido em ~100 mil linhas.
  Testamos também a perda `absolute_error`, que otimiza diretamente o MAE, a nossa métrica principal.

Hiperparâmetros testados na validação (os 6 melhores de {len(tuned)}):

{md_table(tuned[:6], ["modelo", "params", "MAE_treino", "MAE_validacao", "gap"])}
**Escolhido: {r['escolhido']}** (menor MAE na validação).

## 4. Métricas

- **MAE (principal)**: "em média, erramos o prazo por quantos dias?". Está na unidade do negócio, é fácil de explicar
  ao lojista e não é dominada por poucos atrasos extremos.
- **ME (erro com sinal, previsto − real)**: positivo indica folga demais (perde vendas); negativo indica que promete rápido demais (atrasa).
- **RMSE**: pune erros grandes. Mostra o risco de atrasos que quebram contratos.
- **% de atraso**: fração das entregas que chegariam depois do prazo previsto.

## 5. Comparação com a linha de base

**Validação (mar–mai/2018)**, com modelos treinados só no treino:

{md_table(r['validacao'], ["modelo", "MAE", "ME", "RMSE", "atraso_pct"])}
**Teste (jun–ago/2018)**, com modelos re-treinados em treino + validação. É a nota final:

{md_table(r['teste'], ["modelo", "MAE", "ME", "RMSE", "atraso_pct"])}
![MAE por modelo](figs/01_mae_modelos.png)

- O **{r['escolhido']}** erra em média **{chosen['MAE']:.2f} dias**. É **{gain:.0f}% menos** que a melhor linha de base
  ({best_base_name}, {best_base['MAE']:.2f} dias) e **{gain_b0:.0f}% menos** que o prazo prometido hoje (B0, {b0['MAE']:.2f} dias).
- Nos **dois** períodos, os modelos de ML erram menos que todas as linhas de base. O ganho não depende de um período específico.
  Na validação, Random Forest e Gradient Boosting praticamente empatam. Com a greve a vantagem sobre as bases é menor,
  porque um evento externo domina o erro, e o ME fica **negativo**: os modelos prometeram rápido demais,
  já que nada no histórico indicava a greve.
- O B0 tem ME de **+{b0['ME']:.1f} dias**: é o "erro defensivo". Quase nunca atrasa, mas promete muito mais tempo do que precisa.
- Todos os modelos têm ME positivo no teste: aprenderam com um passado mais lento e ficaram um pouco "pessimistas".
  É o efeito da mudança no tempo, e por isso é preciso re-treinar periodicamente.
- Um modelo que mira o MAE erra para os dois lados, então cerca de {chosen['atraso_pct']:.0f}% das entregas chegariam depois do valor
  previsto. Por isso ele é o **tempo esperado**, não o prazo a prometer. Para prometer, usamos o quantil de 90%:

{md_table(r['prazo_seguro'], ["prazo", "chega_no_prazo_pct", "folga_media_dias", "prazo_medio_dias"])}
O **prazo seguro (P90)** mantém a maioria das entregas dentro do prazo prometendo bem menos dias que o B0.
É o valor prático para o lojista.

## 6. Validação e análise de erros

**Sobreajuste.** A coluna `gap` da tabela de hiperparâmetros (MAE validação − MAE treino) mostra quanto o modelo
"decorou" o treino. Árvores mais profundas e folhas menores aumentam o gap. Por isso escolhemos pela validação, e não pelo treino.
Parte do gap também vem da mudança no tempo: a validação inclui a **greve dos caminhoneiros (maio/2018)**,
que nenhum dado de treino poderia antecipar.

**Por região de destino:**

{md_table(reg, ["region", "n", "MAE_modelo", "MAE_B2", "ME_modelo"])}
![Erro por região](figs/02_mae_regiao.png)

**Por distância:**

{md_table(r['por_distancia'], ["dist_bin", "n", "MAE_modelo", "MAE_B2", "ME_modelo"])}
**Por mês de postagem:**

{md_table(r['por_mes'], ["mes", "n", "MAE_modelo", "MAE_B2", "ME_modelo"])}
![Erro por mês](figs/06_mae_mes.png)

**Onde o modelo mais erra:**
- O erro cresce com a distância e é maior para **{reg[0]['region']}** ({reg[0]['MAE_modelo']:.1f} dias),
  onde há menos pedidos para aprender e a logística é mais irregular.
- Nos 5% piores erros, a participação por região é: {pct_dict(r['piores_5pct_regiao'])}.
  No total do teste, é: {pct_dict(r['todas_regiao'])}. Ou seja, Norte e Nordeste aparecem muito mais entre os piores erros do que no volume total.
- {r['atrasos_acima_30_dias_pct']:.1f}% das entregas do teste levaram mais de 30 dias. São extravios, greves e problemas que nenhuma variável da
  postagem antecipa, e geram os maiores erros e o RMSE alto.

![Previsto x real](figs/03_previsto_vs_real.png)
![Distribuição dos erros](figs/04_distribuicao_erros.png)

**O que o modelo aprendeu** (importância por permutação: quanto o MAE piora ao embaralhar cada variável):

{md_table(r['importancia'][:8], ["variavel", "aumento_MAE"])}
![Importância](figs/05_importancia.png)

## 7. Limitações

- **Período e contexto:** dados de 2016–2018 de um único marketplace. O comportamento das transportadoras muda,
  então o modelo precisa ser re-treinado com dados recentes antes de uso real.
- **Censura no fim da base:** pedidos postados no fim de ago/2018 que demoraram muito ainda não estavam entregues
  quando a base foi extraída, e por isso ficaram de fora. O teste pode parecer um pouco mais "rápido" que a realidade.
- **Sem informação de transportadora, modal ou clima:** os grandes atrasos ficam sem explicação.
- **Precisão geográfica:** usamos o centro do prefixo de 5 dígitos do CEP, e não o endereço exato.
- **Escala do WayHub:** a Olist mede entregas interestaduais em dias. As caronas do WayHub entre centros próximos
  (ex.: Anápolis ➔ Goiânia) levam horas, então a previsão no app representa o prazo do envio tradicional usado como referência.

## 8. Integração com a aplicação

O modelo salvo (`ml/models/transit_model.joblib`) é carregado pela API Flask do WayHub:
`POST /api/predict/transit` recebe CEP de origem, CEP de destino, peso, dimensões e data, e devolve o tempo esperado,
o prazo seguro (P90) e a comparação com a média histórica da rota. A tela **Previsão de prazo** do painel do Centro consome essa rota.
"""
    (REPORTS / "relatorio.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
