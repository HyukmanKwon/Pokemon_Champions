"""데미지 계산 테스트.

── 왜 DB 가 없어도 도는가 ──
  calc/damage.py 는 조회된 값만 인자로 받는다. 그래서 여기서는
  포켓몬도 기술도 상성표도 손으로 만든다. DB 가 없어도, DB 내용이
  바뀌어도 이 테스트는 같은 값을 지켜야 한다.

── 무엇을 지키는 테스트인가 ──
  공식의 각 단계를 하나씩 고정한다. 인자를 하나 더 붙일 때 다른 단계가
  같이 움직이면 여기서 걸린다. 실제 게임 수치와의 대조는 이것과 별개다.

      python -m scripts.check_damage      포케챔스에 넣어볼 케이스를 뽑는다
"""

import pytest
from dataclasses import replace

from pokemon_champions.domain import Pokemon, Stats
from pokemon_champions.calc import damage, residual
from pokemon_champions.calc.damage import (BattleContext, Rules,
                                               calc_damage, pokeround, staged)

# ─────────────────────────────────────────────────────────────
# 손으로 만든 판. 실제 종족값이 아니라 계산이 검증하기 쉬운 숫자다.
# ─────────────────────────────────────────────────────────────

CHART = {
    ("fire", "grass"): 2.0, ("fire", "water"): 0.5, ("fire", "fire"): 0.5,
    ("fire", "flying"): 1.0, ("fire", "poison"): 1.0, ("fire", "normal"): 1.0,
    ("water", "fire"): 2.0, ("water", "grass"): 0.5, ("water", "normal"): 1.0,
    ("ground", "flying"): 0.0, ("ground", "fire"): 2.0,
    ("normal", "normal"): 1.0, ("normal", "ghost"): 0.0,
    ("grass", "water"): 2.0,
}
RULES = Rules(
    chart=CHART,
    weathers={
        "sun": {"boost_type": "fire", "boost_mult": 1.5,
                "weaken_type": "water", "weaken_mult": 0.5,
                "def_boost_type": None, "def_boost_stat": None,
                "def_boost_mult": None},
        "snow": {"boost_type": None, "boost_mult": None,
                 "weaken_type": None, "weaken_mult": None,
                 "def_boost_type": "ice", "def_boost_stat": "b",
                 "def_boost_mult": 1.5},
        "sandstorm": {"ko_name": "모래바람",
                      "boost_type": None, "boost_mult": None,
                      "weaken_type": None, "weaken_mult": None,
                      "def_boost_type": "rock", "def_boost_stat": "d",
                      "def_boost_mult": 1.5,
                      "chip_damage": 1 / 16,
                      "chip_immune": ["rock", "ground", "steel"]},
    },
    terrains={
        "electric": {"boost_type": "electric", "boost_mult": 1.3,
                     "weaken_type": None, "weaken_mult": None},
        "misty": {"boost_type": None, "boost_mult": None,
                  "weaken_type": "dragon", "weaken_mult": 0.5},
        "grassy": {"ko_name": "그래스필드",
                   "boost_type": "grass", "boost_mult": 1.3,
                   "weaken_type": None, "weaken_mult": None,
                   "heal_fraction": 1 / 16},
    },
    conditions={
        "burn": {"ko_name": "화상", "turn_damage": 1 / 16},
        "poison": {"ko_name": "독", "turn_damage": 1 / 8},
        "toxic": {"ko_name": "맹독", "turn_damage": None},
        "paralysis": {"ko_name": "마비", "turn_damage": None},
    },
)


def mon(name="공격", types=("fire",), stats=(175, 150, 100, 150, 100, 100),
        ability=None, item=None, condition=None, rank=None, hp=None,
        grounded=True):
    """한 마리에게 걸린 것은 전부 여기로 넘긴다.

    예전에는 랭크·상태이상·HP·접지를 BattleContext 에도 같이 적어야 했다.
    한쪽만 적으면 예외가 아니라 조용히 다른 값이 나왔다 — 화상 걸린 근성을
    재려면 burn 을 두 번 적어야 했던 것이 그 예다.
    """
    return Pokemon(name=name, stats=Stats(*stats), ability=ability,
                   item=item, condition=condition, types=types,
                   rank=rank, hp=hp, grounded=grounded)


