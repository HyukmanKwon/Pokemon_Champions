"""턴이 끝날 때의 HP 변화 — 상태이상·날씨·필드·도구·특성.

── 왜 damage.py 밖인가 ──
  데미지 공식과 이건 성격이 다르다. 데미지는 "기술 한 방이 얼마인가" 라
  난수 16개가 나오고 상성·자속·보정이 줄줄이 걸린다. 여기는 "턴이 끝나면
  HP 가 얼마 움직이는가" 라 난수도 상성도 없고, 전부 최대 HP 의 분수다.
  같은 파일에 두면 BattleContext 를 보는 눈이 둘로 갈린다.

── 공격자에게도 쓸 수 있다 ──
  포켓몬 한 마리와 그 한 마리에게 걸린 판 상태만 받는다. 어느 쪽인지는
  묻지 않는다. 지금은 analyze_ko 가 방어자에게만 부르지만, 생명의구슬
  반동이나 맹독을 쓴 쪽까지 재려면 같은 함수를 한 번 더 부르면 된다.

── 왜 순수 함수인가 ──
  calc/damage.py 와 같은 이유다. conn 이 없으므로 실제 게임에서 확인한
  값을 테스트로 박아둘 수 있고, "왜 이 숫자가 나왔나" 를 인자만 다시 넣어
  재현할 수 있다. 참조표는 Rules 로 받는다.

── 정산 순서 ──
  9세대 본가의 턴 종료 순서를 따른다. 합이 같으면 순서는 상관없어 보이지만,
  회복이 최대 HP 에서 잘리기 때문에 실제로 값이 달라진다 — 먹다남은음식이
  먼저 차고 나서 독이 깎는 것과, 독이 깎고 나서 차는 것이 다르다.

      1. 날씨 (모래바람)
      2. 필드 (그래스필드 회복)
      3. 특성 (아이스바디 · 건조피부)
      4. 도구 (먹다남은음식)
      5. 상태이상 (독 · 맹독 · 화상)
"""

import math
from dataclasses import dataclass, field

# ─────────────────────────────────────────────────────────────
# 분수 상수. 전부 "최대 HP 의 몇 분의 일" 이다.
#
# 여기 있는 값은 게임 규칙이므로 modifiers.py 와 같은 자리다 — DB 의
# abilities.effect 에는 영어 설명문만 있어서 코드가 숫자를 뽑아낼 수 없다.
# 상태이상·날씨·필드의 분수는 DB(status_conditions·weathers·terrains)에
# 있으므로 여기 적지 않고 Rules 로 받는다.
# ─────────────────────────────────────────────────────────────

LEFTOVERS = 16          # 먹다남은음식 — 매 턴 1/16 회복
POISON_HEAL = 8         # 포이즌힐 — 독이면 깎이는 대신 1/8 회복
ICE_BODY = 16           # 아이스바디 — 눈일 때 1/16 회복
DRY_SKIN_HEAL = 8       # 건조피부 — 비에서 1/8 회복
DRY_SKIN_HURT = 8       # 건조피부 — 쾌청에서 1/8 손실

# 맹독은 턴마다 n/16 으로 늘어난다. 본가는 카운터를 15 에서 멈춘다 —
# 16/16 이면 만피에서 한 방에 죽어서 계산이 이상해지기 때문이 아니라,
# 그냥 그렇게 구현되어 있다.
TOXIC_MAX_TURN = 15

# 이 특성은 간접 데미지를 통째로 막는다. 회복은 그대로 받는다.
MAGIC_GUARD = "매직가드"

# 독 상태를 회복으로 뒤집는 특성. 이게 있으면 독의 turn_damage 는 안 본다.
POISON_HEAL_ABILITY = "포이즌힐"

ICE_BODY_ABILITY = "아이스바디"
DRY_SKIN_ABILITY = "건조피부"
LEFTOVERS_ITEM = "먹다남은음식"

POISONS = ("poison", "toxic")


@dataclass
class Tick:
    """턴 하나가 끝날 때 일어난 HP 변화. 음수가 데미지다.

    합계만 돌려주지 않는 이유는, "확정 3타가 확정 2타가 됐다" 를 보는
    사람이 무엇 때문인지 알아야 하기 때문이다. 모래바람인지 독인지
    먹다남은음식이 모자란 건지가 합계 하나로는 안 보인다.
    """

    entries: list = field(default_factory=list)     # [(무엇, 변화량), ...]

    @property
    def net(self):
        return sum(v for _, v in self.entries)

    @property
    def text(self):
        """'모래바람 -25, 맹독 -50' — 화면에 그대로 쓸 한 줄."""
        return ", ".join(f"{name} {v:+d}" for name, v in self.entries)

    def __bool__(self):
        return bool(self.entries)


def fraction(max_hp, denominator):
    """최대 HP 의 1/n. 본가는 내림하되 최소 1 이다.

    최소 1 이 없으면 HP 16 미만인 포켓몬에게 모래바람이 0 데미지가 된다.
    실제로는 1 이 들어가고, 그 1 이 쌓여 확정타를 뒤집는다.
    """
    return max(1, math.floor(max_hp / denominator))


