"""psycopg2 커넥션을 여는 유일한 지점.

── 모듈 최상단에서 connect() 하지 않는다 ──
  import 만 해도 접속이 일어나면 DB 없이는 테스트도 import 도 못 한다.
  커넥션은 진입점(CLI·API·스크립트)에서 한 번 열고 인자로 내려보낸다.
"""

from contextlib import contextmanager

import psycopg2

from ..config import DB_CONFIG


def connect():
    """DB_CONFIG로 psycopg2 커넥션을 연다."""
    return psycopg2.connect(**DB_CONFIG)


@contextmanager
def connection():
    """with 블록을 벗어나면 반드시 닫는다.

        with connection() as conn:
            ...
    """
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
