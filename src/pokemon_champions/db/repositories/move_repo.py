"""moves 테이블 조회.

fetch_type/fetch_learnable 은 엔트리용이라 ko_name 으로 찾고, 아래쪽 도감용
fetch_list/fetch_detail 은 name(영문, UNIQUE)으로 찾는다. 이유는
pokemon_repo 의 첫 주석과 같다 — 한국어 이름은 NULL 일 수 있다.
"""

from ...text import normalize
from ._rows import one, rows


def fetch_type(conn, ko_move):
    """기술 타입을 돌려준다."""
    cur = conn.cursor()
    cur.execute(
        "SELECT type FROM moves WHERE ko_name = %s",
        (normalize(ko_move),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 기술: {ko_move}")
    return row[0]


def fetch_en_name(conn, ko_move):
    """한국어 이름으로 영문 이름을 찾는다. 없으면 None.

    화면과 CLI 는 한국어로 기술을 고르는데, 상세 조회(fetch_detail)는 영문
    name 으로 찾는다. 그 사이를 잇는 자리다. 없는 이름을 예외로 올리지
    않는 이유는, 부르는 쪽이 404 로 바꿀지 되물을지를 정하게 두려는 것이다.
    """
    cur = conn.cursor()
    cur.execute("SELECT name FROM moves WHERE ko_name = %s",
                (normalize(ko_move),))
    row = cur.fetchone()
    return row[0] if row else None


def fetch_learnable(conn, ko_name):
    """이 포켓몬이 배울 수 있는 기술 전부를 한국어 이름으로, 가나다순으로.

        fetch_learnable(conn, "이상해꽃")  ->  ['거대화', '고사리모으기', ...]

    ── 왜 한 번에 다 가져오나 ──
      기술 4개를 하나씩 "배울 수 있나" 물으면 쿼리가 4번 나간다. 엔트리
      6마리면 24번이다. 목록을 통째로 받아 메모리에서 대조하면 1번이다.
      화면의 선택 목록도 같은 결과를 그대로 쓴다.

    한국어 이름이 없는 기술은 뺀다. 이름으로 고르고 이름으로 검증하는데
    이름이 없으면 어느 쪽에도 쓸 수 없다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.ko_name
        FROM pokemon_moves pm
        JOIN pokemons p ON p.id = pm.pokemon_id
        JOIN moves m    ON m.id = pm.move_id
        WHERE p.ko_name = %s AND m.ko_name IS NOT NULL
        ORDER BY m.ko_name
        """,
        (normalize(ko_name),),
    )
    return [r[0] for r in cur.fetchall()]


# ─────────────────────────────────────────────────────────────
# 도감(전체 열람)용
# ─────────────────────────────────────────────────────────────

def fetch_list(conn):
    """기술 전부를 표에 필요한 만큼만.

    설명(description·effect)과 계산용 세부 항목은 빼고 보낸다. 498줄 표에
    본문까지 실으면 응답이 몇 배로 커지는데, 표에서는 어차피 안 보인다.
    상세를 열면 fetch_detail 이 전부 준다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, ko_name, type, category,
               power, accuracy, pp, priority, ailment
        FROM moves
        ORDER BY ko_name NULLS LAST, name
        """
    )
    return rows(cur)


def fetch_detail(conn, name):
    """기술 하나의 모든 칸 + 능력 변화 + 배우는 포켓몬.

    누구의 능력이 변하는지는 stat_changes 가 아니라 meta_category 를 봐야
    안다. damage-raise 면 시전자, damage-lower 면 상대다(schema.py 주석).
    그 해석은 화면이 하고, 여기서는 두 값을 같이 실어 보내기만 한다.
    """
    # 여기서만 SELECT * 를 쓴다. 상세 화면의 요구가 정확히 "이 기술의 모든
    # 칸"이고, 컬럼을 이름으로 받으므로(_rows) 순서가 바뀌어도 안 어긋난다.
    # 목록(fetch_list)에서는 절대 쓰지 않는다 — 498줄 × 전 컬럼이 된다.
    cur = conn.cursor()
    cur.execute("SELECT * FROM moves WHERE name = %s", (name,))
    row = one(cur)
    if row is None:
        raise ValueError(f"존재하지 않는 기술: {name}")

    cur.execute(
        """
        SELECT sc.stat, sc.change
        FROM move_stat_changes sc
        JOIN moves m ON m.id = sc.move_id
        WHERE m.name = %s ORDER BY sc.stat
        """,
        (name,),
    )
    row["stat_changes"] = rows(cur)

    cur.execute(
        """
        SELECT p.id, p.name, p.ko_name, p.type1, p.type2
        FROM pokemon_moves pm
        JOIN pokemons p ON p.id = pm.pokemon_id
        JOIN moves m    ON m.id = pm.move_id
        WHERE m.name = %s
        ORDER BY p.id, p.name
        """,
        (name,),
    )
    row["learners"] = rows(cur)

    return row
