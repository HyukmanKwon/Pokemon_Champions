"""
포챔스에서 지니게 할 수 있는 도구 목록을 PokeAPI에서 받아,
items 테이블용 06_items.sql 을 생성한다.

핵심:
  - 대상 도구 목록 = ITEM_CATEGORIES 의 카테고리들을 조회해 합집합으로 수집
    (도구를 하나하나 적는 대신 카테고리 상수만 조절하면 범위가 바뀐다)

주의:
  - 기술/특성은 flavor_text_entries 의 본문 키가 "flavor_text" 지만
    도구는 "text" 다. pick_korean_flavor 에 키를 넘겨줘야 한다.
"""

from pokemon_champions.db import connect

from . import overrides
from . import paths
from . import schema
from .parse_utils import (get_json, pick_korean, pick_korean_flavor,
                         pick_english_effect, render, mogrify_rows)

POKEAPI_BASE = "https://pokeapi.co/api/v2/item"
KO_OVERRIDE_KEY = "item_ko_names"
USABLE_OVERRIDE_KEY = "item_usable"
POKEAPI_CATEGORY = "https://pokeapi.co/api/v2/item-category"

# 카테고리로 긁어온 목록이라 대전에서 쓸 수 없는 것이 섞인다. PokeAPI 는 그
# 구분을 주지 않으므로 일단 전부 TRUE 로 두고 사람이 확인한다.
DEFAULT_USABLE = True

FILENAME = "06_items.sql"
TABLE = "items"
COLUMNS = ["id", "name", "ko_name", "category",
           "fling_power", "description", "effect", "usable", "reviewed"]
DDL = schema.ITEMS

# ─────────────────────────────────────────────────────────────
# 수집 대상 카테고리 (옆의 숫자는 현재 PokeAPI 기준 개수)
#   포챔스 룰에 따라 z-crystals, memories, jewels 등을 넣고 빼면 된다
# ─────────────────────────────────────────────────────────────
ITEM_CATEGORIES = [
    "type-enhancement",  # 22  목탄, 신비의물방울 ... (기술 위력 상승류)
    "mega-stones",       # 92  메가스톤 전체
    "type-protection",   # 19  오카열매, 꼬시개열매 ... (타입 데미지 반감 열매)
]

# 카테고리 통째로 담기에는 아까운 것들. 카테고리 안에 대전에서 못 쓰는
# 것이 더 많아서, 쓸 것만 이름으로 집는다.
#
# held-items 만 해도 72개인데 그중 남길 건 아래 정도다. 카테고리를 통째로
# 넣고 나중에 usable 플래그로 거르는 방법도 있지만, 그러면 도감이 안 쓰는
# 도구로 뒤덮인다.
EXTRA_ITEMS = [
    # 열매 — 상태이상 회복. status-cures 카테고리를 통째로 넣으면 해독제·
    # 만병통치제 같은 가방 아이템이 딸려 온다. 지니는 열매만 집는다.
    "aspear-berry",    # 얼음
    "cheri-berry",     # 마비
    "chesto-berry",    # 잠듦
    "lum-berry",       # 상태이상 전부 + 혼란
    "pecha-berry",     # 독
    "persim-berry",    # 혼란
    "rawst-berry",     # 화상
    # 열매 — 회복
    "sitrus-berry",    # 자뭉열매
    # 허브류
    "mental-herb", "mirror-herb", "power-herb", "white-herb",
    # 렌즈류 (노력치용 파워렌즈는 대전에서 안 쓴다)
    "scope-lens", "wide-lens", "zoom-lens",
    # 바위류 — 날씨를 늘리는 것들. 딱딱한돌·가벼운돌은 여기가 아니다
    "damp-rock", "heat-rock", "icy-rock", "smooth-rock",
    # 구애 시리즈
    "choice-band", "choice-scarf", "choice-specs",
    # 기합 시리즈
    "focus-band", "focus-sash",
    # 낱개
    "big-root",        # 큰뿌리
    "bright-powder",   # 반짝가루
    "expert-belt",     # 달인의띠
    "iron-ball",       # 검은철구
    "kings-rock",      # 왕의징표석
    "leftovers",       # 먹다남은음식
    "life-orb",        # 생명의구슬
    "light-ball",      # 전기구슬
    "light-clay",      # 빛의점토
    "metronome",       # 메트로놈
    "muscle-band",     # 힘의머리띠
    "quick-claw",      # 선제공격손톱
    "shed-shell",      # 아름다운허물
    "shell-bell",      # 조개껍질방울
    "wise-glasses",    # 박식안경
]