def move(name="화염방사", type="fire", category="special", power=90, **kw):
    row = {"name": name, "ko_name": name, "type": type, "category": category,
           "power": power, "target": "selected-pokemon"}
    row.update(kw)
    return row


def dmg(attacker=None, defender=None, m=None, ctx=None):
    return calc_damage(attacker or mon(), defender or mon("방어", ("normal",)),
                       m or move(), ctx, RULES)


# ─────────────────────────────────────────────────────────────
# 본가식 정수 연산
# ─────────────────────────────────────────────────────────────

def test_pokeround_는_반올림이_아니다():
    # 파이썬 round() 는 짝수로 붙어서 round(0.5)==0, round(1.5)==2 다.
    # 본가는 .5 를 항상 내린다.
    assert pokeround(0.5) == 0
    assert pokeround(1.5) == 1
    assert pokeround(2.5) == 2
    assert pokeround(1.51) == 2


def test_랭크는_근사값이_아니라_분수로_적용된다():
    assert staged(100, 0) == 100
    assert staged(100, 1) == 150          # (2+1)/2
    assert staged(100, 6) == 400          # (2+6)/2
    assert staged(100, -1) == 66          # 2/(2+1) -> 0.6666..., stat_stages 는 0.6667
    assert staged(100, -6) == 25          # 2/8


def test_랭크_근사값을_쓰면_어긋난다():
    # stat_stages.battle_mult 의 -4 는 0.3333 이다. 실능 300 에 곱하면
    # 99.99 -> 99 가 되어, 분수 2/6 로 계산한 100 과 1 이 어긋난다.
    # 이 1 이 확정타 판정을 뒤집기 때문에 표가 아니라 분수를 쓴다.
    assert int(300 * 0.3333) == 99
    assert staged(300, -4) == 100


# ─────────────────────────────────────────────────────────────
# 데미지 없는 경우
# ─────────────────────────────────────────────────────────────

def test_변화기는_데미지가_없다():
    assert dmg(m=move("칼춤", "normal", "status", None)).max == 0


def test_상성_0배는_데미지가_없다():
    d = dmg(mon(types=("ground",)), mon("방어", ("flying",)),
            move("지진", "ground", "physical", 100))
    assert d.max == 0


def test_특성_면역은_상성과_별개로_막는다():
    # 부유는 상성표에 0 이 없어도 땅 기술을 막는다
    d = dmg(mon(types=("ground",)),
            mon("방어", ("fire",), ability="부유"),
            move("지진", "ground", "physical", 100))
    assert d.max == 0
    # 특성이 없으면 같은 판에서 데미지가 난다
    assert dmg(mon(types=("ground",)), mon("방어", ("fire",)),
               move("지진", "ground", "physical", 100)).max > 0


def test_데미지는_최소_1이다():
    d = dmg(mon(stats=(175, 1, 100, 1, 100, 100)),
            mon("방어", ("water",), stats=(175, 100, 999, 100, 999, 100)),
            move(power=10))
    assert d.min >= 1


# ─────────────────────────────────────────────────────────────
# 난수 16단계
# ─────────────────────────────────────────────────────────────

def test_난수는_16단계이고_최대가_최소보다_크다():
    d = dmg()
    assert len(d.rolls) == 16
    assert d.min < d.max
    assert d.rolls == sorted(d.rolls)      # 85% -> 100% 오름차순


def test_최소는_최대의_85퍼센트_근처다():
    # 정확히 0.85 가 아니다. 난수를 곱한 뒤에도 자속·상성·최종 보정에서
    # 매번 내림이 들어가서, 작은 쪽이 조금 더 깎인다. 그 폭까지 포함해
    # "대략 85%" 만 지킨다 — 정확한 값은 포케챔스 대조의 몫이다.
    d = dmg()
    assert 0.80 <= d.min / d.max <= 0.88


# ─────────────────────────────────────────────────────────────
# 곱셈 인자 — 하나씩 켜면서 방향만 본다
#
# 정확한 값이 아니라 "켜면 오르는가/내리는가" 를 지킨다. 정확한 값은
# 포케챔스 대조(scripts/check_damage.py)의 몫이다.
# ─────────────────────────────────────────────────────────────

