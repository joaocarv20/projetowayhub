"""
Arquivo: domain/pedidos.py
Função: classes (POO) do pedido — Pedido (validação e gravação) e CalculadoraTaxa
        (tabela de faixas que define o valor pago ao motorista por tamanho/peso).
"""
from datetime import datetime, timedelta

from config.settings import ANTECEDENCIA_MINIMA_MIN
from database.connection import transaction


class CalculadoraTaxa:
    """Faixas: (nome, peso máx. kg, volume máx. cm³, taxa em R$). Vale a menor faixa que comporta peso E volume."""
    FAIXAS = [
        ("Mini (tipo capinha)", 0.5, 1_500, 0.70),
        ("Pequeno", 2.0, 10_000, 1.50),
        ("Médio", 10.0, 60_000, 3.00),
        ("Grande", 30.0, 200_000, 6.00),
    ]

    @classmethod
    def classificar(cls, peso_kg, volume_cm3):
        for nome, peso_max, vol_max, taxa in cls.FAIXAS:
            if peso_kg <= peso_max and volume_cm3 <= vol_max:
                return nome, taxa
        raise ValueError("Pedido acima do limite do WayHub (máx. 30 kg e 200.000 cm³).")


class Pedido:
    def __init__(self, centro_origem_id, centro_destino_id, descricao,
                 altura, comprimento, largura, peso, retirada_prevista):
        self.centro_origem_id = centro_origem_id
        self.centro_destino_id = centro_destino_id
        self.descricao = (descricao or "").strip()
        self.altura, self.comprimento, self.largura = float(altura), float(comprimento), float(largura)
        self.peso = float(peso)
        self.retirada_prevista = retirada_prevista

    @property
    def volume(self):
        return self.altura * self.comprimento * self.largura

    def classificar(self):
        return CalculadoraTaxa.classificar(self.peso, self.volume)

    def validar(self):
        erros = []
        if not self.descricao:
            erros.append("Descreva o pedido.")
        if not self.centro_destino_id:
            erros.append("Escolha o centro logístico de destino.")
        elif self.centro_destino_id == self.centro_origem_id:
            erros.append("O destino precisa ser diferente da origem.")
        if min(self.altura, self.comprimento, self.largura, self.peso) <= 0:
            erros.append("Altura, comprimento, largura e peso precisam ser maiores que zero.")
        else:
            try:
                self.classificar()
            except ValueError as e:
                erros.append(str(e))
        if self.retirada_prevista < datetime.now() + timedelta(minutes=ANTECEDENCIA_MINIMA_MIN):
            erros.append(f"A retirada precisa ser daqui a pelo menos {ANTECEDENCIA_MINIMA_MIN} minutos "
                         "para que um motorista consiga solicitar.")
        return erros

    def salvar(self):
        erros = self.validar()
        if erros:
            raise ValueError("\n".join(erros))
        categoria, taxa = self.classificar()
        with transaction() as cur:
            cur.execute("SELECT COALESCE(MAX(seq_centro),0)+1 AS prox FROM pedidos WHERE centro_origem_id=%s",
                        (self.centro_origem_id,))
            seq = cur.fetchone()["prox"]
            codigo = f"WH-{self.centro_origem_id:03d}-{seq:05d}"
            cur.execute(
                """INSERT INTO pedidos (codigo_pedido, seq_centro, centro_origem_id, centro_destino_id,
                       descricao, altura_cm, comprimento_cm, largura_cm, peso_kg, categoria, taxa,
                       retirada_prevista)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (codigo, seq, self.centro_origem_id, self.centro_destino_id, self.descricao,
                 self.altura, self.comprimento, self.largura, self.peso, categoria, taxa,
                 self.retirada_prevista))
        return codigo
