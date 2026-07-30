"""DB 접속 설정과 경로 상수."""

import os
import psycopg2
from pathlib import Path

DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE", "pokemon"),
    "user": os.getenv("PGUSER", "hyukman"),
    "password": os.getenv("PGPASSWORD", ""),
}

# database/            <- 이 파일이 있는 곳
BASE_DIR = Path(__file__).resolve().parent
# database/sql/        <- main.py가 만들어 SQL 파일을 쌓아두는 곳
SQL_DIR = BASE_DIR / "sql"
# ../sql/              <- 이미 만들어져 있는 SQL (API 재호출을 피하기 위한 씨앗)
BASELINE_DIR = BASE_DIR.parent / "sql"


def connect():
    """DB_CONFIG로 psycopg2 커넥션을 연다."""
    return psycopg2.connect(**DB_CONFIG)