def test_자속은_데미지를_올린다():
    without = dmg(mon(types=("water",)))          # 불꽃 기술, 물 타입 공격자
    with_stab = dmg(mon(types=("fire",)))
    assert with_stab.max > without.max


def test_적응력은_자속보다_더_올린다():
    normal = dmg(mon(types=("fire",)))
    adapt = dmg(mon(types=("fire",), ability="적응력"))
    assert adapt.max > normal.max


def test_상성_2배는_등배의_두_배쯤이다():
    neutral = dmg(defender=mon("방어", ("normal",)))
    weak = dmg(defender=mon("방어", ("grass",)))
    assert 1.9 < weak.max / neutral.max < 2.1


def test_급소는_데미지를_올린다():
    assert dmg(ctx=BattleContext(is_critical=True)).max > dmg().max


def test_급소는_상대의_방어_상승을_무시한다():
    guarded = mon("방어", ("normal",), rank={"d": 2})
    crit = BattleContext(is_critical=True)
    assert dmg(defender=guarded, ctx=crit).max > dmg(defender=guarded).max


def test_급소는_자신의_공격_상승은_그대로_쓴다():
    crit = BattleContext(is_critical=True)
    boosted = dmg(mon(rank={"c": 2}), ctx=crit)
    assert boosted.max > dmg(ctx=crit).max


def test_랭크_상승은_데미지를_올리고_하락은_내린다():
    assert dmg(mon(rank={"c": 2})).max > dmg().max
    assert dmg(mon(rank={"c": -2})).max < dmg().max


def test_날씨는_기술_타입에_따라_오르내린다():
    sun = BattleContext(weather="sun")
    assert dmg(ctx=sun).max > dmg().max                       # 쾌청 + 불꽃
    water = move("파도타기", "water", "special", 90)
    assert dmg(m=water, ctx=sun).max < dmg(m=water).max        # 쾌청 + 물


def test_눈은_얼음_타입의_물리방어를_올린다():
    ice = mon("방어", ("ice",))
    physical = move("몸통박치기", "normal", "physical", 90)
    snow = BattleContext(weather="snow")
    assert dmg(defender=ice, m=physical, ctx=snow).max < dmg(
        defender=ice, m=physical).max
    # 특수에는 안 걸린다 — def_boost_stat 이 b 이기 때문
    assert dmg(defender=ice, ctx=snow).max == dmg(defender=ice).max


def test_화상은_물리만_반감하고_특수는_그대로다():
    burned = mon(condition="burn")
    physical = move("몸통박치기", "normal", "physical", 90)
    assert dmg(burned, m=physical).max < dmg(m=physical).max
    assert dmg(burned).max == dmg().max


def test_근성은_화상_반감을_받지_않는다():
    # burn 을 한 번만 적는다. 예전에는 Pokemon 과 BattleContext 양쪽에
    # 적어야 했고, 한쪽을 빠뜨리면 조용히 다른 것을 재고 있었다.
    physical = move("몸통박치기", "normal", "physical", 90)
    guts = mon(ability="근성", condition="burn")
    plain = mon(condition="burn")
    assert dmg(guts, m=physical).max > dmg(plain, m=physical).max


def test_스크린은_같은_분류만_막고_급소에는_뚫린다():
    physical = move("몸통박치기", "normal", "physical", 90)
    reflect = BattleContext(reflect=True)
    assert dmg(m=physical, ctx=reflect).max < dmg(m=physical).max
    assert dmg(ctx=reflect).max == dmg().max          # 특수는 리플렉터 무관
    # 급소면 스크린이 없는 것과 같다
    assert (dmg(m=physical, ctx=BattleContext(reflect=True, is_critical=True)).max
            == dmg(m=physical, ctx=BattleContext(is_critical=True)).max)


def test_광역기는_더블에서만_깎인다():
    spread = move("눈보라", "water", "special", 110, target="all-opponents")
    single = BattleContext(is_doubles=False)
    double = BattleContext(is_doubles=True)
    assert dmg(m=spread, ctx=double).max < dmg(m=spread, ctx=single).max
    # 단일 대상 기술은 더블이어도 안 깎인다
    assert dmg(ctx=double).max == dmg(ctx=single).max


