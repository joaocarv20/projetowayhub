"""
Arquivo: ml/previsao.py
Função: PrevisorEntrega — treina a IA ao iniciar e prevê o tempo de entrega (em horas) de um ou
        vários pedidos. A apresentação em dias é feita por utils.helpers.fmt_dias.
"""
import pandas as pd

from ml.geografia import distancia_km
from ml.preparacao_dados import montar_features
from ml.treinamento import treinar


def item_de_pedido(p):
    """Converte uma linha de pedido do MySQL no formato que o previsor entende."""
    return {"origem_cidade": p["origem_cidade"], "destino_cidade": p["destino_cidade"],
            "peso_kg": p["peso_kg"], "altura_cm": p["altura_cm"], "comprimento_cm": p["comprimento_cm"],
            "largura_cm": p["largura_cm"], "retirada": p.get("retirado_em") or p["retirada_prevista"]}


class PrevisorEntrega:
    def __init__(self, resultado):
        self.res = resultado

    @classmethod
    def treinar_agora(cls):
        return cls(treinar())

    def prever_horas(self, itens):
        """itens: lista de dicts (origem_cidade, destino_cidade, peso_kg, altura_cm, comprimento_cm,
        largura_cm, retirada). Devolve uma lista de horas, na mesma ordem."""
        if not itens:
            return []
        dist = []
        for i in itens:
            d = distancia_km(i["origem_cidade"], i["destino_cidade"])
            dist.append(self.res.distancia_padrao if d is None else d)
        if self.res.modelo is None:  # poucos dados: 3 h de operação + 50 km/h
            return [3.0 + d / 50.0 for d in dist]
        df = pd.DataFrame({"distancia_km": dist,
                           "peso_kg": [float(i["peso_kg"]) for i in itens],
                           "altura_cm": [float(i["altura_cm"]) for i in itens],
                           "comprimento_cm": [float(i["comprimento_cm"]) for i in itens],
                           "largura_cm": [float(i["largura_cm"]) for i in itens],
                           "retirado_em": [i["retirada"] for i in itens]})
        return [float(h) for h in self.res.modelo.predict(montar_features(df))]

    def resumo(self):
        r = self.res
        if r.modelo is None:
            return f"IA em modo simples ({r.n_total} entregas; preciso de pelo menos 10)"
        erro = f" · erro médio ±{r.mae_horas:.1f} h" if r.mae_horas is not None else ""
        return f"IA treinada com {r.n_total} entregas ({r.n_historico} do histórico + {r.n_mysql} do WayHub){erro}"
