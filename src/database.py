import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = dict(
    host='127.0.0.1',
    port=3306,
    user='root',
    password='aitrading123',
    database='ai_trading',
    charset='utf8mb4',
    cursorclass=DictCursor,
)


def get_conn():
    return pymysql.connect(**DB_CONFIG)
