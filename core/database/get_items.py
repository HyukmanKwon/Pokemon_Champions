"""
포챔스에서 지니게 할 수 있는 도구 목록을 PokeAPI에서 받아,
items 테이블용 06_items.sql 을 생성한다.

핵심:
  - 대상 도구 목록 = ITEM_CATEGORIES 의 카테고리들을 조회해 합집합으로 수집
    (도구를 하나하나 적는 대신 카테고리 상수만 조절하면 범위가 바뀐다)

주의:
  - 기술/특성은 flavor_text_entries 의 본문 키가 "flavor_text" 지만
    도구는 "text" 다. pick_korean_flavor 에 키를 넘겨줘야 한다.

단독 실행:
    python get_items.py
"""

import db
import schema
from parse_utils import (get_json, pick_korean, pick_korean_flavor,
                         pick_english_effect, render, mogrify_rows)

POKEAPI_BASE = "https://pokeapi.co/api/v2/item"
POKEAPI_CATEGORY = "https://pokeapi.co/api/v2/item-category"

FILENAME = "06_items.sql"
TABLE = "items"
COLUMNS = ["id", "name", "ko_name", "category",
           "fling_power", "description", "effect"]
DDL = schema.ITEMS
USES_API = True   # 생성 시 PokeAPI를 호출하는가

# ─────────────────────────────────────────────────────────────
# 수집 대상 카테고리 (옆의 숫자는 현재 PokeAPI 기준 개수)
#   포챔스 룰에 따라 z-crystals, memories, jewels 등을 넣고 빼면 된다
# ─────────────────────────────────────────────────────────────
ITEM_CATEGORIES = [
    "held-items",        # 72  먹다남은음식, 생명의구슬 ...
    "choice",            #  3  구애 시리즈
    "bad-held-items",    #  6  검은진흙, 끈적끈적바늘 ...
    "type-enhancement",  # 22  차콜, 신비의물방울 ...
    "species-specific",  # 22  전기구슬, 이상한부적 ...
    "mega-stones",       # 92  메가스톤 전체
    "stat-boosts",       #  9
    "in-a-pinch",        #  9  기합의띠 계열 열매
    "type-protection",   # 19  ○○열매
    "picky-healing",     #  5
    "effort-training",   #  7  파워 시리즈
    "plates",            # 19
]


def fetch_category(category):
    """카테고리 하나에 속한 도구 이름 목록을 받아온다. 실패 시 빈 리스트."""
    data = get_json(f"{POKEAPI_CATEGORY}/{category}")
    if data is None:
        return []
    return [i["name"] for i in data["items"]]


def collect_item_names():
    """ITEM_CATEGORIES 전체를 돌며 중복 없는 도구 이름 목록을 만든다."""
    names = set()
    for category in ITEM_CATEGORIES:
        got = fetch_category(category)
        if not got:
            print(f"{category} - 카테고리 조회 실패")
            continue
        names.update(got)
        print(f"{category} - {len(got)}개")
    return sorted(names)


def fetch_item(name):
    """PokeAPI에서 도구 하나의 원본 JSON을 받아온다. 실패 시 None."""
    return get_json(f"{POKEAPI_BASE}/{name}")


def parse_item(data):
    return {
        "id": data["id"],
        "name": data["name"],
        "ko_name": pick_korean(data["names"]),
        "category": data["category"]["name"],
        "fling_power": data["fling_power"],   # 던질 수 없는 도구는 None
        "description": pick_korean_flavor(data["flavor_text_entries"], key="text"),
        "effect": pick_english_effect(data["effect_entries"]),
    }


def build(conn):
    """06_items.sql 전문을 만들어 돌려준다. (카테고리 12회 + 도구 수만큼 API 호출)"""
    cur = conn.cursor()
    items = collect_item_names()
    print(f"\n수집 대상 도구 수: {len(items)}\n")

    failed = []
    no_ko = []
    values = []
    for name in items:
        data = fetch_item(name)
        if data is None:
            failed.append(name)
            print(f"{name} - failed")
            continue
        it = parse_item(data)
        if it["ko_name"] is None:
            no_ko.append(it["name"])
        values.append(tuple(it[c] for c in COLUMNS))
        print(f"{it['name']} -> {it['ko_name']}")

    print(f"\n수집 {len(values)}개")
    print(f"한국어 이름 없음: {len(no_ko)}개 - {no_ko}")
    print(f"실패: {len(failed)}개 - {failed}")
    return render(schema.ITEMS, TABLE, COLUMNS,
                  mogrify_rows(cur, values, len(COLUMNS)))


def main():
    conn = db.connect()
    db.SQL_DIR.mkdir(exist_ok=True)
    (db.SQL_DIR / FILENAME).write_text(build(conn), encoding="utf-8")
    print(f"{FILENAME} 생성 완료")
    conn.close()


if __name__ == "__main__":
    main()
