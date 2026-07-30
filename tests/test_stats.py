"""실능치 계산 테스트.

── DB 없이 돈다 ──
  services/stats.py 에서 SQL 을 걷어냈기 때문에 가능하다. 종족값과 성격
  보정을 인자로 넘기면 되니까, PostgreSQL 이 떠 있지 않아도, 데이터가
  들어 있지 않아도 검증된다.

  실행:  pytest
"""

import pytest

from pokemon_champions.config import MAX_SP, MAX_SP_PER_STAT
from pokemon_champions.domain import Stats
from pokemon_champions.services.stats import calc_stats, make_sp


# ─────────────────────────────────────────────────────────────
# make_sp — 레귤레이션 제약
# ─────────────────────────────────────────────────────────────

def test_합계가_상한_이내면_통과한다():
    sp = make_sp((0, 0, 0, 32, 2, 32))
    assert sp.total() == 66
    assert sp.c == 32


def test_합계가_상한을_넘으면_거부한다():
    with pytest.raises(ValueError, match="합계"):
        make_sp((32, 32, 32, 0, 0, 0))   # 96 > 66


def test_한_능력치에_상한을_넘게_주면_거부한다():
    with pytest.raises(ValueError, match=str(MAX_SP_PER_STAT)):
        make_sp((33, 0, 0, 0, 0, 0))


def test_음수를_거부한다():
    with pytest.raises(ValueError, match="음수"):
        make_sp((-1, 0, 0, 0, 0, 0))


def test_개수가_6개가_아니면_거부한다():
    with pytest.raises(ValueError, match="6개"):
        make_sp((0, 0, 0))


def test_상한_경계값은_통과한다():
    assert make_sp((2, 0, 0, 32, 0, 32)).total() == MAX_SP


# ─────────────────────────────────────────────────────────────
# calc_stats — 공식
# ─────────────────────────────────────────────────────────────

# 리자몽 종족값
CHARIZARD = Stats(h=78, a=84, b=78, c=109, d=85, s=100)


def test_HP는_성격보정을_받지_않는다():
    up_c = {"c": 1.1, "a": 0.9}
    sp = make_sp((0, 0, 0, 32, 2, 32))
    assert calc_stats(CHARIZARD, sp, up_c).h == 78 + 75 + 0


def test_성격보정이_없으면_그대로다():
    sp = make_sp((0, 0, 0, 0, 0, 0))
    stats = calc_stats(CHARIZARD, sp, {})
    assert stats.c == 109 + 20
    assert stats.s == 100 + 20


def test_겁쟁이_리자몽():
    """겁쟁이 = 스피드 1.1 / 공격 0.9. SP는 C32 D2 S32."""
    nature = {"s": 1.1, "a": 0.9}
    sp = make_sp((0, 0, 0, 32, 2, 32))
    stats = calc_stats(CHARIZARD, sp, nature)

    assert stats.h == 78 + 75          # 153
    assert stats.a == int((84 + 20 + 0) * 0.9)    # 93
    assert stats.c == 109 + 20 + 32               # 161
    assert stats.s == int((100 + 20 + 32) * 1.1)  # 167


def test_보정은_내림한다():
    """int() 라서 버림이다. 반올림으로 바꾸면 여기가 깨진다."""
    base = Stats(h=1, a=100, b=1, c=1, d=1, s=1)
    stats = calc_stats(base, make_sp((0, 0, 0, 0, 0, 0)), {"a": 0.9})
    assert stats.a == 108           # 120 * 0.9 = 108.0
    assert stats.a != 108.0000001
