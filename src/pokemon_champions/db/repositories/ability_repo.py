"""abilities 테이블 조회.

fetch_effect 는 엔트리용이라 ko_name 으로 찾고, 도감용 fetch_list/fetch_detail
은 name(영문, UNIQUE)으로 찾는다. 이유는 pokemon_repo 의 첫 주석과 같다.
"""

from ...text import normalize
from ._rows import one, rows


def fetch_effect(conn, ko_ability):
    """특성 설명(한글)을 돌려준다."""
    cur = conn.cursor()
    cur.execute(
        "SELECT description FROM abilities WHERE ko_name = %s",
        (normalize(ko_ability),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 특성: {ko_ability}")
    return row[0]


# ─────────────────────────────────────────────────────────────
# 도감(전체 열람)용
# ─────────────────────────────────────────────────────────────

def fetch_list(conn):
    """특성 전부 + 그 특성을 가질 수 있는 포켓몬 수.

    ── 마릿수를 목록에서 같이 세는 이유 ──
      "이 특성은 아무도 안 가진다"가 목록에서 바로 보여야 쓸모가 있다.
      수집 범위 밖의 특성이 섞여 있는지 여기서 드러난다.

      LEFT JOIN 이라 0마리인 특성도 빠지지 않는다. INNER JOIN 이면
      정확히 그 알고 싶은 줄이 목록에서 사라진다. COUNT 도 COUNT(*) 가
      아니라 COUNT(p.name) 이어야 한다 — COUNT(*) 는 매칭이 없어도 1을 센다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ab.id, ab.name, ab.ko_name, ab.description,
               COUNT(p.name) AS pokemon_count
        FROM abilities ab
        LEFT JOIN pokemon_abilities pa ON pa.ability_id = ab.id
        LEFT JOIN pokemons p           ON p.id = pa.pokemon_id
        GROUP BY ab.id, ab.name, ab.ko_name, ab.description
        ORDER BY ab.ko_name NULLS LAST, ab.name
        """
    )
    return rows(cur)


def fetch_detail(conn, name):
    """특성 하나 + 그 특성을 가질 수 있는 포켓몬 전부.

    슬롯 번호를 같이 준다. 3번이면 숨은 특성이라, 화면에서 "보통 특성"과
    "숨은 특성"을 갈라 보여줄 수 있다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, ko_name, description, effect "
        "FROM abilities WHERE name = %s",
        (name,),
    )
    row = one(cur)
    if row is None:
        raise ValueError(f"존재하지 않는 특성: {name}")

    cur.execute(
        """
        SELECT p.id, p.name, p.ko_name, p.type1, p.type2,
               pa.slot AS pos, pa.slot = 3 AS is_hidden
        FROM pokemon_abilities pa
        JOIN pokemons p ON p.id = pa.pokemon_id
        WHERE pa.ability_id = (SELECT id FROM abilities WHERE name = %s)
        ORDER BY p.id, p.name
        """,
        (name,),
    )
    row["pokemons"] = rows(cur)

    return row
