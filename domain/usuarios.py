"""
Arquivo: domain/usuarios.py
Função: classes (POO) dos usuários do WayHub — Usuario (abstrata), Motorista,
        CentroLogistico e Veiculo — com validação, cadastro e login.
"""
import re
from abc import ABC, abstractmethod
from datetime import datetime

import mysql.connector

from database.connection import query, transaction
from utils.helpers import (cnpj_valido, email_valido, hash_senha,
                           somente_digitos, verificar_senha)


class Usuario(ABC):
    TIPO = ""

    def __init__(self, email, senha, telefone):
        self.id = None
        self.__email = (email or "").strip().lower()   # atributos privados (encapsulamento)
        self.__senha = senha or ""
        self.telefone = somente_digitos(telefone)

    @property
    def email(self):
        return self.__email

    def validar(self):
        erros = []
        if not email_valido(self.__email):
            erros.append("E-mail inválido.")
        if len(self.__senha) < 6:
            erros.append("A senha precisa ter pelo menos 6 caracteres.")
        if len(self.telefone) not in (10, 11):
            erros.append("Telefone inválido (use DDD + número).")
        return erros + self._validar_especifico()

    @abstractmethod
    def _validar_especifico(self):
        """Cada perfil valida seus próprios campos (polimorfismo)."""

    @abstractmethod
    def _inserir_perfil(self, cur, usuario_id):
        """Cada perfil grava seus próprios dados (polimorfismo)."""

    def cadastrar(self):
        erros = self.validar()
        if erros:
            raise ValueError("\n".join(erros))
        try:
            with transaction() as cur:
                cur.execute("SELECT id FROM usuarios WHERE email=%s", (self.__email,))
                if cur.fetchone():
                    raise ValueError("Este e-mail já está cadastrado.")
                cur.execute(
                    "INSERT INTO usuarios (tipo, email, senha_hash, telefone) VALUES (%s,%s,%s,%s)",
                    (self.TIPO, self.__email, hash_senha(self.__senha), self.telefone))
                self.id = cur.lastrowid
                self._inserir_perfil(cur, self.id)
        except mysql.connector.errors.IntegrityError:
            raise ValueError("CNPJ ou placa já cadastrados no WayHub.")
        return self.id

    @staticmethod
    def autenticar(email, senha):
        u = query("SELECT * FROM usuarios WHERE email=%s", ((email or "").strip().lower(),), one=True)
        if not u or not verificar_senha(senha or "", u["senha_hash"]):
            return None
        if u["tipo"] == "motorista":
            p = query("SELECT nome, sobrenome FROM motoristas WHERE usuario_id=%s", (u["id"],), one=True)
            nome = f"{p['nome']} {p['sobrenome']}"
        else:
            nome = query("SELECT nome FROM centros WHERE usuario_id=%s", (u["id"],), one=True)["nome"]
        return {"id": u["id"], "tipo": u["tipo"], "email": u["email"], "nome": nome}


class Veiculo:
    def __init__(self, tipo, modelo, placa, ano):
        self.tipo = tipo
        self.modelo = (modelo or "").strip()
        self.placa = re.sub(r"[^A-Za-z0-9]", "", placa or "").upper()
        self.ano = int(ano or 0)

    def validar(self):
        erros = []
        if not self.modelo:
            erros.append("Informe o modelo do veículo.")
        if not re.fullmatch(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", self.placa):
            erros.append("Placa inválida (exemplo: ABC1D23).")
        if not (1980 <= self.ano <= datetime.now().year + 1):
            erros.append("Ano do veículo inválido.")
        return erros

    def salvar(self, cur, motorista_id):
        cur.execute("INSERT INTO veiculos (motorista_id, tipo, modelo, placa, ano) VALUES (%s,%s,%s,%s,%s)",
                    (motorista_id, self.tipo, self.modelo, self.placa, self.ano))


class Motorista(Usuario):
    TIPO = "motorista"

    def __init__(self, email, senha, telefone, nome, sobrenome, cidade_origem, endereco, veiculo):
        super().__init__(email, senha, telefone)
        self.nome = (nome or "").strip()
        self.sobrenome = (sobrenome or "").strip()
        self.cidade_origem = (cidade_origem or "").strip()
        self.endereco = (endereco or "").strip()
        self.veiculo = veiculo

    def _validar_especifico(self):
        erros = []
        if not self.nome or not self.sobrenome:
            erros.append("Informe nome e sobrenome.")
        if not self.cidade_origem:
            erros.append("Informe a cidade de origem.")
        if not self.endereco:
            erros.append("Informe o endereço de moradia.")
        return erros + self.veiculo.validar()

    def _inserir_perfil(self, cur, usuario_id):
        cur.execute("INSERT INTO motoristas (usuario_id, nome, sobrenome, cidade_origem, endereco) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (usuario_id, self.nome, self.sobrenome, self.cidade_origem, self.endereco))
        self.veiculo.salvar(cur, usuario_id)


class CentroLogistico(Usuario):
    TIPO = "centro"

    def __init__(self, email, senha, telefone, nome, cnpj, cidade, bairro, logradouro, numero):
        super().__init__(email, senha, telefone)
        self.nome = (nome or "").strip()
        self.cnpj = somente_digitos(cnpj)
        self.cidade = (cidade or "").strip()
        self.bairro = (bairro or "").strip()
        self.logradouro = (logradouro or "").strip()
        self.numero = (numero or "").strip()

    def _validar_especifico(self):
        erros = []
        if not self.nome:
            erros.append("Informe o nome do centro logístico.")
        if not cnpj_valido(self.cnpj):
            erros.append("CNPJ inválido.")
        if not (self.cidade and self.bairro and self.logradouro and self.numero):
            erros.append("Preencha cidade, bairro, rua e número do endereço.")
        return erros

    def _inserir_perfil(self, cur, usuario_id):
        cur.execute("INSERT INTO centros (usuario_id, nome, cnpj, cidade, bairro, logradouro, numero) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (usuario_id, self.nome, self.cnpj, self.cidade, self.bairro, self.logradouro, self.numero))
