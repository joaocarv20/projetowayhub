"""
Arquivo: utils/helpers.py
Função: funções de apoio sem regra de negócio — validações (e-mail, CNPJ), formatação
        (dinheiro, telefone, dias), criptografia de senha e rótulos de status.
"""
import hashlib
import hmac
import math
import os
import re

STATUS_LABEL = {
    "disponivel": "Disponível",
    "solicitado": "Solicitado",
    "em_andamento": "Em andamento",
    "encerrado": "Encerrado",
    "cancelado": "Cancelado",
}


def somente_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def email_valido(email):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or ""))


def cnpj_valido(cnpj):
    c = somente_digitos(cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False

    def digito(base):
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        if len(base) == 13:
            pesos = [6] + pesos
        resto = sum(int(d) * p for d, p in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = digito(c[:12])
    return c[12:] == d1 + digito(c[:12] + d1)


def fmt_tel(t):
    d = somente_digitos(t)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return t or ""


def fmt_brl(valor):
    s = f"{float(valor):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_dias(horas):
    """O cálculo é em horas, mas a apresentação é sempre em dias (arredondado para cima)."""
    if horas is None:
        return "sem histórico"
    dias = max(1, math.ceil(float(horas) / 24))
    return "até 1 dia" if dias == 1 else f"até {dias} dias"


# ---------- senhas (PBKDF2, só biblioteca padrão) ----------
def hash_senha(senha, salt=None):
    salt = salt or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), 120_000).hex()
    return f"{salt}${h}"


def verificar_senha(senha, armazenado):
    salt, h = armazenado.split("$")
    return hmac.compare_digest(hash_senha(senha, salt).split("$")[1], h)
