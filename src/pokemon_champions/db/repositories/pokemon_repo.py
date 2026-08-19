"""pokemons 테이블 조회.

── 엔트리용 조회와 도감용 조회의 열쇠가 다르다 ──
  아래쪽 fetch_base/fetch_meta 는 ko_name 으로 찾는다. 엔트리(my_team.json)에
  사람이 한국어로 적어 넣기 때문이다.

  도감용 fetch_list/fetch_detail 은 name(영문 PK)으로 찾는다. ko_name 은
  NULL 일 수 있고(한국어 이름이 아직 없는 폼) 유일하다는 보장도 없어서,
  목록에서 고른 한 마리를 다시 집어내는 열쇠로는 못 쓴다.
"""

from ...domain import Stats
from ...text import normalize
from ._rows import one, rows


def fetch_base(conn, ko_name):
    """종족값을 Stats 로 돌려준다."""
    cur = conn.cursor()
    cur.execute(
        "SELECT h, a, b, c, d, s FROM pokemons WHERE ko_name = %s",
        (normalize(ko_name),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 포켓몬: {ko_name}")
    return Stats(*row)


def fetch_all_meta(conn):
    """모든 포켓몬의 id·이름·타입을 한 번에 읽어온다.

    이미지 일괄 다운로드처럼 "전체를 훑는" 작업용이다. 한 마리씩
    fetch_meta() 를 313번 부르면 쿼리도 313번 나간다.

    id 순이 아니라 name 순으로 정렬한다. 폼 변이(메가·리전폼)가 10000번대
    id 를 쓰는 탓에 id 정렬은 원종과 폼이 멀리 떨어져 보기 불편하다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, ko_name, type1, type2 FROM pokemons ORDER BY name"
    )
    return [
        {"id": r[0], "name": r[1], "ko_name": r[2], "type1": r[3], "type2": r[4]}
        for r in cur.fetchall()
    ]


def fetch_selectable(conn):
    """엔트리에 등록할 수 있는 포켓몬 이름을 가나다순으로.

    메가폼은 뺀다. 메가는 배틀 중 상태라 엔트리에는 원종만 올라가고,
    validate_spec 도 같은 이유로 메가폼을 거부한다. 고를 수 없는 것을
    목록에 올려두면 고르는 순간 에러가 나는 화면이 된다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT ko_name FROM pokemons p "
        "WHERE NOT EXISTS (SELECT 1 FROM mega_evolutions m"
        "                  WHERE m.mega_id = p.id) "
        "  AND ko_name IS NOT NULL ORDER BY ko_name"
    )
    return [r[0] for r in cur.fetchall()]


def fetch_meta(conn, ko_name):
    """도감 번호(id)·타입·메가폼 여부를 읽어온다.

    id 와 타입은 사진/타입 아이콘을 고르는 데 쓰고, is_mega 는 엔트리 검증에
    쓴다. 메가는 배틀 중 상태라 엔트리에 등록할 수 없다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT p.id, p.type1, p.type2, "
        "       EXISTS (SELECT 1 FROM mega_evolutions m"
        "               WHERE m.mega_id = p.id) AS is_mega "
        "FROM pokemons p WHERE p.ko_name = %s",
        (normalize(ko_name),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 포켓몬: {ko_name}")
    pokemon_id, type1, type2, is_mega = row
    return {"id": pokemon_id, "type1": type1, "type2": type2,
            "is_mega": is_mega}


def fetch_abilities(conn, ko_name):
    """이 포켓몬이 가질 수 있는 특성을 한국어 이름으로 돌려준다.

        fetch_abilities(conn, "이상해꽃")  ->  ['심록', '엽록소']

    pokemon_abilities 는 영문 이름을 들고 있어 abilities 와 조인해야
    한국어가 나온다. slot 으로 정렬하는 이유는 순서(1 · 2 · 숨은특성)가
    화면에서 의미를 갖기 때문이다.

    한국어 이름이 없는 신규 특성은 영문 이름으로 대신한다. 그마저 없으면
    화면에도 검증에도 쓸 이름이 없어진다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(ab.ko_name, ab.name)
        FROM pokemons p
        JOIN pokemon_abilities pa ON pa.pokemon_id = p.id
        JOIN abilities ab         ON ab.id = pa.ability_id
        WHERE p.ko_name = %s
        ORDER BY pa.slot
        """,
        (normalize(ko_name),),
    )
    return list(dict.fromkeys(r[0] for r in cur.fetchall()))


# ─────────────────────────────────────────────────────────────
# 도감(전체 열람)용
# ─────────────────────────────────────────────────────────────

def fetch_list(conn):
    """포켓몬 전부를 화면에 필요한 컬럼째로.

    ── 왜 서버에서 검색·정렬을 하지 않나 ──
      313마리다. 전부 보내도 수십 KB 라 브라우저가 메모리에서 거르는 편이
      빠르고, 글자를 칠 때마다 요청이 나가지 않는다. 몇 천 줄이 되면
      그때 WHERE 와 LIMIT 을 여기에 붙인다.

    합계(BST)는 넣지 않는다. 여섯 칸에서 더하면 나오는 값이라
    DB 에도 없고 여기서도 만들지 않는다 — 더하는 곳은 화면 한 곳이다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id, p.dex_no AS pokemon_id, p.name, p.ko_name, p.type1, p.type2,
               p.height, p.weight, p.h, p.a, p.b, p.c, p.d, p.s,
               EXISTS (SELECT 1 FROM mega_evolutions m WHERE m.base_id = p.id) AS can_mega,
               EXISTS (SELECT 1 FROM mega_evolutions m WHERE m.mega_id = p.id) AS is_mega
        FROM pokemons p
        ORDER BY p.dex_no, p.id, p.name
        """
    )
    return rows(cur)


def fetch_detail(conn, name):
    """한 마리의 모든 것 — 기본 정보 · 특성 · 배울 수 있는 기술 · 메가 관계.

    한 번에 다 담아 보낸다. 상세를 열 때마다 네 번 왕복하면 화면이 네 번
    나뉘어 그려지고, 중간에 하나만 실패했을 때 처리가 지저분해진다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id, p.dex_no AS pokemon_id, p.name, p.ko_name, p.type1, p.type2,
               p.height, p.weight, p.h, p.a, p.b, p.c, p.d, p.s,
               EXISTS (SELECT 1 FROM mega_evolutions m WHERE m.base_id = p.id) AS can_mega,
               EXISTS (SELECT 1 FROM mega_evolutions m WHERE m.mega_id = p.id) AS is_mega
        FROM pokemons p WHERE p.name = %s
        """,
        (name,),
    )
    row = one(cur)
    if row is None:
        raise ValueError(f"존재하지 않는 포켓몬: {name}")

    # 특성. 슬롯 3번이 숨은 특성이라 순서를 지켜야 한다.
    cur.execute(
        """
        SELECT pa.slot AS pos, ab.name, ab.ko_name, ab.description,
               pa.slot = 3 AS is_hidden
        FROM pokemons p
        JOIN pokemon_abilities pa ON pa.pokemon_id = p.id
        JOIN abilities ab         ON ab.id = pa.ability_id
        WHERE p.name = %s
        ORDER BY pa.slot
        """,
        (name,),
    )
    row["abilities"] = rows(cur)

    cur.execute(
        """
        SELECT m.id, m.name, m.ko_name, m.type, m.category,
               m.power, m.accuracy, m.pp, m.priority
        FROM pokemon_moves pm
        JOIN moves m    ON m.id = pm.move_id
        JOIN pokemons p ON p.id = pm.pokemon_id
        WHERE p.name = %s
        ORDER BY m.ko_name NULLS LAST, m.name
        """,
        (name,),
    )
    row["moves"] = rows(cur)

    # 메가 관계는 양방향으로 본다. 원종이면 "무엇이 되는가", 메가폼이면
    # "무엇에서 왔는가" 를 알아야 상세끼리 서로 오갈 수 있다.
    cur.execute(
        """
        SELECT mp.name AS mega_name, mp.ko_name AS mega_ko_name,
               CASE WHEN i.name LIKE '%%-x' THEN 'x'
                    WHEN i.name LIKE '%%-y' THEN 'y' END AS variant, i.name AS item_name, i.ko_name AS item_ko_name
        FROM mega_evolutions me
        JOIN pokemons mp  ON mp.id = me.mega_id
        LEFT JOIN items i ON i.id  = me.item_id
        JOIN pokemons bp  ON bp.id = me.base_id
        WHERE bp.name = %s
        ORDER BY i.name NULLS FIRST, mp.name
        """,
        (name,),
    )
    row["mega_forms"] = rows(cur)

    cur.execute(
        """
        SELECT bp.name AS base_name, bp.ko_name AS base_ko_name,
               CASE WHEN i.name LIKE '%%-x' THEN 'x'
                    WHEN i.name LIKE '%%-y' THEN 'y' END AS variant, i.name AS item_name, i.ko_name AS item_ko_name
        FROM mega_evolutions me
        JOIN pokemons bp  ON bp.id = me.base_id
        LEFT JOIN items i ON i.id  = me.item_id
        JOIN pokemons mp  ON mp.id = me.mega_id
        WHERE mp.name = %s
        """,
        (name,),
    )
    row["mega_of"] = one(cur)

    return row
