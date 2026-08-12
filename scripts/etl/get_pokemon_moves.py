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

from pokemon_champions.db import connect

from . import paths
from . import schema
from .parse_utils import get_json, render, mogrify_rows

POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon"

FILENAME = "07_pokemon_moves.sql"
TABLE = "pokemon_moves"
COLUMNS = ["pokemon_name", "move_name"]
DDL = schema.POKEMON_MOVES


def fetch_pokemon(name):
    """PokeAPI에서 포켓몬 하나의 원본 JSON을 받아온다. 실패 시 None."""
    return get_json(f"{POKEAPI_BASE}/{name}")


def build(conn):
    """07_pokemon_moves.sql 전문을 만들어 돌려준다. (포켓몬 수만큼 API 호출)"""
    cur = conn.cursor()

    # 1) DB에 존재하는 유효 기술 목록 (교집합 기준)
    cur.execute("SELECT name FROM moves")
    valid_moves = {row[0] for row in cur.fetchall()}
    print(f"DB 기술 수: {len(valid_moves)}")

    # 2) DB에 존재하는 포켓몬 목록 (대상)
    cur.execute("SELECT name FROM pokemons")
    pokemons = [row[0] for row in cur.fetchall()]
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
            values.append((name, move))

        print(f"{name} - {len(valid)}개")

    print(f"\n연결 {len(values)}행 / 실패: {len(failed)}개 - {failed}")
    return render(schema.POKEMON_MOVES, TABLE, COLUMNS,
                  mogrify_rows(cur, values, len(COLUMNS)))


def main():
    conn = connect()
    paths.SQL_DIR.mkdir(exist_ok=True)
    (paths.SQL_DIR / FILENAME).write_text(build(conn), encoding="utf-8")
    print(f"{FILENAME} 생성 완료")
    conn.close()


if __name__ == "__main__":
    main()