# type-enhancement 안에 섞여 있는 향로류. 하는 일은 목탄·자석과 같은데
# 위력 배수가 더 낮아, 목록에 두면 고를 일 없는 줄만 늘어난다.
EXCLUDE_ITEMS = [
    "odd-incense", "rock-incense", "rose-incense",
    "sea-incense", "wave-incense",
]


def fetch_category(category):
    """카테고리 하나에 속한 도구 이름 목록을 받아온다. 실패 시 빈 리스트."""
    data = get_json(f"{POKEAPI_CATEGORY}/{category}")
    if data is None:
        return []
    return [i["name"] for i in data["items"]]


def collect_item_names():
    """카테고리 + EXTRA_ITEMS 에서 EXCLUDE_ITEMS 를 뺀 이름 목록."""
    names = set()
    for category in ITEM_CATEGORIES:
        got = fetch_category(category)
        if not got:
            print(f"{category} - 카테고리 조회 실패")
            continue
        names.update(got)
        print(f"{category} - {len(got)}개")
    names.update(EXTRA_ITEMS)
    print(f"낱개 지정 - {len(EXTRA_ITEMS)}개")
    names -= set(EXCLUDE_ITEMS)
    print(f"제외 - {len(EXCLUDE_ITEMS)}개")
    return sorted(names)


def fetch_item(name):
    """PokeAPI에서 도구 하나의 원본 JSON을 받아온다. 실패 시 None."""
    return get_json(f"{POKEAPI_BASE}/{name}")


def parse_item(data):
    # 신규 메가스톤 등 PokeAPI 에 한국어가 없는 도구가 많다. annotator 로
    # 손본 이름·설명을 덮어씌운다.
    #   python -m scripts.etl.annotator.ko_names items
    ko = {
        "ko_name": pick_korean(data["names"]),
        "description": pick_korean_flavor(data["flavor_text_entries"],
                                          key="text"),
    }
    overrides.apply(KO_OVERRIDE_KEY, data["name"], ko)

    # 지닐 수 있는 도구인지의 판정. 이 적용이 없으면
    # python -m scripts.etl.build 한 번에 손으로 찍은 것이 전부 날아간다.
    #   python -m scripts.etl.annotator.items
    flags = {"usable": DEFAULT_USABLE}
    reviewed = overrides.apply(USABLE_OVERRIDE_KEY, data["name"], flags)

    return {
        "id": data["id"],
        "name": data["name"],
        "ko_name": ko["ko_name"],
        "category": data["category"]["name"],
        "fling_power": data["fling_power"],   # 던질 수 없는 도구는 None
        "description": ko["description"],
        "effect": pick_english_effect(data["effect_entries"]),
        "usable": flags["usable"],
        "reviewed": reviewed,
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
    judged = len(overrides.load(USABLE_OVERRIDE_KEY)["values"])
    print(f"지닐 수 없다고 확인된 도구: {judged}개 "
          f"(annotator/items.py 로 확인합니다)")
    return render(schema.ITEMS, TABLE, COLUMNS,
                  mogrify_rows(cur, values, len(COLUMNS)))


def main():
    conn = connect()
    paths.SQL_DIR.mkdir(exist_ok=True)
    (paths.SQL_DIR / FILENAME).write_text(build(conn), encoding="utf-8")
    print(f"{FILENAME} 생성 완료")
    conn.close()


if __name__ == "__main__":
    main()
