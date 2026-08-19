"""
포켓몬별 습득 기술을 PokeAPI에서 받아,
DB에 실제로 존재하는 포켓몬/기술과 대조한 뒤
pokemon_moves 연결 테이블용 07_pokemon_moves.sql 을 생성한다.

핵심:
  - 대상 포켓몬 목록 = DB의 pokemons 테이블에서 SELECT
  - 유효 기술 목록   = DB의 moves 테이블에서 SELECT
  - PokeAPI가 준 습득 기술 중, 위 유효 기술과 겹치는 것만 저장
  - 따라서 03_pokemons.sql / 04_moves.sql 이 DB에 올라간 뒤에 실행돼야 한다.
"""

from . import schema
from .parse_utils import endpoint, sql_of

POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon"

TABLE = "pokemon_moves"
COLUMNS = ["pokemon_id", "move_id"]


# collect() 를 쓰지 않는다. 이름 하나가 행 수십 개가 되고 ko_name 도 없어서,
# 끼워 넣으면 collect 에 이 생성기 전용 분기가 둘 생긴다. (parse_utils 참고)
fetch_pokemon = endpoint(POKEAPI_BASE)


def build(conn):
    """07_pokemon_moves.sql 전문을 만들어 돌려준다. (포켓몬 수만큼 API 호출)"""
    cur = conn.cursor()

    # 1) DB에 존재하는 유효 기술 목록 (교집합 기준)
    cur.execute("SELECT name, id FROM moves")
    move_id = dict(cur.fetchall())
    valid_moves = set(move_id)
    print(f"DB 기술 수: {len(valid_moves)}")

    # 2) DB에 존재하는 포켓몬 목록 (대상). 표에는 id 로 넣으므로 같이 읽는다.
    cur.execute("SELECT name, id FROM pokemons")
    pokemon_id = dict(cur.fetchall())
    pokemons = list(pokemon_id)
    print(f"DB 포켓몬 수: {len(pokemons)}")

    failed = []
    values = []
    for name in pokemons:
        data = fetch_pokemon(name)
        if data is None:
            failed.append(name)
            print(f"{name} - failed")
            continue

        # PokeAPI가 준 습득 기술 전체
        learned = {m["move"]["name"] for m in data["moves"]}
        # DB에 있는 유효 기술과의 교집합만 저장
        valid = learned & valid_moves

        for move in sorted(valid):
            values.append((pokemon_id[name], move_id[move]))

        print(f"{name} - {len(valid)}개")

    print(f"\n연결 {len(values)}행 / 실패: {len(failed)}개 - {failed}")
    return sql_of(cur, TABLE, COLUMNS, values)

