"""items 테이블 조회.

── 거르는 자리는 수집할 때 하나뿐이다 ──
  "포챔스에서 지니게 할 수 있는 도구인가"를 PokeAPI 는 알려주지 않는다.
  그 판단은 get_items.py 의 ITEM_CATEGORIES 3개 + EXTRA_ITEMS 낱개 지정이
  전부 한다. 여기 들어온 것은 이미 지닐 수 있는 도구다.

  전에는 items.usable 로 한 번 더 걸렀지만, 그 칸은 168개 전부 true 라
  아무것도 거르지 않으면서 "이 행을 써도 되나"를 매 질의마다 묻게 만들었다.
  카테고리를 넓힐 일이 생기면 넓히는 그 자리에서 좁힌다.
"""

from ._rows import one, rows


def fetch_selectable(conn, include_mega_stones=False):
    """포챔스에서 지닐 수 있는 도구를 한국어 이름으로, 가나다순으로.

    도구는 포켓몬마다 다르지 않으므로 전역 목록 하나면 된다.
    6마리를 위해 여섯 번 조회할 이유가 없다.

    ── 메가스톤을 기본으로 빼는 이유 ──
      선택 목록에 92개를 통째로 올리면 쓸 수 있는 스톤 한두 개가 묻힌다.
      화면에서는 그 포켓몬 것만 따로 보여주므로(mega_repo.fetch_stones)
      여기서는 뺀다.

      다만 검증은 include_mega_stones=True 로 부른다. 거북왕이 리자몽나이트를
      지니는 것은 잘못이 아니라 그냥 메가가 안 되는 것뿐이라서,
      주인이 아닌 스톤도 통과시켜야 한다.
    """
    where = "ko_name IS NOT NULL"
    if not include_mega_stones:
        where += " AND category <> 'mega-stones'"

    cur = conn.cursor()
    cur.execute(f"SELECT ko_name FROM items WHERE {where} ORDER BY ko_name")
    return [r[0] for r in cur.fetchall()]


# ─────────────────────────────────────────────────────────────
# 도감(전체 열람)용
# ─────────────────────────────────────────────────────────────

def fetch_list(conn):
    """도구 전부. 도감은 DB 에 무엇이 들어 있는지 보는 화면이다."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, ko_name, category, fling_power, description
        FROM items
        ORDER BY ko_name NULLS LAST, name
        """
    )
    return rows(cur)


def fetch_detail(conn, name):
    """도구 하나 + (메가스톤이면) 어느 포켓몬을 무엇으로 만드는지.

    메가스톤이 아니면 mega 는 None 이다. 스톤이 아닌 도구가 대부분이라
    없는 게 정상이고, 예외를 올릴 일이 아니다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, ko_name, category, fling_power, "
        "description, effect FROM items WHERE name = %s",
        (name,),
    )
    row = one(cur)
    if row is None:
        raise ValueError(f"존재하지 않는 도구: {name}")

    cur.execute(
        """
        SELECT bp.id   AS base_id,
               bp.name AS base_name, bp.ko_name AS base_ko_name,
               mp.id   AS mega_id,
               mp.name AS mega_name, mp.ko_name AS mega_ko_name,
               -- 이 쿼리는 도구가 주어라 items 를 조인하지 않는다.
               -- 스톤 이름은 me.item_name 이 곧 그것이다.
               CASE WHEN me.item_name LIKE '%%-x' THEN 'x'
                    WHEN me.item_name LIKE '%%-y' THEN 'y' END AS variant
        FROM mega_evolutions me
        JOIN pokemons bp ON bp.name = me.base_name
        JOIN pokemons mp ON mp.name = me.mega_name
        WHERE me.item_name = %s
        """,
        (name,),
    )
    row["mega"] = one(cur)

    return row
