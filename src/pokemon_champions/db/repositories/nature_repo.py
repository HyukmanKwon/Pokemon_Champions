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
    """성격 21종을 [{ko_name, up, down}] 로. 고를 목록을 만드는 데 쓴다.

    성격은 포켓몬을 가리지 않으므로 6마리를 위해 여섯 번 조회할 이유가 없다.
    up/down 은 'a' 'c' 같은 능력치 글자이고, 성실은 둘 다 NULL 이다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT ko_name, up, down FROM pokemon_natures ORDER BY ko_name"
    )
    return [{"ko_name": r[0], "up": r[1], "down": r[2]}
            for r in cur.fetchall()]
