"""
Arquivo: ml/geografia.py
Função: coordenadas das cidades do WayHub e cálculo da distância estimada por estrada (km),
        usada como variável da IA quando a distância não é informada.
"""
from math import asin, cos, radians, sin, sqrt

FATOR_ESTRADA = 1.25      # a estrada é ~25% mais longa que a linha reta
DISTANCIA_MESMA_CIDADE = 10.0

COORDENADAS = {  # (latitude, longitude) — as chaves são os mesmos nomes de CIDADES em config/settings.py
    "Anápolis - GO": (-16.3267, -48.9528), "Goiânia - GO": (-16.6869, -49.2648),
    "Brasília - DF": (-15.7939, -47.8828), "Aparecida de Goiânia - GO": (-16.8198, -49.2469),
    "Trindade - GO": (-16.6517, -49.4925), "Senador Canedo - GO": (-16.7084, -49.0914),
    "Inhumas - GO": (-16.3589, -49.4958), "Goianésia - GO": (-15.3125, -49.1175),
    "Ceres - GO": (-15.3067, -49.5989), "Uruaçu - GO": (-14.5238, -49.1411),
    "Pirenópolis - GO": (-15.8514, -48.9586), "Luziânia - GO": (-16.2525, -47.9500),
    "Valparaíso de Goiás - GO": (-16.0651, -47.9787), "Águas Lindas de Goiás - GO": (-15.7617, -48.2814),
    "Formosa - GO": (-15.5400, -47.3347), "Planaltina - GO": (-15.4525, -47.6086),
    "Catalão - GO": (-18.1656, -47.9440), "Rio Verde - GO": (-17.7923, -50.9192),
    "Itumbiara - GO": (-18.4094, -49.2158), "Caldas Novas - GO": (-17.7441, -48.6246),
    "Uberlândia - MG": (-18.9186, -48.2772), "Palmas - TO": (-10.1689, -48.3317),
}


def distancia_km(origem, destino):
    """Distância estimada por estrada; None se alguma cidade não estiver na tabela."""
    if origem == destino:
        return DISTANCIA_MESMA_CIDADE
    if origem not in COORDENADAS or destino not in COORDENADAS:
        return None
    la1, lo1 = map(radians, COORDENADAS[origem])
    la2, lo2 = map(radians, COORDENADAS[destino])
    a = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return round(2 * 6371 * asin(sqrt(a)) * FATOR_ESTRADA, 1)
