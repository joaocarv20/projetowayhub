"""
Arquivo: ml/preparacao_dados.py
Função: lê e padroniza os dados de treino (tabela historico_entregas + entregas encerradas do MySQL) e transforma
        cada entrega nas variáveis (features) que a IA usa: distância, peso, volume, dia da semana e hora.
"""
import pandas as pd

from config.settings import ML_TEMPO_MINIMO_HORAS
from database.connection import query
from ml.geografia import distancia_km

COLUNAS = ["cidade_origem", "cidade_destino", "distancia_km", "peso_kg",
           "altura_cm", "comprimento_cm", "largura_cm", "retirado_em", "entregue_em"]
NUMERICAS = ["distancia_km", "peso_kg", "altura_cm", "comprimento_cm", "largura_cm"]
FEATURES = ["distancia_km", "peso_kg", "volume_cm3", "dia_semana", "hora_retirada"]


def _numero(serie):
    return pd.to_numeric(serie.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _padronizar(df):
    """Converte tipos, completa a distância (se vazia) e calcula tempo_horas = entregue_em - retirado_em."""
    df = df.copy()
    for c in COLUNAS:
        if c not in df.columns:
            df[c] = None
    for c in NUMERICAS:
        df[c] = _numero(df[c])
    df["retirado_em"] = pd.to_datetime(df["retirado_em"], errors="coerce")
    df["entregue_em"] = pd.to_datetime(df["entregue_em"], errors="coerce")
    vazias = df["distancia_km"].isna()
    if vazias.any():
        estimadas = [distancia_km(o, d) for o, d in zip(df.loc[vazias, "cidade_origem"], df.loc[vazias, "cidade_destino"])]
        df.loc[vazias, "distancia_km"] = pd.Series(estimadas, index=df.index[vazias], dtype="float64")
    df["tempo_horas"] = (df["entregue_em"] - df["retirado_em"]).dt.total_seconds() / 3600
    df = df.dropna(subset=NUMERICAS + ["retirado_em", "entregue_em", "tempo_horas"])
    return df[df["tempo_horas"] > 0][COLUNAS + ["tempo_horas"]].reset_index(drop=True)


def carregar_historico_treino():
    """Base de treino inicial: tabela historico_entregas (você insere/importa os dados no Workbench)."""
    linhas = query("SELECT cidade_origem, cidade_destino, distancia_km, peso_kg, altura_cm, comprimento_cm, "
                   "largura_cm, retirado_em, entregue_em FROM historico_entregas")
    return _padronizar(pd.DataFrame(linhas, columns=COLUNAS))


def carregar_entregas_mysql():
    """Entregas reais já encerradas no WayHub. Entregas muito rápidas (testes) são descartadas."""
    linhas = query("""SELECT o.cidade AS cidade_origem, d.cidade AS cidade_destino, p.peso_kg,
                             p.altura_cm, p.comprimento_cm, p.largura_cm, p.retirado_em, p.entregue_em
                      FROM pedidos p
                      JOIN centros o ON o.usuario_id = p.centro_origem_id
                      JOIN centros d ON d.usuario_id = p.centro_destino_id
                      WHERE p.status='encerrado' AND p.retirado_em IS NOT NULL AND p.entregue_em IS NOT NULL""")
    df = _padronizar(pd.DataFrame(linhas, columns=["cidade_origem", "cidade_destino", "peso_kg", "altura_cm",
                                                   "comprimento_cm", "largura_cm", "retirado_em", "entregue_em"]))
    return df[df["tempo_horas"] >= ML_TEMPO_MINIMO_HORAS].reset_index(drop=True)


def versao_dados():
    """'Impressão digital' da base de treino: muda sempre que uma entrega é encerrada no WayHub ou a tabela
    historico_entregas é alterada. Quando muda, a IA se retreina sozinha (aprendizado contínuo)."""
    r = query("""SELECT (SELECT COUNT(*) FROM historico_entregas) AS h, COUNT(*) AS n, MAX(entregue_em) AS m
                 FROM pedidos WHERE status='encerrado'""", one=True)
    return f"{r['h']}-{r['n']}-{r['m']}"


def montar_features(df):
    """Uma linha por entrega -> tabela numérica que entra no modelo."""
    retirada = pd.to_datetime(df["retirado_em"])
    return pd.DataFrame({
        "distancia_km": df["distancia_km"].astype(float),
        "peso_kg": df["peso_kg"].astype(float),
        "volume_cm3": (df["altura_cm"].astype(float) * df["comprimento_cm"].astype(float)
                       * df["largura_cm"].astype(float)),
        "dia_semana": retirada.dt.dayofweek,
        "hora_retirada": retirada.dt.hour,
    })[FEATURES]
