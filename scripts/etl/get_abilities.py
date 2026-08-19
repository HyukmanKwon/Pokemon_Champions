"""
포챔스 포켓몬들이 가진 특성 목록을 PokeAPI에서 받아,
abilities 테이블용 05_abilities.sql 을 생성한다.

핵심:
  - 대상 특성 목록 = DB의 pokemon_abilities 에서 중복 없이 SELECT
    (포켓몬 목록이 바뀌면 특성 목록도 자동으로 따라간다)
  - 따라서 03_pokemons.sql 이 DB에 올라간 뒤에 실행돼야 한다.
    build.py 는 생성과 실행을 번갈아 하므로 순서가 저절로 맞는다.
"""

from . import schema
from .parse_utils import (collect, endpoint, korean, pick_english_effect,
                          sql_of, to_values)

POKEAPI_BASE = "https://pokeapi.co/api/v2/ability"
KO_OVERRIDE_KEY = "ability_ko_names"

TABLE = "abilities"
COLUMNS = ["id", "name", "ko_name", "description", "effect"]


fetch_ability = endpoint(POKEAPI_BASE)


def parse_ability(data):
    # PokeAPI 에 한국어가 없는 신규 특성이 있고, flavor text 도 옛 표현이거나
    # 잘려 있는 경우가 있다. annotator 로 손본 값을 덮어씌워서 재구축해도
    # 사라지지 않게 한다.
    ko = korean(data, KO_OVERRIDE_KEY)

    return {
        "id": data["id"],
        "name": data["name"],
        "ko_name": ko["ko_name"],
        "description": ko["description"],
        "effect": pick_english_effect(data["effect_entries"]),
    }


def select_ability_names(cur):
    """pokemon_abilities 에 쓰인 특성 이름을 중복 없이. (03 단계가 채운다)"""
    cur.execute(
        "SELECT DISTINCT ability_name FROM pokemon_abilities ORDER BY 1")
    return [row[0] for row in cur.fetchall()]


def build(conn):
    """05_abilities.sql 전문을 만들어 돌려준다. (특성 수만큼 API 호출)"""
    cur = conn.cursor()
    abilities = select_ability_names(cur)
    print(f"DB 특성 수: {len(abilities)}")

    rows = collect(abilities, fetch_ability, parse_ability)
    return sql_of(cur, TABLE, COLUMNS, to_values(rows, COLUMNS))


