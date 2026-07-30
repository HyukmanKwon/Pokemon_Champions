"""pokemons 테이블 조회."""

from ...domain import Stats
from ...text import normalize


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


def fetch_meta(conn, ko_name):
    """도감 번호(id)와 타입을 읽어온다. 사진/타입 아이콘을 고르는 데 쓴다."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, type1, type2 FROM pokemons WHERE ko_name = %s",
        (normalize(ko_name),),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"존재하지 않는 포켓몬: {ko_name}")
    pokemon_id, type1, type2 = row
    return {"id": pokemon_id, "type1": type1, "type2": type2}
