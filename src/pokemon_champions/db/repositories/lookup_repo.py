"""영문 이름 -> 한국어 이름 대응표.

── 왜 따로 있나 ──
  채용률 데이터가 전부 영문으로 온다(Earthquake, Focus Sash, Rough Skin).
  화면과 도우미는 한국어로 말하므로 어딘가에서 바꿔야 하는데, 기술 열 개를
  하나씩 물으면 쿼리가 열 번 나간다. 표를 통째로 한 번 받아 메모리에서
  맞추는 편이 낫다 — moves 498줄, items 166줄, abilities 200줄 남짓이라
  전부 들고 있어도 문제가 없다.

── 왜 테이블 이름을 인자로 받나 ──
  네 테이블의 모양이 (name, ko_name) 으로 같다. 함수를 넷으로 나누면 거의
  같은 파일이 네 벌이 된다. 대신 아무 이름이나 받으면 SQL 주입이 되므로
  허용 목록 밖은 거부한다.
"""

# {테이블: 영문 이름이 든 컬럼}. 성격만 en_name 이다 — 그 테이블은 이름이
# ENUM 이라 name 이라는 컬럼이 아예 없다.
TABLES = {
    "moves": "name",
    "items": "name",
    "abilities": "name",
    "pokemons": "name",
    "pokemon_natures": "en_name",
}


def fetch_id_map(conn, table):
    """{영문 이름: 기본키}. 채용률이 저쪽 이름을 우리 것으로 옮길 때 쓴다.

    성격만 값이 정수가 아니라 enum 문자열이다 — pokemon_natures 의
    기본키가 en_name 이라 정수 id 가 아예 없다.
    """
    column = TABLES.get(table)
    if column is None:
        raise ValueError(f"허용되지 않은 테이블입니다: {table}")
    key = "en_name" if table == "pokemon_natures" else "id"
    cur = conn.cursor()
    cur.execute(f"SELECT {column}, {key} FROM {table}")
    return dict(cur.fetchall())


def fetch_ko_map(conn, table):
    """{영문 이름: 한국어 ko_name}. 한국어가 없는 행은 뺀다."""
    column = TABLES.get(table)
    if column is None:
        raise ValueError(f"허용되지 않은 테이블입니다: {table}")
    cur = conn.cursor()
    cur.execute(
        f"SELECT {column}, ko_name FROM {table} WHERE ko_name IS NOT NULL")
    return dict(cur.fetchall())
