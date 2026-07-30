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
