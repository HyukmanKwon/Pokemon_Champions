"""계산 규칙 조회 — 타입 상성과 타입 이름.

── 날씨·필드·상태이상은 여기 없다 ──
  열다섯 줄짜리 상수라 calc/rules.py 로 옮겼다. 조인 상대가 없고, 읽는
  방법도 "통째로 한 번 읽어 dict 로 접기" 하나뿐이라 표로 둘 이유가
  없었다. 상성표는 324행이고 enum 으로 묶여 있어 DB 에 남는다.

── 왜 매번 읽지 않고 통째로 주나 ──
  타입 상성은 데미지 한 번 계산할 때마다 필요하다. 그때마다 SELECT 하면
  확정 N타 분석에서 턴 수만큼 쿼리가 나간다. 324행이라 전부 들고 있어도
  메모리가 문제되지 않으므로, 진입점에서 한 번 읽어 인자로 내려보낸다.
  (calc/damage.py 의 Rules 참고)

"""

from ._rows import keyed


def fetch_type_chart(conn):
    """{(공격타입, 방어타입): 배수} 로 324행 전부.

    dict 로 주는 이유는 계산 쪽이 chart[(atk, dfn)] 한 번으로 끝나야 하기
    때문이다. 리스트로 주면 쓰는 쪽이 매번 훑어야 한다.
    """
    cur = conn.cursor()
    cur.execute("SELECT attack_type, defense_type, multiplier FROM pokemon_types")
    return {(r[0], r[1]): float(r[2]) for r in cur.fetchall()}


def fetch_type_names(conn, language="ko"):
    """{영문 타입: 그 언어 표기} 18줄.

    상성표는 타입을 영문 슬러그로만 들고 있다. 화면과 도우미는 "불꽃",
    "에스퍼" 라고 말해야 하는데, 그 표기가 pokemon_type_names 에 언어별로
    들어 있다. ko 말고 en·ja 도 있어서 언어를 인자로 받는다.

    이름 있는 다른 표들과 달리 ko_name 컬럼이 아니라 (type_name, language,
    name) 세로 모양이라 lookup_repo 에 얹지 못한다.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT type_name, name FROM pokemon_type_names WHERE language = %s",
        (language,))
    return dict(cur.fetchall())