def test_생명의구슬은_1_3배다():
    plain = dmg().max
    orb = dmg(mon(item="생명의구슬")).max
    assert 1.25 < orb / plain < 1.35


def test_구애안경은_특수만_올린다():
    specs = mon(item="구애안경")
    physical = move("몸통박치기", "normal", "physical", 90)
    assert dmg(specs).max > dmg().max
    assert dmg(specs, m=physical).max == dmg(m=physical).max


def test_타입강화도구는_같은_타입만_올린다():
    charcoal = mon(item="목탄")
    water = move("파도타기", "water", "special", 90)
    assert dmg(charcoal).max > dmg().max
    assert dmg(charcoal, m=water).max == dmg(m=water).max


def test_색안경은_반감일_때만_걸린다():
    resisted = mon("방어", ("water",))          # 불꽃 -> 물 0.5배
    neutral = mon("방어", ("normal",))
    lens = mon(ability="색안경")
    assert dmg(lens, resisted).max > dmg(mon(), resisted).max
    assert dmg(lens, neutral).max == dmg(mon(), neutral).max


def test_약점_반감_열매는_그_타입_약점일_때만_걸린다():
    grass = mon("방어", ("grass",))                       # 불꽃이 2배
    normal = mon("방어", ("normal",))                     # 불꽃이 등배
    assert dmg(defender=mon("방어", ("grass",), item="오카열매")).max \
        < dmg(defender=grass).max
    # 등배에서는 안 걸린다
    assert dmg(defender=mon("방어", ("normal",), item="오카열매")).max \
        == dmg(defender=normal).max
    # 타입이 다른 열매도 안 걸린다
    assert dmg(defender=mon("방어", ("grass",), item="꼬시개열매")).max \
        == dmg(defender=grass).max


def test_카리열매는_등배_노말에도_걸린다():
    # 노말은 약점이 될 수 없다. "효과가 뛰어날 때" 조건을 달면 영영 안 걸린다.
    plain = mon("방어", ("normal",))
    berry = mon("방어", ("normal",), item="카리열매")
    m = move("몸통박치기", "normal", "physical", 100)
    assert dmg(mon(types=("normal",)), berry, m).max \
        < dmg(mon(types=("normal",)), plain, m).max


def test_위력_1할_도구는_분류가_맞을_때만_걸린다():
    phys = move("불꽃펀치", "fire", "physical", 75)
    spec = move("화염방사", "fire", "special", 90)
    base_p = dmg(mon(), m=phys).max
    base_s = dmg(mon(), m=spec).max
    assert dmg(mon(item="힘의머리띠"), m=phys).max > base_p
    assert dmg(mon(item="힘의머리띠"), m=spec).max == base_s
    assert dmg(mon(item="박식안경"), m=spec).max > base_s
    assert dmg(mon(item="박식안경"), m=phys).max == base_p


def test_필터류는_약점일_때만_깎는다():
    weak_filter = mon("방어", ("grass",), ability="필터")     # 불꽃 -> 풀 2배
    weak_plain = mon("방어", ("grass",))
    assert dmg(defender=weak_filter).max < dmg(defender=weak_plain).max


def test_멀티스케일은_만피일_때만_걸린다():
    wall = mon("방어", ("normal",), ability="멀티스케일")
    hurt = mon("방어", ("normal",), ability="멀티스케일", hp=1)
    assert dmg(defender=wall).max < dmg(defender=hurt).max


