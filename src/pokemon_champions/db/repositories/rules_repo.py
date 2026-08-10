"""계산 규칙 테이블 조회 — 타입 상성 · 날씨 · 필드 · 상태이상.

── 왜 한 파일에 모으나 ──
  이 넷은 성격이 같다. 포켓몬마다 다르지 않고, 배틀 중에 바뀌지 않고,
  한 번 읽어서 계산 내내 돌려쓰는 참조표다. 조회 함수도 전부 "그 테이블
  통째로" 하나뿐이라 파일을 넷으로 쪼개면 파일당 함수가 하나가 된다.

── 왜 매번 읽지 않고 통째로 주나 ──
  타입 상성은 데미지 한 번 계산할 때마다 필요하다. 그때마다 SELECT 하면
  확정 N타 분석에서 턴 수만큼 쿼리가 나간다. 324행이라 전부 들고 있어도
  메모리가 문제되지 않으므로, 진입점에서 한 번 읽어 인자로 내려보낸다.
  (services/damage.py 의 Rules 참고)
"""


def fetch_type_chart(conn):
    """{(공격타입, 방어타입): 배수} 로 324행 전부.

    dict 로 주는 이유는 계산 쪽이 chart[(atk, dfn)] 한 번으로 끝나야 하기
    때문이다. 리스트로 주면 쓰는 쪽이 매번 훑어야 한다.
    """
    cur = conn.cursor()
    cur.execute("SELECT attack_type, defense_type, multiplier FROM pokemon_types")
    return {(r[0], r[1]): float(r[2]) for r in cur.fetchall()}


def fetch_weathers(conn):
    """{날씨이름: 행} — 위력 보정·방어 보정·지속 데미지까지."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name, ko_name, boost_type, boost_mult, weaken_type, weaken_mult,
               def_boost_type, def_boost_stat, def_boost_mult,
               chip_damage, chip_immune
        FROM weathers
        """
    )
    names = [d[0] for d in cur.description]
    return {r[0]: dict(zip(names, r)) for r in cur.fetchall()}


def fetch_terrains(conn):
    """{필드이름: 행}. 필드는 접지된 쪽에만 걸린다."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name, ko_name, boost_type, boost_mult,
               weaken_type, weaken_mult, heal_fraction
        FROM terrains
        """
    )
    names = [d[0] for d in cur.description]
    return {r[0]: dict(zip(names, r)) for r in cur.fetchall()}


def fetch_status_conditions(conn):
    """{상태이상이름: 행}. 화상의 공격 반감, 마비의 스피드 반감 등."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name, ko_name, attack_mult, speed_mult, turn_damage,
               immobile, fail_chance
        FROM status_conditions
        """
    )
    names = [d[0] for d in cur.description]
    return {r[0]: dict(zip(names, r)) for r in cur.fetchall()}
