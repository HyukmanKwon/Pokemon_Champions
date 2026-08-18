"""pokemon_natures 테이블 조회."""

from ...text import normalize


def fetch_modifiers(conn, ko_nature):
    """{능력치: 배수} 를 돌려준다. 성실처럼 보정이 없으면 빈 dict."""
    cur = conn.cursor()
    cur.execute(
        "SELECT up, down FROM pokemon_natures WHERE ko_name = %s",
        (normalize(ko_nature),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 성격: {ko_nature}")

    up, down = row
    mods = {}
    if up is not None:
        mods[up] = 1.1
    if down is not None:
        mods[down] = 0.9
    return mods


def fetch_all(conn):
    """성격 25종을 [{ko_name, up, down}] 로. 고를 목록을 만드는 데 쓴다.

    성격은 포켓몬을 가리지 않으므로 6마리를 위해 여섯 번 조회할 이유가 없다.
    up/down 은 'a' 'c' 같은 능력치 글자이고, 성실은 둘 다 NULL 이다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT ko_name, up, down FROM pokemon_natures ORDER BY ko_name"
    )
    return [{"ko_name": r[0], "up": r[1], "down": r[2]}
            for r in cur.fetchall()]


def fetch_by_mods(conn, up, down):
    """올라가는 칸과 내려가는 칸으로 성격 한국어 이름을 찾는다. 없으면 None.

    fetch_modifiers 와 방향이 반대다. 저쪽은 이름 -> 보정이고 여기는
    보정 -> 이름이다. 채용률이 "Jolly (Speed↑ Sp.Atk↓)" 처럼 보정만
    알려줄 때 쓴다 — 저쪽 영문 성격 이름을 우리 표에 맞추는 것보다
    보정으로 찾는 편이 확실하다. 보정은 게임 규칙이라 표기가 안 흔들린다.

    ── 무보정 성격은 이 함수로 못 가른다 ──
      성실·노력·온순·수줍음·변덕 다섯은 up/down 이 전부 NULL 이라 보정만
      보고는 구별할 수 없다. 여기서는 성실을 돌려준다 — 부르는 쪽이 이름을
      알고 있으면 이 함수를 거치지 말고 그 이름을 써야 한다.
      (usecases/usage.py 는 usage_rows.linked_name 을 먼저 본다)
    """
    cur = conn.cursor()
    if up is None or down is None:
        cur.execute("SELECT ko_name FROM pokemon_natures "
                    "WHERE up IS NULL AND down IS NULL "
                    "ORDER BY en_name = 'serious' DESC, en_name")
    else:
        cur.execute("SELECT ko_name FROM pokemon_natures "
                    "WHERE up = %s AND down = %s", (up, down))
    row = cur.fetchone()
    return row[0] if row else None
