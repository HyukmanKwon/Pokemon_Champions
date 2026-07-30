"""moves 테이블 조회."""

from ...text import normalize


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
