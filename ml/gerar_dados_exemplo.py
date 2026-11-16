"""
Arquivo: ml/gerar_dados_exemplo.py
Função: gera a base de treino da IA com entregas FICTÍCIAS (800 linhas), em dois formatos com os MESMOS dados:
        database/dados_treino_exemplo.sql (rodar no Workbench) e data/entregas_historico.csv (CSV).
        Uso:  python -m ml.gerar_dados_exemplo
"""
import csv
import random
from datetime import datetime, timedelta

from config.settings import RAIZ
from ml.geografia import COORDENADAS, distancia_km

N_LINHAS = 800
COLUNAS = ["cidade_origem", "cidade_destino", "distancia_km", "peso_kg", "altura_cm",
           "comprimento_cm", "largura_cm", "retirado_em", "entregue_em"]

random.seed(42)
cidades = list(COORDENADAS)
linhas = []
for _ in range(N_LINHAS):
    o, d = random.sample(cidades, 2)
    km = distancia_km(o, d)
    retirada = datetime(2026, 1, 5) + timedelta(days=random.randint(0, 270), hours=random.randint(7, 20),
                                                 minutes=random.choice([0, 15, 30, 45]))
    peso = round(random.choice([0.1, 0.3, 0.8, 1.5, 4, 8, 15, 25]) * random.uniform(0.8, 1.2), 2)
    alt, comp, larg = (round(random.uniform(2, 50), 1) for _ in range(3))
    horas = 3 + km / 55 + peso * 0.05 + random.uniform(-1, 2)      # operação + estrada + carga
    if retirada.hour >= 16:
        horas += 12                                                 # sai só no dia seguinte
    if retirada.weekday() == 5:
        horas += 18                                                 # sábado
    if retirada.weekday() == 6:
        horas += 30                                                 # domingo
    entrega = retirada + timedelta(hours=horas)
    linhas.append([o, d, km, peso, alt, comp, larg, f"{retirada:%Y-%m-%d %H:%M:00}", f"{entrega:%Y-%m-%d %H:%M:00}"])

# ---------- script SQL para o MySQL Workbench ----------
cab = ("-- Arquivo: database/dados_treino_exemplo.sql\n"
       f"-- Função: insere {N_LINHAS} entregas FICTÍCIAS em historico_entregas (só para o protótipo; troque pelos dados reais).\n"
       "-- Rode DEPOIS do schema.sql.\nSET NAMES utf8mb4;\nUSE wayhub;\nDELETE FROM historico_entregas;\n")
blocos = []
for i in range(0, len(linhas), 100):
    corpo = ",\n".join("('{}','{}',{},{},{},{},{},'{}','{}')".format(*l) for l in linhas[i:i + 100])
    blocos.append("INSERT INTO historico_entregas (cidade_origem, cidade_destino, distancia_km, peso_kg, altura_cm, "
                  "comprimento_cm, largura_cm, retirado_em, entregue_em) VALUES\n" + corpo + ";\n")
destino_sql = RAIZ / "database" / "dados_treino_exemplo.sql"
destino_sql.write_text(cab + "\n".join(blocos), encoding="utf-8")

# ---------- o mesmo conteúdo em CSV ----------
(RAIZ / "data").mkdir(exist_ok=True)
destino_csv = RAIZ / "data" / "entregas_historico.csv"
with destino_csv.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(COLUNAS)
    w.writerows(linhas)

print(f"{len(linhas)} linhas gravadas em:\n  {destino_sql}\n  {destino_csv}")
