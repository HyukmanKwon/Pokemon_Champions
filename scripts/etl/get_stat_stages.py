"""랭크 변화 배수표(stat_stages)를 만든다. API 호출 없음.

공격·방어 계열과 명중·회피는 계산식이 다르다.

    공방      stage >= 0 : (2 + stage) / 2       stage < 0 : 2 / (2 - stage)
    명중회피   stage >= 0 : (3 + stage) / 3       stage < 0 : 3 / (3 - stage)

같은 +1이라도 공격은 1.5배지만 명중은 1.33배다. 이 차이 때문에
계산기에서 배수를 잘못 쓰기 쉬워서 테이블로 못 박아 둔다.
"""

from . import schema
from .parse_utils import render, mogrify_rows

FILENAME = "08_stat_stages.sql"
TABLE = "stat_stages"
COLUMNS = ["stage", "battle_mult", "accuracy_mult"]
DDL = schema.STAT_STAGES

STAGES = range(-6, 7)


def battle_mult(stage):
    """a b c d s 에 적용되는 배수."""
    if stage >= 0:
        return (2 + stage) / 2
    return 2 / (2 - stage)


def accuracy_mult(stage):
    """명중률·회피율에 적용되는 배수."""
    if stage >= 0:
        return (3 + stage) / 3
    return 3 / (3 - stage)


def build(conn):
    """08_stat_stages.sql 전문을 만들어 돌려준다. (13행)"""
    cur = conn.cursor()
    values = [
        (s, round(battle_mult(s), 4), round(accuracy_mult(s), 4))
        for s in STAGES
    ]
    for stage, bm, am in values:
        print(f"{stage:+d}  공방 {bm:.4f}  명중회피 {am:.4f}")
    return render(schema.STAT_STAGES, TABLE, COLUMNS,
                  mogrify_rows(cur, values, len(COLUMNS)))

