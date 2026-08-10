"""포챔스에서 지닐 수 있는 도구인지를 브라우저에서 확인·수정한다.

        python -m scripts.etl.annotator.items

브라우저가 자동으로 열린다. 안 열리면 http://localhost:8769 로 접속.

── 왜 필요한가 ──
  도구 목록은 PokeAPI 의 카테고리를 합집합으로 긁어 만든다(get_items.py 의
  ITEM_CATEGORIES). 카테고리 단위라 대전에서 쓸 수 없는 것이 섞여 들어온다.
  "이 도구를 지닐 수 있는가" 는 PokeAPI 가 알려주지 않으므로, 일단 전부
  TRUE 로 두고 사람이 X 를 찍는다.

  이게 정리되면 엔트리 화면의 도구 선택 목록이 짧아지고, 검증이
  "포챔스에서 지닐 수 없는 도구입니다" 로 걸러낼 수 있게 된다.

── 저장은 두 군데에 동시에 ──
  1. DB 의 items 테이블            즉시 반영. 화면과 검증이 바로 쓴다
  2. overrides/item_usable.json    재구축해도 살아남는다. git 에 커밋된다

  DB 에만 쓰면 python -m scripts.etl.build 한 번에 전부 사라진다.
  JSON 에만 쓰면 다시 구축하기 전까지 반영이 안 된다. 그래서 둘 다 쓴다.

── 작업 요령 ──
  분류(category)가 가장 큰 단서라 분류 순으로 정렬해 둔다. 한 분류는 대개
  판정이 같아서 몰아서 보는 편이 빠르다. 판단이 서지 않으면 오른쪽의
  한국어 설명을 본다.

  검색창은 분류로도 걸린다. mega-stones 를 치면 메가스톤만 남는다.
  메가스톤은 92개나 되지만 전부 지닐 수 있는 도구다 — 엔트리 화면에서만
  따로 빼서 그 포켓몬 것만 보여준다(item_repo.fetch_usable).
"""

from pokemon_champions.db import connect

from .. import overrides
from ._common import Spec, serve

OVERRIDE_KEY = "item_usable"

# 추측값. 카테고리로 긁어온 것이라 일단 전부 "지닐 수 있다" 로 둔다.
# JSON 에는 이 추측과 결론이 다른 것만 쌓인다.
DEFAULT_USABLE = True

INFO_COLUMNS = [
    ("id", "번호", "num"),
    ("name", "영문 이름"),
    ("ko_name", "한국어"),
    ("category", "분류"),
    ("related", "이 도구의 주인"),
]

CHECK_COLUMNS = [("usable", "사용")]
LABELS = {"usable": "사용"}

# 메가스톤은 영문 이름만 봐서는 누구 것인지 모른다. mega_evolutions 에 그
# 관계가 있으므로 붙여서 보여준다. 성별 폼이 스톤을 공유해 한 도구에 여러
# 행이 걸리므로 미리 묶는다 — 그냥 조인하면 도구가 중복된다.
# (annotator/ko_names.py 의 items 설정과 같은 조인이다)
STONE_OWNER_JOIN = """
    LEFT JOIN (
        SELECT m.item_name,
               string_agg(DISTINCT p.ko_name, ', ') AS ko_names
        FROM mega_evolutions m
        JOIN pokemons p ON p.name = m.base_name
        WHERE m.item_name IS NOT NULL
        GROUP BY m.item_name
    ) stone_owner ON stone_owner.item_name = t.name
"""


def fetch():
    """분류 순으로 읽는다. 한 분류는 대개 판정이 같아서 몰아 보기 좋다."""
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT t.id, t.name, t.ko_name, t.category,
               stone_owner.ko_names, t.description, t.effect,
               t.usable, t.reviewed
        FROM items t{STONE_OWNER_JOIN}
        ORDER BY t.category, t.name
        """
    )
    cols = ["id", "name", "ko_name", "category", "related",
            "description", "effect", "usable", "reviewed"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def save(name, values, reviewed):
    """DB 와 override JSON 에 동시에 쓴다. 추측과 다른 부분을 돌려준다."""
    usable = bool(values["usable"])

    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE items SET usable = %s, reviewed = %s WHERE name = %s "
        "RETURNING name",
        (usable, reviewed, name),
    )
    found = cur.fetchone()
    conn.commit()
    conn.close()
    if found is None:
        raise KeyError(f"{name} 이라는 도구가 DB에 없습니다")

    # 추측(DEFAULT_USABLE)과 다른 것만 JSON 에 남긴다. 대부분은 지닐 수 있는
    # 도구라, 이렇게 두면 파일에 "쓸 수 없다고 찍은 것" 만 모인다.
    data = overrides.load(OVERRIDE_KEY, refresh=True)
    diff = {} if usable == DEFAULT_USABLE else {"usable": usable}

    if diff:
        data["values"][name] = diff
    else:
        data["values"].pop(name, None)
    if reviewed:
        data["reviewed"] = sorted(set(data["reviewed"]) | {name})
    else:
        data["reviewed"] = [n for n in data["reviewed"] if n != name]
    overrides.save(OVERRIDE_KEY, data)
    return diff


def check_schema():
    """판정 칸이 없으면 안내하고 끝낸다."""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'items'")
    have = {r[0] for r in cur.fetchall()}
    conn.close()
    missing = [c for c in ("usable", "reviewed") if c not in have]
    if missing:
        print("items 테이블에 판정 칸이 없습니다:", ", ".join(missing))
        print("\n아래로 붙이세요. 재구축(API 1,900회)까지 할 일은 아닙니다.")
        print("  psql -d pokemon -c \"ALTER TABLE items"
              " ADD COLUMN usable BOOLEAN NOT NULL DEFAULT TRUE,"
              " ADD COLUMN reviewed BOOLEAN NOT NULL DEFAULT FALSE;\"")
        raise SystemExit(1)


def summary():
    data = overrides.load(OVERRIDE_KEY, refresh=True)
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FILTER (WHERE NOT usable), "
                "       count(*) FILTER (WHERE reviewed), count(*) FROM items")
    unusable, reviewed, total = cur.fetchone()
    conn.close()
    print(f"확인 {reviewed}/{total}개 / 쓸 수 없다고 찍은 것 {unusable}개")
    print(f"JSON 에 남은 항목 {len(data['values'])}개")
    print(f"저장 위치: {overrides.path(OVERRIDE_KEY)}")


SPEC = Spec(
    title="도구 사용 가능 확인",
    subtitle="포챔스에서 지닐 수 없는 도구의 체크를 끄세요",
    info_columns=INFO_COLUMNS,
    check_columns=CHECK_COLUMNS,
    fetch=fetch,
    save=save,
    key_field="name",
    search_fields=("name", "ko_name", "category", "related",
                   "description", "effect"),
    detail_field="description",
    port=8769,
    summary=summary,
    labels=LABELS,
)


def main():
    check_schema()
    serve(SPEC)


if __name__ == "__main__":
    main()
