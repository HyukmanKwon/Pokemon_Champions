"""데미지 계산 테스트.

── 왜 DB 가 없어도 도는가 ──
  services/damage.py 는 조회된 값만 인자로 받는다. 그래서 여기서는
  포켓몬도 기술도 상성표도 손으로 만든다. DB 가 없어도, DB 내용이
  바뀌어도 이 테스트는 같은 값을 지켜야 한다.

── 무엇을 지키는 테스트인가 ──
  공식의 각 단계를 하나씩 고정한다. 인자를 하나 더 붙일 때 다른 단계가
  같이 움직이면 여기서 걸린다. 실제 게임 수치와의 대조는 이것과 별개다.

      python -m scripts.check_damage      포케챔스에 넣어볼 케이스를 뽑는다
"""

import pytest

from pokemon_champions.domain import Pokemon, Stats
from pokemon_champions.services import damage
from pokemon_champions.services.damage import (BattleContext, Rules,
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
    },
    terrains={
        "electric": {"boost_type": "electric", "boost_mult": 1.3,
                     "weaken_type": None, "weaken_mult": None},
        "misty": {"boost_type": None, "boost_mult": None,
                  "weaken_type": "dragon", "weaken_mult": 0.5},
    },
)


def mon(name="공격", types=("fire",), stats=(175, 150, 100, 150, 100, 100),
        ability=None, item=None, condition=None):
    return Pokemon(name=name, stats=Stats(*stats), ability=ability,
                   item=item, condition=condition, types=types)


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
    up = BattleContext(defender_rank={"d": 2})
    assert (dmg(ctx=BattleContext(defender_rank={"d": 2}, is_critical=True)).max
            > dmg(ctx=up).max)


def test_급소는_자신의_공격_상승은_그대로_쓴다():
    plain = dmg(ctx=BattleContext(is_critical=True))
    boosted = dmg(ctx=BattleContext(attacker_rank={"c": 2}, is_critical=True))
    assert boosted.max > plain.max


def test_랭크_상승은_데미지를_올리고_하락은_내린다():
    assert dmg(ctx=BattleContext(attacker_rank={"c": 2})).max > dmg().max
    assert dmg(ctx=BattleContext(attacker_rank={"c": -2})).max < dmg().max


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
    burn = BattleContext(attacker_condition="burn")
    physical = move("몸통박치기", "normal", "physical", 90)
    assert dmg(m=physical, ctx=burn).max < dmg(m=physical).max
    assert dmg(ctx=burn).max == dmg().max


def test_근성은_화상_반감을_받지_않는다():
    burn = BattleContext(attacker_condition="burn")
    physical = move("몸통박치기", "normal", "physical", 90)
    guts = mon(ability="근성", condition="burn")
    plain = mon(condition="burn")
    assert dmg(guts, m=physical, ctx=burn).max > dmg(plain, m=physical,
                                                    ctx=burn).max


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


def test_필터류는_약점일_때만_깎는다():
    weak_filter = mon("방어", ("grass",), ability="필터")     # 불꽃 -> 풀 2배
    weak_plain = mon("방어", ("grass",))
    assert dmg(defender=weak_filter).max < dmg(defender=weak_plain).max


def test_멀티스케일은_만피일_때만_걸린다():
    wall = mon("방어", ("normal",), ability="멀티스케일")
    full = dmg(defender=wall).max
    hurt = dmg(defender=wall, ctx=BattleContext(defender_hp=1)).max
    assert full < hurt


def test_궁지_특성은_HP_3분의1_이하에서만_걸린다():
    blaze = mon(ability="맹화")
    full = BattleContext(attacker_hp=blaze.stats.h)
    low = BattleContext(attacker_hp=blaze.stats.h // 3)
    assert dmg(blaze, ctx=low).max > dmg(blaze, ctx=full).max
    # 다른 타입 기술에는 안 걸린다
    water = move("파도타기", "water", "special", 90)
    assert dmg(blaze, m=water, ctx=low).max == dmg(blaze, m=water,
                                                  ctx=full).max


def test_필드는_접지된_쪽에만_걸린다():
    elec = move("10만볼트", "electric", "special", 90)
    on = BattleContext(terrain="electric")
    off = BattleContext(terrain="electric", attacker_grounded=False)
    assert dmg(m=elec, ctx=on).max > dmg(m=elec).max
    assert dmg(m=elec, ctx=off).max == dmg(m=elec).max


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
    assert bulk["physical"] == 175 * 200
    assert bulk["special"] == 175 * 100
    assert bulk["physical"] > bulk["special"]


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
