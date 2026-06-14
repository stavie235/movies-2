"""
database.py — oti exei na kanei me ti vasi einai edo, lowkey to pio boring arxeio

ola ta alla arxeia pernane connection mesa apo get_db() opote an allaksei to path
tis basis to allazoume mono edo kai den psaxnoume pantou, not gonna lie smart move
"""

import sqlite3
from pathlib import Path

# relative sto arxeio ayto opote den xalaei an trekseis apo allo fakelo no cap
DB_PATH = Path(__file__).parent / "movielens.db"


def get_db() -> sqlite3.Connection:
    """
    anoigei connection sti vasi kai to epistrefei.
    to row_factory = sqlite3.Row mas afhnei na grafoume row["title"] anti row[0]
    which is so much better honestly. o caller kleinei to connection meta.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # dict-like access, poly pio readable
    return conn


def fetchall(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """
    trexei SELECT kai epistrefei oles tis grammes.
    ta params mpainoun sta ? — POTE min kaneis f-string mesa sto SQL
    giati SQL injection is not it bestie
    """
    conn = get_db()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def fetchone(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    """SELECT alla mono i proti grammi, None an den vrike tipota"""
    conn = get_db()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> int:
    """
    gia INSERT / UPDATE / DELETE. kanei commit mono tou kai epistrefei
    to id tis grammis pou molis egrapse (lastrowid), pretty useful
    """
    conn = get_db()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
