import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(
    host='127.0.0.1', port=3306, user='root',
    password='aitrading123', database='ai_trading',
    charset='utf8mb4',
)


def get_conn():
    return pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)


def query(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def query_one(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()
    finally:
        conn.close()


def execute(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
            return cur.rowcount
    finally:
        conn.close()
