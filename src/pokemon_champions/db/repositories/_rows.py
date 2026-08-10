"""커서 결과를 dict 로 바꾸는 최소 도구.

── 왜 필요한가 ──
  기존 조회는 컬럼이 서너 개라 row[0], row[1] 로 충분했다. 도감 화면은
  pokemons 18칸, moves 27칸을 통째로 보여주므로 같은 방식이면 row[19] 가
  무엇인지 세어야 하고, SELECT 순서를 한 칸만 바꿔도 조용히 어긋난다.

  psycopg2 의 RealDictCursor 를 쓰지 않는 이유는, 그러면 커넥션을 여는
  connection.py 나 부르는 쪽이 cursor_factory 를 알아야 해서 psycopg2 가
  repositories 밖으로 새어 나가기 때문이다. 여기서 닫아둔다.
"""


def rows(cur):
    """SELECT 결과 전부를 [{컬럼명: 값}] 로."""
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def one(cur):
    """한 행을 dict 로. 없으면 None."""
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cur.description], row))
