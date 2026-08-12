"""상태이상 상수표(status_conditions)를 만든다. API 호출 없음.

name 은 PokeAPI 의 move-ailment 이름을 그대로 쓴다. 그래서
moves.ailment 와 바로 조인된다.

    SELECT m.ko_name, s.ko_name, s.attack_mult
    FROM moves m JOIN status_conditions s ON m.ailment = s.name;

── 값의 출처 ──
아래 수치는 9세대 본가 기준이다. 포챔스가 다르게 잡았다면 이 파일의
CONDITIONS 만 고치면 된다. 세대마다 실제로 바뀐 적이 있는 항목:

  - 화상 지속 데미지 : 1/8 (2~6세대) -> 1/16 (7세대~)
  - 마비 스피드     : 1/4 (2~6세대) -> 1/2 (7세대~)
  - 얼음 해동 확률   : 매 턴 20%

맹독(toxic)은 턴마다 1/16씩 누적되는 특수 계산이라 turn_damage 를
NULL 로 두고 note 로만 남긴다.
"""

from . import schema
from .parse_utils import render, mogrify_rows

FILENAME = "09_status_conditions.sql"
TABLE = "status_conditions"
COLUMNS = ["name", "ko_name", "attack_mult", "speed_mult",
           "turn_damage", "immobile", "fail_chance", "note"]
DDL = schema.STATUS_CONDITIONS

# (name, ko_name, attack_mult, speed_mult, turn_damage, immobile, fail_chance, note)
CONDITIONS = [
    ("burn", "화상", 0.5, None, 1 / 16, False, None,
     "물리공격 0.5배. 불꽃 타입은 걸리지 않는다"),
    ("paralysis", "마비", None, 0.5, None, False, 0.25,
     "행동 실패 25%. 전기 타입은 걸리지 않는다"),
    ("poison", "독", None, None, 1 / 8, False, None,
     "독·강철 타입은 걸리지 않는다"),
    ("toxic", "맹독", None, None, None, False, None,
     "턴마다 1/16씩 누적. n턴째 n/16"),
    ("sleep", "잠듦", None, None, None, True, None,
     "1~3턴. 잠꼬대·코골기만 사용 가능"),
    ("freeze", "얼음", None, None, None, True, None,
     "매 턴 20% 확률로 해동. 얼음 타입은 걸리지 않는다"),
    ("confusion", "혼란", None, None, None, False, 0.33,
     "부가 상태. 33% 확률로 자신을 공격"),
]


def build(conn):
    """09_status_conditions.sql 전문을 만들어 돌려준다. (7행)"""
    cur = conn.cursor()
    for c in CONDITIONS:
        print(f"{c[0]:<10} {c[1]}")
    return render(schema.STATUS_CONDITIONS, TABLE, COLUMNS,
                  mogrify_rows(cur, CONDITIONS, len(COLUMNS)))