def toxic_damage(max_hp, turn):
    """맹독 n턴째 데미지. n/16 이고 16턴째부터는 15/16 에서 멈춘다."""
    n = min(turn, TOXIC_MAX_TURN)
    return max(1, math.floor(max_hp * n / 16))


def _weather_chips(pokemon, weather_rule):
    """모래바람처럼 날씨가 매 턴 깎는가. 면역 타입이면 안 깎는다."""
    if not weather_rule or not weather_rule.get("chip_damage"):
        return 0
    immune = weather_rule.get("chip_immune") or ()
    if any(t in immune for t in pokemon.types or ()):
        return 0
    return fraction(pokemon.stats.h, round(1 / weather_rule["chip_damage"]))


def end_of_turn(pokemon, hp=None, condition=None, weather=None, terrain=None,
                grounded=True, rules=None, toxic_turn=1):
    """이 포켓몬의 턴 종료 정산. -> Tick

    pokemon     Pokemon. 최대 HP · 타입 · 특성 · 도구를 여기서 본다
    hp          현재 HP. None 이면 만피. 회복이 얼마나 들어가는지가 갈린다
    condition   status_conditions.name — "burn" "poison" "toxic" ...
    weather     weathers.name / terrain  terrains.name
    grounded    필드는 접지된 쪽에만 걸린다
    rules       damage.Rules. conditions · weathers · terrains 를 본다
    toxic_turn  맹독이 몇 턴째인가. 1 부터 센다

    ── 왜 hp 를 받나 ──
      회복은 최대 HP 를 넘지 못한다. 만피에서 먹다남은음식은 +0 이고,
      그 0 과 +25 의 차이가 확정 3타와 확정 4타를 가른다.
    """
    if rules is None:
        raise ValueError("rules 가 필요합니다. rules_repo 로 읽어 넘기세요.")

    max_hp = pokemon.stats.h
    hp = max_hp if hp is None else hp
    tick = Tick()

    guarded = pokemon.ability == MAGIC_GUARD
    w = (rules.weathers or {}).get(weather)
    t = (rules.terrains or {}).get(terrain)
    c = (rules.conditions or {}).get(condition)

    def add(name, delta):
        """회복은 만피에서 잘린다. 잘려서 0 이 되면 줄을 남기지 않는다."""
        nonlocal hp
        if delta > 0:
            delta = min(delta, max_hp - hp)
        if delta == 0:
            return
        hp += delta
        tick.entries.append((name, delta))

    # ── 1. 날씨 ──
    if not guarded:
        chip = _weather_chips(pokemon, w)
        if chip:
            add(w.get("ko_name") or weather, -chip)

    # ── 2. 필드 ── 접지된 쪽만
    if t and t.get("heal_fraction") and grounded:
        add(t.get("ko_name") or terrain,
            fraction(max_hp, round(1 / t["heal_fraction"])))

    # ── 3. 특성 ──
    if pokemon.ability == ICE_BODY_ABILITY and weather == "snow":
        add(ICE_BODY_ABILITY, fraction(max_hp, ICE_BODY))
    elif pokemon.ability == DRY_SKIN_ABILITY:
        if weather == "rain":
            add(DRY_SKIN_ABILITY, fraction(max_hp, DRY_SKIN_HEAL))
        elif weather == "sun" and not guarded:
            add(DRY_SKIN_ABILITY, -fraction(max_hp, DRY_SKIN_HURT))

    # ── 4. 도구 ──
    if pokemon.item == LEFTOVERS_ITEM:
        add(LEFTOVERS_ITEM, fraction(max_hp, LEFTOVERS))

    # ── 5. 상태이상 ──
    # 포이즌힐은 독을 회복으로 뒤집는다. 매직가드보다 먼저 본다 —
    # 둘 다 가진 포켓몬은 없지만, 순서를 정해두지 않으면 나중에 갈린다.
    if condition in POISONS and pokemon.ability == POISON_HEAL_ABILITY:
        add(POISON_HEAL_ABILITY, fraction(max_hp, POISON_HEAL))
    elif guarded:
        pass
    elif condition == "toxic":
        add(_ko(c, condition), -toxic_damage(max_hp, toxic_turn))
    elif c and c.get("turn_damage"):
        add(_ko(c, condition), -fraction(max_hp, round(1 / c["turn_damage"])))

    return tick


def _ko(row, fallback):
    """표에 한국어 이름이 있으면 그걸로. 없으면 영문 슬러그 그대로."""
    return (row or {}).get("ko_name") or fallback


def all_ability_keys():
    """검사 스크립트가 쓴다 — 이 파일이 이름으로 찾는 특성 전부."""
    return {MAGIC_GUARD, POISON_HEAL_ABILITY, ICE_BODY_ABILITY,
            DRY_SKIN_ABILITY}


def all_item_keys():
    """검사 스크립트가 쓴다 — 이 파일이 이름으로 찾는 도구 전부."""
    return {LEFTOVERS_ITEM}