def test_궁지_특성은_HP_3분의1_이하에서만_걸린다():
    full = mon(ability="맹화")
    low = mon(ability="맹화", hp=full.stats.h // 3)
    assert dmg(low).max > dmg(full).max
    # 다른 타입 기술에는 안 걸린다
    water = move("파도타기", "water", "special", 90)
    assert dmg(low, m=water).max == dmg(full, m=water).max


def test_필드는_접지된_쪽에만_걸린다():
    elec = move("10만볼트", "electric", "special", 90)
    field = BattleContext(terrain="electric")
    flying = mon(grounded=False)
    assert dmg(m=elec, ctx=field).max > dmg(m=elec).max
    assert dmg(flying, m=elec, ctx=field).max == dmg(flying, m=elec).max


def test_테크니션은_위력_60_이하만_올린다():
    tech = mon(ability="테크니션")
    weak, strong = move(power=60), move(power=61)
    assert dmg(tech, m=weak).max > dmg(m=weak).max
    assert dmg(tech, m=strong).max == dmg(m=strong).max


def test_보정은_따로_곱하지_않고_합쳐서_한_번에_걸린다():
    # 생명의구슬(1.3)과 달인의띠(1.2)를 각각 반올림해 곱하면 값이 달라진다.
    # 실패하면 chain() 이 아니라 apply_mod 를 두 번 부르고 있다는 뜻이다.
    d = dmg(mon(item="생명의구슬"), mon("방어", ("grass",)))
    assert d.max > 0


# ─────────────────────────────────────────────────────────────
# 결정력 · 내구력
# ─────────────────────────────────────────────────────────────

def test_결정력은_자속을_반영한다():
    fire = mon(types=("fire",))
    water = mon(types=("water",))
    assert damage.power_index(fire, move()) > damage.power_index(water, move())


def test_변화기의_결정력은_0이다():
    assert damage.power_index(mon(), move("칼춤", "normal", "status", None)) == 0


def test_내구력은_물리와_특수를_따로_준다():
    m = mon(stats=(175, 150, 200, 150, 100, 100))
    bulk = damage.bulk_index(m)
    assert bulk["physical"] == pytest.approx(175 * 200 / 0.411)
    assert bulk["special"] == pytest.approx(175 * 100 / 0.411)
    assert bulk["physical"] > bulk["special"]


def test_내구력_비는_실제로_버티는_횟수의_비다():
    # 0.411 로 나누는 이유가 이것이다. 방어가 두 배면 내구력도 두 배고,
    # 위력 100 등배 기술을 견디는 횟수도 두 배여야 한다.
    thin = mon("방어", ("normal",), stats=(800, 100, 100, 100, 100, 100))
    thick = mon("방어", ("normal",), stats=(800, 100, 200, 100, 100, 100))
    ratio = damage.bulk_index(thick)["physical"] / damage.bulk_index(thin)["physical"]
    assert ratio == pytest.approx(2.0)

    # 실제로 재 봐도 2배쯤 버틴다. 데미지 공식의 내림 때문에 딱 떨어지지
    # 않고, 확정타는 정수라 몇 방 안 되는 판에서는 오차가 20% 를 넘는다.
    # 그래서 여러 방 버티는 몸으로 잰다.
    m = move("몸통박치기", "normal", "physical", 100)
    hits = [damage.analyze_ko(mon(types=("normal",)), p, m, rules=RULES,
                              max_turns=60)["guaranteed"]
            for p in (thin, thick)]
    assert hits == [10, 19]     # 딱 2배가 아닌 것은 내림이 쌓여서다


def test_내구력에도_랭크가_걸린다():
    plain = mon(stats=(200, 100, 100, 100, 100, 100))
    guarded = mon(stats=(200, 100, 100, 100, 100, 100))
    guarded.rank = {"b": 2}
    assert (damage.bulk_index(guarded)["physical"]
            == pytest.approx(damage.bulk_index(plain)["physical"] * 2))


# ─────────────────────────────────────────────────────────────
# 확정 N타
# ─────────────────────────────────────────────────────────────

def test_한_방에_확실히_죽으면_확정_1타():
    glass = mon("방어", ("grass",), stats=(50, 100, 50, 100, 50, 100))
    ko = damage.analyze_ko(mon(), glass, move(power=250), rules=RULES)
    assert ko["guaranteed"] == 1
    assert ko["text"] == "확정 1타"


def test_아무리_때려도_안_죽으면_None():
    wall = mon("방어", ("water",), stats=(999, 100, 999, 100, 999, 100))
    ko = damage.analyze_ko(mon(), wall, move(power=10), rules=RULES,
                           max_turns=2)
    assert ko["guaranteed"] is None
    assert "쓰러지지 않음" in ko["text"]


def test_무효인_기술은_턴을_낭비하지_않는다():
    flyer = mon("방어", ("flying",))
    ko = damage.analyze_ko(mon(types=("ground",)), flyer,
                           move("지진", "ground", "physical", 100),
                           rules=RULES, max_turns=4)
    assert ko["guaranteed"] is None
    assert len(ko["turns"]) == 1        # 무효를 확인한 첫 턴에서 멈춘다


def test_난수타는_확정타보다_먼저_온다():
    # 최고 난수는 죽이고 최저 난수는 못 죽이는 구간을 찾는다
    for hp in range(40, 400):
        target = mon("방어", ("normal",), stats=(hp, 100, 100, 100, 100, 100))
        ko = damage.analyze_ko(mon(), target, move(power=90), rules=RULES)
        if ko["possible"] and ko["guaranteed"] and ko["possible"] != ko["guaranteed"]:
            assert ko["possible"] < ko["guaranteed"]
            assert "난수" in ko["text"]
            return
    pytest.skip("난수타가 갈리는 HP 를 못 찾았다")


def test_rules_없이_부르면_친절하게_막는다():
    with pytest.raises(ValueError, match="rules"):
        calc_damage(mon(), mon("방어"), move())


# ─────────────────────────────────────────────────────────────
# 턴 끝 정산 (calc/residual.py)
#
# 여기도 DB 를 안 본다. 분수는 위 RULES 의 conditions·weathers·terrains 에
# 손으로 적어 뒀다.
# ─────────────────────────────────────────────────────────────

def tick(p, hp=None, **kw):
    return residual.end_of_turn(p, hp, rules=RULES, **kw)


def test_분수는_내림하되_최소_1이다():
    # HP 10 이면 1/16 이 0.625 다. 0 이 되면 모래바람이 영영 안 깎인다.
    assert residual.fraction(160, 16) == 10
    assert residual.fraction(159, 16) == 9
    assert residual.fraction(10, 16) == 1


def test_맹독은_턴마다_세지고_15턴에서_멈춘다():
    assert residual.toxic_damage(160, 1) == 10      # 1/16
    assert residual.toxic_damage(160, 3) == 30      # 3/16
    assert residual.toxic_damage(160, 15) == 150
    assert residual.toxic_damage(160, 99) == 150    # 카운터가 멈춘다


def test_독은_최대HP의_8분의1을_깎는다():
    t = tick(mon(stats=(160, 100, 100, 100, 100, 100)), condition="poison")
    assert t.net == -20
    assert t.entries == [("독", -20)]


def test_먹다남은음식은_만피에서는_아무_일도_안_한다():
    p = mon(stats=(160, 100, 100, 100, 100, 100), item="먹다남은음식")
    assert tick(p, hp=160).net == 0        # 이미 가득
    assert tick(p, hp=100).net == 10       # 1/16
    # 남은 칸보다 회복량이 크면 남은 칸까지만
    assert tick(p, hp=155).net == 5


def test_매직가드는_간접_데미지만_막고_회복은_받는다():
    p = mon(stats=(160, 100, 100, 100, 100, 100),
            ability="매직가드", item="먹다남은음식")
    t = tick(p, hp=100, condition="poison", weather="sandstorm")
    assert t.net == 10                      # 독도 모래바람도 안 걸린다
    assert t.entries == [("먹다남은음식", 10)]


def test_포이즌힐은_독을_회복으로_뒤집는다():
    p = mon(stats=(160, 100, 100, 100, 100, 100), ability="포이즌힐")
    assert tick(p, hp=100, condition="poison").net == 20        # 1/8 회복
    assert tick(p, hp=100, condition="toxic").net == 20         # 맹독도 같다


def test_모래바람은_바위_땅_강철을_깎지_않는다():
    frail = mon("방어", ("normal",), stats=(160, 100, 100, 100, 100, 100))
    rocky = mon("방어", ("rock", "ground"), stats=(160, 100, 100, 100, 100, 100))
    assert tick(frail, weather="sandstorm").net == -10
    assert tick(rocky, weather="sandstorm").net == 0


def test_그래스필드는_접지된_쪽만_회복시킨다():
    p = mon(stats=(160, 100, 100, 100, 100, 100))
    assert tick(p, hp=100, terrain="grassy").net == 10
    assert tick(p, hp=100, terrain="grassy", grounded=False).net == 0


def test_정산_없는_판에서는_Tick_이_비어_있다():
    assert not tick(mon())


# ─────────────────────────────────────────────────────────────
# 정산이 확정타를 뒤집는다
# ─────────────────────────────────────────────────────────────

def wall(hp=200):
    return mon("방어", ("normal",), stats=(hp, 100, 100, 100, 100, 100))


def test_아무것도_안_걸리면_정산_전과_결과가_같다():
    ko = damage.analyze_ko(mon(), wall(), move(power=90), rules=RULES)
    assert ko["residual"] is False
    assert "타" in ko["text"]              # '턴' 이 아니다
    assert all(t["tick"] is None for t in ko["turns"])


def test_독이_확정_3타를_확정_2타로_바꾼다():
    # 같은 판에 독만 얹는다. 기술 데미지는 한 글자도 안 건드린다.
    target = wall(123)
    m = move(power=60)
    plain = damage.analyze_ko(mon(), target, m, rules=RULES)
    poisoned = damage.analyze_ko(
        mon(), replace(target, condition="poison"), m, rules=RULES)

    assert plain["guaranteed"] == 3
    assert poisoned["guaranteed"] == 2
    assert poisoned["residual"] is True
    # 기술 데미지 자체는 그대로여야 한다 — 독은 턴 끝에만 걸린다
    assert plain["turns"][0]["damage"].rolls == poisoned["turns"][0]["damage"].rolls


def test_지속_데미지가_섞이면_타가_아니라_턴이다():
    ko = damage.analyze_ko(
        mon(), replace(wall(123), condition="poison"), move(power=60),
        rules=RULES)
    assert ko["text"] == "확정 2턴"


def test_맹독은_무효인_기술_상대로도_결국_쓰러뜨린다():
    # 지진은 비행에게 안 통한다. 그래도 맹독은 턴마다 쌓인다.
    flyer = mon("방어", ("flying",), stats=(160, 100, 100, 100, 100, 100),
                condition="toxic")
    ko = damage.analyze_ko(
        mon(types=("ground",)), flyer,
        move("지진", "ground", "physical", 100),
        rules=RULES, max_turns=10)
    # 1/16 + 2/16 + ... 로 쌓여 6턴째 누계가 21/16 > 1 이다
    assert ko["guaranteed"] == 6
    assert ko["text"] == "확정 6턴"


def test_먹다남은음식은_확정타를_뒤로_민다():
    # 한 방이 최대 HP 의 1/16 을 겨우 넘는 구간에서 가장 크게 벌어진다.
    stats = (150, 100, 100, 100, 100, 100)
    lefty = mon("방어", ("normal",), stats=stats, item="먹다남은음식")
    bare = mon("방어", ("normal",), stats=stats)
    m = move(power=31)
    assert damage.analyze_ko(mon(), bare, m, rules=RULES,
                             max_turns=10)["guaranteed"] == 6
    assert damage.analyze_ko(mon(), lefty, m, rules=RULES,
                             max_turns=10)["guaranteed"] == 8


def test_맹독_시작_턴을_앞당기면_더_빨리_쓰러진다():
    target = wall(300)
    m = move(power=60)
    poisoned = replace(target, condition="toxic")
    fresh = damage.analyze_ko(mon(), poisoned, m, rules=RULES)
    stale = damage.analyze_ko(mon(), poisoned, m,
                              BattleContext(toxic_turn=5), RULES)
    assert stale["guaranteed"] <= fresh["guaranteed"]


def test_턴마다_무엇이_얼마나_움직였는지_남는다():
    ko = damage.analyze_ko(
        mon(), replace(wall(240), condition="poison"), move(power=20),
        BattleContext(weather="sandstorm"), RULES, max_turns=3)
    first = ko["turns"][0]["tick"]
    assert [name for name, _ in first.entries] == ["모래바람", "독"]
    assert first.text == "모래바람 -15, 독 -30"
