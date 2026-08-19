"""포챔스 포켓몬들이 가진 특성을 PokeAPI 에서 받는다. abilities 와
pokemon_abilities 두 표를 같이 만든다.

── 왜 연결표까지 여기서 만드나 ──
  pokemon_abilities.ability_id 가 abilities(id) 를 참조한다. 그런데 어느
  특성을 받아야 하는지는 포켓몬 응답을 봐야 알 수 있어서, abilities 는
  포켓몬 단계보다 뒤에 올 수밖에 없다. 즉 포켓몬 단계에서는 연결표를
  넣을 수 없다.

  그래서 get_pokemons 가 (포켓몬 id, 특성 이름, 슬롯) 을 ABILITY_ROWS 에
  담아 두고, 여기서 abilities 를 넣은 뒤 이어서 넣는다. 한 단계 안이라
  순서가 어긋날 자리가 없다.

  전에는 연결표를 포켓몬 단계에서 넣고 외래키만 나중에 ALTER 로 붙였다.
  그 우회가 사라진다.
"""

from . import get_pokemons
from .parse_utils import (collect, endpoint, korean, pick_english_effect,
                          sql_of, to_values)

POKEAPI_BASE = "https://pokeapi.co/api/v2/ability"
KO_OVERRIDE_KEY = "ability_ko_names"

TABLE = "abilities"
COLUMNS = ["id", "name", "ko_name", "description", "effect"]

LINK_TABLE = "pokemon_abilities"
LINK_COLUMNS = ["pokemon_id", "ability_id", "slot"]

# dump_sql 이 읽는 목록 — 이 파일에 표가 하나 더 있다는 뜻이다.
EXTRA = [(LINK_TABLE, LINK_COLUMNS)]


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


def wanted_names():
    """받아야 할 특성 이름. get_pokemons 가 담아 둔 것에서 중복을 없앤다."""
    return sorted({name for _, name, _ in get_pokemons.ABILITY_ROWS})


def build(conn):
    """abilities + pokemon_abilities INSERT. (특성 수만큼 API 호출)"""
    cur = conn.cursor()
    names = wanted_names()
    if not names:
        raise SystemExit(
            "받을 특성이 없습니다. 포켓몬 단계를 먼저 돌려야 합니다.\n"
            "  python -m scripts.etl.build --only pokemons --only abilities")
    print(f"대상 특성 수: {len(names)}")

    rows = collect(names, fetch_ability, parse_ability)
    sql = sql_of(cur, TABLE, COLUMNS, to_values(rows, COLUMNS))

    # 이름 -> id. 방금 받은 응답에 id 가 들어 있어 조회가 필요 없다.
    ability_id = {r["name"]: r["id"] for r in rows}
    links = [(pokemon_id, ability_id[name], slot)
             for pokemon_id, name, slot in get_pokemons.ABILITY_ROWS
             if name in ability_id]
    print(f"특성 연결 {len(links)}행")
    return sql + "\n" + sql_of(cur, LINK_TABLE, LINK_COLUMNS, links)


