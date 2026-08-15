"""실능치 계산 — 순수 함수만 있다.

── 공식 ──
    HP     = 종족값 + 75 + SP
    나머지  = int((종족값 + 20 + SP) * 성격보정)

  성격 보정은 1.1 / 1.0 / 0.9 이고, 성실은 보정이 없다(up·down 이 둘 다 NULL).
  75와 20은 레벨 50 · 개체값 31 고정에서 나온 상수라 config 에 있다.

  랭크 변화는 여기서 곱하지 않는다. 교체하면 초기화되므로 데미지 계산
  시점에 적용한다. (calc/damage.py 참고)

── conn 을 받지 않는다 ──
  이 파일에는 DB 조회가 없다. 종족값과 성격 보정은 호출하는 쪽(team.py)이
  repositories 로 읽어서 넘긴다. 그래서 이 모듈은 DB 없이 테스트된다.
  (tests/test_stats.py)
"""

from ..config import HP_OFFSET, MAX_SP, MAX_SP_PER_STAT, STAT_OFFSET
from ..domain import Stats

BATTLE_STATS = ("a", "b", "c", "d", "s")


def make_sp(values):
    """SP 투자값 (h, a, b, c, d, s) 를 Stats 로 만들고 합계를 확인한다."""
    if len(values) != 6:
        raise ValueError(f"SP는 6개여야 합니다. 받은 개수: {len(values)}")
    if any(v < 0 for v in values):
        raise ValueError(f"SP에 음수가 있습니다: {values}")
    if any(v > MAX_SP_PER_STAT for v in values):
        raise ValueError(f"능력치 하나당 SP는 최대 {MAX_SP_PER_STAT}입니다: {values}")

    sp = Stats(*values)
    total = sp.total()
    if total > MAX_SP:
        raise ValueError(f"SP 합계 {total}, 최대 {MAX_SP}")
    return sp


def calc_stats(base, sp, nature):
    """실능치를 계산한다.

    base    종족값 Stats
    sp      make_sp() 가 검증한 투자값 Stats
    nature  {능력치: 배수}. nature_repo.fetch_modifiers() 의 반환값
    """
    return Stats(
        h=base.h + HP_OFFSET + sp.h,
        **{k: int((base[k] + STAT_OFFSET + sp[k]) * nature.get(k, 1.0))
           for k in BATTLE_STATS},
    )
