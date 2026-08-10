"""items 테이블 조회.

── usable 이 무엇인가 ──
  PokeAPI 는 "포챔스에서 지니게 할 수 있는 도구인가"를 알려주지 않는다.
  카테고리로 긁어온 284개 안에는 대전에서 쓸 수 없는 것이 섞여 있다.
  그래서 사람이 눈으로 확인한 결과를 items.usable 에 담는다.
      python -m scripts.etl.annotator.items
"""

from ._rows import one, rows


def fetch_usable(conn, include_mega_stones=False):
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
    where = "usable AND ko_name IS NOT NULL"
    if not include_mega_stones:
        where += " AND category <> 'mega-stones'"

    cur = conn.cursor()
    cur.execute(f"SELECT ko_name FROM items WHERE {where} ORDER BY ko_name")
    return [r[0] for r in cur.fetchall()]


# ─────────────────────────────────────────────────────────────
# 도감(전체 열람)용
# ─────────────────────────────────────────────────────────────

def fetch_list(conn):
    """도구 전부. usable 로 거르지 않는다.

    fetch_usable 은 "고를 수 있는 것"을 주는 함수라 거르는 게 맞지만,
    도감은 DB 에 무엇이 들어 있는지 보는 화면이다. 여기서까지 걸러 버리면
    usable=false 로 잘못 표시된 도구를 눈으로 찾아낼 방법이 없어진다.
    대신 usable/reviewed 를 같이 보내 화면에서 표시하고 거르게 한다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, ko_name, category, fling_power,
               description, usable, reviewed
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
        "description, effect, usable, reviewed FROM items WHERE name = %s",
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
               me.variant
        FROM mega_evolutions me
        JOIN pokemons bp ON bp.name = me.base_name
        JOIN pokemons mp ON mp.name = me.mega_name
        WHERE me.item_name = %s
        """,
        (name,),
    )
    row["mega"] = one(cur)

    return row
