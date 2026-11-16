"""
Arquivo: config/settings.py
Função: centraliza as configurações do WayHub — conexão com o MySQL (lida do .env),
        regras de negócio (prazos e taxa mínima), listas fixas e caminhos/parâmetros do ML.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

# ---------- Banco de dados (o mesmo servidor do MySQL Workbench) ----------
DB_CONFIG = {
    "host": os.getenv("WAYHUB_DB_HOST", "localhost"),
    "port": int(os.getenv("WAYHUB_DB_PORT", "3306")),
    "user": os.getenv("WAYHUB_DB_USER", "root"),
    "password": os.getenv("WAYHUB_DB_PASSWORD", ""),
    "database": os.getenv("WAYHUB_DB_NAME", "wayhub"),
}

# ---------- Regras de negócio ----------
ANTECEDENCIA_MINIMA_MIN = 40   # solicitar a carona no mínimo 40 min antes da retirada
TOLERANCIA_ATRASO_MIN = 15     # passou disso sem retirada, o pedido volta a ficar disponível
TAXA_MINIMA_CARONA = 5.00      # soma mínima das taxas dos pedidos de uma carona

TIPOS_VEICULO = ["Moto", "Carro", "Van", "Utilitário / Caminhonete"]
OUTRA_CIDADE = "Outra cidade..."
CIDADES = [
    "Anápolis - GO", "Goiânia - GO", "Brasília - DF", "Aparecida de Goiânia - GO",
    "Trindade - GO", "Senador Canedo - GO", "Inhumas - GO", "Goianésia - GO",
    "Ceres - GO", "Uruaçu - GO", "Pirenópolis - GO", "Luziânia - GO",
    "Valparaíso de Goiás - GO", "Águas Lindas de Goiás - GO", "Formosa - GO",
    "Planaltina - GO", "Catalão - GO", "Rio Verde - GO", "Itumbiara - GO",
    "Caldas Novas - GO", "Uberlândia - MG", "Palmas - TO",
]

# ---------- Machine Learning (previsão do tempo de entrega) ----------
DIR_DADOS = RAIZ / "data"
JSON_METRICAS = DIR_DADOS / "metricas_modelo.json"     # gerado a cada treino (base de treino: tabela historico_entregas)
ML_MINIMO_LINHAS = 10          # abaixo disso a IA usa uma estimativa simples (sem modelo)
ML_TEMPO_MINIMO_HORAS = 0.5    # entregas do MySQL mais rápidas que isso são testes e não treinam a IA
