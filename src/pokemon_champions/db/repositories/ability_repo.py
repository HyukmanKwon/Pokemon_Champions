"""abilities 테이블 조회."""

from ...text import normalize


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
