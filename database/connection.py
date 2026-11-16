"""
Arquivo: database/connection.py
Função: conexão com o MySQL e helpers de consulta (query), escrita (execute) e
        transação (transaction) usados por todo o sistema.
"""
from contextlib import contextmanager

import mysql.connector

from config.settings import DB_CONFIG


def get_conn():
    return mysql.connector.connect(**DB_CONFIG)


def query(sql, params=None, one=False):
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        if one:
            return rows[0] if rows else None
        return rows
    finally:
        conn.close()


def execute(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


@contextmanager
def transaction():
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
