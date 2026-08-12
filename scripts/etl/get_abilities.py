"""
포챔스 포켓몬들이 가진 특성 목록을 PokeAPI에서 받아,
abilities 테이블용 05_abilities.sql 을 생성한다.

핵심:
  - 대상 특성 목록 = DB의 pokemons 테이블 ability1/2/3 에서 중복 없이 SELECT
    (포켓몬 목록이 바뀌면 특성 목록도 자동으로 따라간다)
  - 따라서 03_pokemons.sql 이 DB에 올라간 뒤에 실행돼야 한다.
    build.py 는 생성과 실행을 번갈아 하므로 순서가 저절로 맞는다.
"""

from . import overrides
from . import schema
from .parse_utils import (get_json, pick_korean, pick_korean_flavor,
                         pick_english_effect, render, mogrify_rows)

POKEAPI_BASE = "https://pokeapi.co/api/v2/ability"
KO_OVERRIDE_KEY = "ability_ko_names"

FILENAME = "05_abilities.sql"
TABLE = "abilities"
COLUMNS = ["id", "name", "ko_name", "description", "effect"]
DDL = schema.ABILITIES


def fetch_ability(name):
    """PokeAPI에서 특성 하나의 원본 JSON을 받아온다. 실패 시 None."""
    return get_json(f"{POKEAPI_BASE}/{name}")


def parse_ability(data):
    # PokeAPI 에 한국어가 없는 신규 특성이 있고, flavor text 도 옛 표현이거나
    # 잘려 있는 경우가 있다. annotator 로 손본 값을 덮어씌워서 재구축해도
    # 사라지지 않게 한다.
    #   python -m scripts.etl.annotator.ko_names abilities
    ko = {
        "ko_name": pick_korean(data["names"]),
        "description": pick_korean_flavor(data["flavor_text_entries"]),
    }
    overrides.apply(KO_OVERRIDE_KEY, data["name"], ko)

    return {
        "id": data["id"],
        "name": data["name"],
        "ko_name": ko["ko_name"],
        "description": ko["description"],
        "effect": pick_english_effect(data["effect_entries"]),
    }


def select_ability_names(cur):
    """pokemons 테이블의 ability1/2/3을 합쳐 중복 없는 특성 이름 목록을 만든다."""
    cur.execute(
        """
        SELECT DISTINCT ability FROM (
            SELECT ability1 AS ability FROM pokemons
            UNION SELECT ability2 FROM pokemons
            UNION SELECT ability3 FROM pokemons
        ) t
        WHERE ability IS NOT NULL
        ORDER BY ability
        """
    )
    return [row[0] for row in cur.fetchall()]


def build(conn):
    """05_abilities.sql 전문을 만들어 돌려준다. (특성 수만큼 API 호출)"""
    cur = conn.cursor()
    abilities = select_ability_names(cur)
    print(f"DB 특성 수: {len(abilities)}")

    failed = []
    no_ko = []
    values = []
    for name in abilities:
        data = fetch_ability(name)
        if data is None:
            failed.append(name)
            print(f"{name} - failed")
            continue
        a = parse_ability(data)
        if a["ko_name"] is None:
            no_ko.append(a["name"])
        values.append(tuple(a[c] for c in COLUMNS))
        print(f"{a['name']} -> {a['ko_name']}")

    print(f"\n수집 {len(values)}개")
    print(f"한국어 이름 없음: {len(no_ko)}개 - {no_ko}")
    print(f"실패: {len(failed)}개 - {failed}")
    return render(schema.ABILITIES, TABLE, COLUMNS,
                  mogrify_rows(cur, values, len(COLUMNS)))

