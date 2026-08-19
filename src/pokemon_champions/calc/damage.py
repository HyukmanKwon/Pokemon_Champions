"""데미지 계산 — 결정력·내구력 지표와 실제 데미지, 확정 N타 판정.

── conn 이 없다 ──
  옮기기 전 이 파일은 모듈 최상단에서 psycopg2.connect() 를 했다. import
  하는 것만으로 DB 접속이 일어났고, 그래서 DB 없이는 테스트도 import 도
  불가능했다. 이제 이 모듈은 이미 조회된 값만 인자로 받는다.

  조회는 부르는 쪽(agent 툴이나 API 라우터)에서 repositories 로 하고,
  여기에는 숫자만 넘어온다. 그 덕에 세 가지가 가능해진다.

    1. 실제 게임에서 확인한 데미지 케이스를 테스트로 박아둘 수 있다.
    2. LLM 툴로 감쌀 때 시그니처가 그대로 툴 스키마가 된다.
    3. "왜 이 숫자가 나왔나" 를 인자만 다시 넣어 재현할 수 있다.

── 공식은 9세대 본가와 같다 ──
  포챔스는 레벨 50 고정 · 개체값 31 고정 · SP 라는 자체 규칙을 쓰지만,
  그건 "실능치를 어떻게 만드는가" 의 규칙이고 데미지 공식 자체는 9세대
  그대로다. 실능치는 calc/stats.py 가 이미 포챔스 규칙으로 만들어
  주므로, 여기서는 그 숫자를 받아 공식에 넣기만 한다.

── 왜 4096 고정소수점인가 ──
  본가는 실수 곱셈을 쓰지 않는다. 모든 보정을 4096 = 1.0 으로 두고 정수로
  곱한 뒤 특유의 반올림(pokeround)을 한다. float 로 계산해도 대부분 같은
  값이 나오지만 경계에서 1 이 어긋나고, 그 1 때문에 "확정 2타" 가
  "난수 2타" 로 뒤집힌다. 계산기의 존재 이유가 바로 그 판정이므로
  본가 방식을 그대로 쓴다.

── 왜 BattleContext 로 묶나 ──
  날씨·필드·랭크·스크린·상태이상은 순차 계산 도중에 값이 변한다. 인자로
  하나씩 늘리면 새 요소를 지원할 때마다 모든 호출부를 고쳐야 한다. 한
  덩어리로 묶으면 필드 추가가 호출부를 건드리지 않고, 확정 N방 분석도
  "context 를 한 턴씩 바꾸며 같은 함수를 반복 호출" 로 깔끔하게 써진다.
"""

import math
from dataclasses import dataclass, field, replace

from ..config import BULK_FACTOR, LEVEL_FACTOR, MOD_ONE, SPREAD_MULT
from ..domain import BattlePokemon
from . import modifiers, residual, rules

# 여러 대상을 치는 기술. moves.target 이 이 값이면 더블에서 위력이 깎인다.
SPREAD_TARGETS = {"all-opponents", "all-other-pokemon", "all-pokemon"}


@dataclass
class BattleContext:
    """판 전체에 걸리는 것. 한쪽에게만 걸리는 것은 BattlePokemon 이 들고 있다.

    가르는 기준이 "누구에게 걸리나" 하나다. 랭크·상태이상·남은 HP·접지는
    한 마리의 사정이므로 BattlePokemon 에 있고, 날씨·필드·급소·스크린·더블은
    판의 사정이라 여기 있다.

    맹독 턴만 예외다 — 방어자에게 걸린 상태인데 여기 있다. 지금 맹독을
    재는 쪽이 방어자뿐이라 그렇고, 공격자 맹독까지 재게 되면 BattlePokemon 으로
    옮긴다.

    전부 기본값이 있다. 아무것도 안 넘기면 평지·맑음이다.
    """

    weather: str = None          # weathers.name — "sun" "rain" "sandstorm" "snow"
    terrain: str = None          # terrains.name — "electric" "grassy" ...
    is_critical: bool = False
    reflect: bool = False        # 리플렉터 (물리 반감)
    light_screen: bool = False   # 빛의장막 (특수 반감)
    # 더블인가. 광역기 0.75 보정과 스크린 배수(0.5 대신 0.667)가 갈린다.
    # 포챔스는 싱글·더블 랭크가 따로 있어서 고정할 수 없다.
    is_doubles: bool = False
    # 맹독이 몇 턴째인가. 데미지가 n/16 으로 늘어나므로 1 부터 시작하는지
    # 이미 세 턴 지났는지가 확정타를 가른다. 맹독이 아니면 안 쓰인다.
    toxic_turn: int = 1


@dataclass
class Rules:
    """계산 내내 돌려쓰는 참조표.

    chart 만 DB 에서 온다(324행). 데미지 한 번마다 SELECT 하면 확정 N타
    분석에서 턴 수만큼 쿼리가 나가므로 진입점에서 한 번 읽어 넘긴다.

    날씨·필드·상태이상은 calc/rules.py 의 상수다. 넘기지 않으면 그것이
    쓰인다 — 부르는 쪽이 chart 만 챙기면 된다.
    """

    chart: dict                              # {(공격타입, 방어타입): 배수}

    # 셋은 상수라 기본값이 곧 정답이다. 넘길 이유가 없지만 인자로 남겨
    # 두는 것은 테스트가 다른 값을 끼워 넣을 수 있어야 하기 때문이다.
    weathers: dict = field(default_factory=lambda: rules.WEATHERS)
    terrains: dict = field(default_factory=lambda: rules.TERRAINS)
    # 화상의 공격 반감은 여기 없이도 되지만(damage.py 가 직접 본다), 턴 끝
    # 지속 데미지는 분수가 표에 있어야 한다. calc/residual.py 가 본다.
    conditions: dict = field(default_factory=lambda: rules.STATUS_CONDITIONS)


@dataclass
class Situation:
    """보정 표(modifiers.py)가 보는 판 전체. 표의 조건 함수가 이걸 받는다.

    BattlePokemon 과 move 를 따로 넘기지 않고 하나로 묶는 이유는, 표에 조건을
    추가할 때 필요한 값이 늘어나도 표만 고치면 되게 하려는 것이다.
    """

    attacker: BattlePokemon
    defender: BattlePokemon
    move: dict
    ctx: BattleContext
    rules: Rules
    type_eff: float = 1.0        # 상성 배수. 최종 보정 단계에서만 정해진다

    @property
    def weather(self):
        return self.ctx.weather

    @property
    def terrain(self):
        return self.ctx.terrain

    @property
    def weather_rule(self):
        return self.rules.weathers.get(self.ctx.weather)

    @property
    def terrain_rule(self):
        return self.rules.terrains.get(self.ctx.terrain)

    @property
    def attacker_hp(self):
        return self.attacker.hp_now()

    @property
    def defender_hp(self):
        return self.defender.hp_now()


@dataclass
class DamageRange:
    """난수 16단계(85~100%)의 최소·최대와 전체 목록."""

    rolls: list

    @property
    def min(self):
        return min(self.rolls)

    @property
    def max(self):
        return max(self.rolls)

    def percent(self, max_hp):
        """최대 HP 대비 몇 %인가. (최소, 최대)"""
        return (self.min / max_hp * 100, self.max / max_hp * 100)


# ─────────────────────────────────────────────────────────────
# 본가식 정수 연산
# ─────────────────────────────────────────────────────────────

def pokeround(x):
    """.5 이하는 내림, 초과는 올림.

    파이썬 round() 는 .5 를 짝수 쪽으로 붙인다(round(2.5) == 2). 본가는
    항상 내림이라 2.5 -> 2, 3.5 -> 3 이다. 우연히 같아 보이지만
    round(0.5) == 0, round(1.5) == 2 에서 갈린다.
    """
    return math.floor(x) if x % 1 <= 0.5 else math.ceil(x)


def chain(mods):
    """보정 여러 개를 4096 기준으로 이어 곱한다.

    각각을 따로 곱해 반올림하면 오차가 쌓인다. 본가는 보정끼리 먼저
    합쳐 하나로 만든 뒤 한 번만 적용한다.
    """
    m = MOD_ONE
    for mod in mods:
        if mod != MOD_ONE:
            m = (m * mod + 2048) >> 12
    return m


def apply_mod(value, mod):
    """4096 기준 보정 하나를 값에 적용한다."""
    return pokeround(value * mod / MOD_ONE)


def staged(value, stage):
    """랭크 변화를 적용한 실능치.

    ── 왜 stat_stages 테이블을 안 쓰나 ──
      그 테이블의 battle_mult 는 REAL 이라 -1 이 0.6667 로 들어 있다.
      본가는 2/(2-stage) 라는 분수를 그대로 쓰므로, 근사값으로 곱하면
      경계에서 1 이 어긋난다. 표는 화면 표시용으로 남기고 계산은 분수로 한다.
    """
    if stage >= 0:
        return math.floor(value * (2 + stage) / 2)
    return math.floor(value * 2 / (2 - stage))


# ─────────────────────────────────────────────────────────────
# 상대가 없어도 나오는 지표
#
# 데미지보다 입력이 단순해서 먼저 만든다. "이 스펙이 센가"를 상대 없이
# 비교할 수 있고, 테스트도 곱셈 하나짜리라 쓰기 쉽다.
# ─────────────────────────────────────────────────────────────

def power_index(pokemon, move, types=None):
    """
    결정력 — 공격 실능 × 기술 위력 × 자속 보정.
    """
    power = move.get("power") or 0
    if not power:
        return 0

    stat = "a" if move["category"] == "physical" else "c"
    types = types if types is not None else pokemon.types  
    stab = 1.5 if move["type"] in (types or ()) else 1.0    #자속 보정
    atk = staged(pokemon.stats[stat], pokemon.rank_of(stat))
    return int(atk * power * stab)


def bulk_index(pokemon):
    """내구력 — HP × 방어 / 0.411, HP × 특수방어 / 0.411.

    ── 왜 곱인가 ──
      HP 만 봐도, 방어만 봐도 실제로 몇 방 버티는지가 안 나온다. 받는
      데미지가 방어에 반비례하고 남은 턴이 HP 에 비례하므로, 버티는 정도는
      두 값의 곱에 비례한다.

    ── 왜 0.411 로 나누는가 ──
      곱만 두면 자릿수가 커서(3만~9만) 서로 견줄 때 눈에 안 들어온다.
      0.411 은 레벨 50 데미지 공식에서 실능치를 뺀 나머지를 상수로 접은
      값이다. 그래서 이 값은 그냥 큰 수가 아니라 **위력 100 등배 자속 없는
      기술을 몇 번 견디는가에 비례하는 양**이 된다.

          받는 데미지 ≈ (공격 실능 × 위력) × 0.411 / 방어 실능
          견디는 횟수 ≈ HP / 받는 데미지 = HP × 방어 / (0.411 × 공격 × 위력)

      공격 쪽을 1 로 두면 남는 것이 HP × 방어 / 0.411 이다. 절대값 자체를
      게임에서 보는 일은 없고, 여전히 비교용이다 — 다만 두 포켓몬의
      내구력 비가 실제로 버티는 횟수의 비와 같아진다.

    ── 왜 소수를 그대로 두나 ──
      데미지 계산과 달리 여기는 본가가 하는 연산이 아니다. 확정타를 가르는
      1 이 없으므로 4096 정수로 옮길 이유가 없고, 반올림하면 비교값이 계단
      모양이 된다. 화면에서 자리수를 줄이는 것은 표시하는 쪽 일이다.

    방어·특수방어에는 랭크가 걸리고 HP 에는 안 걸린다. 본가에 HP 랭크가
    없기 때문이다 — 화면에서 체력 칸을 올려도 여기서는 무시된다.
    """
    h = pokemon.stats.h
    return {
        "physical": h * staged(pokemon.stats.b, pokemon.rank_of("b")) / BULK_FACTOR,
        "special": h * staged(pokemon.stats.d, pokemon.rank_of("d")) / BULK_FACTOR,
    }


# ─────────────────────────────────────────────────────────────
# 타입 상성
# ─────────────────────────────────────────────────────────────

def type_multiplier(move_type, defender_types, chart):
    """타입 상성 배수. chart 는 {(공격, 방어): 배수} — pokemon_types 테이블.

    조회 결과를 인자로 받는다. 이 함수 안에서 SELECT 하지 않는다.

    2타입이면 두 배수를 곱한다. 표에 없는 조합은 1.0 으로 본다 — 없는
    것과 등배는 계산상 같고, 여기서 예외를 올리면 폼 하나 빠졌다고
    데미지 계산 전체가 멈춘다.
    """
    mult = 1.0
    for t in defender_types or ():
        mult *= chart.get((move_type, t), 1.0)
    return mult


# ─────────────────────────────────────────────────────────────
# 데미지
# ─────────────────────────────────────────────────────────────

def calc_damage(attacker, defender, move, ctx=None, rules=None):
    """데미지 난수 16개를 DamageRange 로 돌려준다.

    attacker / defender  BattlePokemon (실능치·타입·배틀 상태가 들어 있다)
    move                 moves 테이블 한 행 (dict)
    ctx                  BattleContext. None 이면 기본 상태
    rules                Rules. 최소한 chart 는 있어야 한다

    곱셈 순서가 곧 공식이다. 아래 주석의 번호가 본가 순서다 — 순서를
    바꾸면 값이 달라지므로 인자를 추가할 때 자리를 잘 봐야 한다.
    """
    ctx = ctx or BattleContext()
    if rules is None:
        raise ValueError("rules 가 필요합니다. rules_repo 로 읽어 넘기세요.")

    # 변화기와 위력 없는 기술은 데미지가 없다. 0 을 돌려준다 —
    # 예외를 올리면 기술 4개를 훑는 쪽이 매번 감싸야 한다.
    if move.get("category") == "status" or not move.get("power"):
        return DamageRange([0] * 16)

    sit = Situation(attacker, defender, move, ctx, rules)

    # 특성·도구가 통째로 막으면 상성을 볼 것도 없다.
    if modifiers.is_immune(sit):
        return DamageRange([0] * 16)

    eff = type_multiplier(move["type"], defender.types, rules.chart)
    if eff == 0:
        return DamageRange([0] * 16)
    sit = replace(sit, type_eff=eff)

    # ── 1. 공격·방어 실능 (랭크 -> 특성/도구 순) ──
    atk_key = "a" if move["category"] == "physical" else "c"
    def_key = "b" if move["category"] == "physical" else "d"

    a_stage = attacker.rank_of(atk_key)
    d_stage = defender.rank_of(def_key)
    # 급소는 "자신에게 불리한" 랭크만 무시한다. 공격이 오른 것은 그대로
    # 쓰고 내려간 것은 없던 걸로, 상대 방어는 그 반대.
    if ctx.is_critical:
        a_stage = max(a_stage, 0)
        d_stage = min(d_stage, 0)

    atk = apply_mod(staged(attacker.stats[atk_key], a_stage),
                    chain(modifiers.attack_mods(sit)))
    dfn = apply_mod(staged(defender.stats[def_key], d_stage),
                    chain(modifiers.defense_mods(sit)))
    atk, dfn = max(1, atk), max(1, dfn)

    # ── 2. 기술 위력 ──
    power = max(1, apply_mod(move["power"], chain(modifiers.power_mods(sit))))

    # ── 3. 기본 데미지 ──
    # floor 가 세 번 들어간다. 한 번이라도 빼면 값이 어긋난다.
    base = math.floor(math.floor(LEVEL_FACTOR * power * atk / dfn) / 50) + 2

    # ── 4. 광역기 (더블에서만) ──
    if ctx.is_doubles and move.get("target") in SPREAD_TARGETS:
        base = apply_mod(base, round(SPREAD_MULT * MOD_ONE))

    # ── 5. 날씨 (기술 타입에 대한 위력 보정) ──
    w = sit.weather_rule
    if w:
        if w.get("boost_type") == move["type"] and w.get("boost_mult"):
            base = apply_mod(base, round(w["boost_mult"] * MOD_ONE))
        elif w.get("weaken_type") == move["type"] and w.get("weaken_mult"):
            base = apply_mod(base, round(w["weaken_mult"] * MOD_ONE))

    # ── 6. 급소 ──
    if ctx.is_critical:
        base = math.floor(base * 1.5)

    # ── 7~11. 난수 16단계. 여기부터는 난수마다 따로 굴린다 ──
    is_stab = move["type"] in (attacker.types or ())
    stab = modifiers.stab_mod(sit, is_stab)
    final = chain(modifiers.final_mods(sit))
    # 화상은 물리에만, 근성 특성이면 안 걸린다 (근성은 공격을 올린다)
    burned = (attacker.condition == "burn"
              and move["category"] == "physical"
              and attacker.ability != "근성")

    rolls = []
    for i in range(16):
        d = math.floor(base * (85 + i) / 100)   # 7. 난수
        d = apply_mod(d, stab)                  # 8. 자속
        d = math.floor(d * eff)                 # 9. 타입 상성
        if burned:
            d = math.floor(d / 2)               # 10. 화상
        d = max(1, apply_mod(d, final))         # 11. 최종 보정
        rolls.append(d)

    return DamageRange(rolls)


# ─────────────────────────────────────────────────────────────
# 확정 N타
# ─────────────────────────────────────────────────────────────

def analyze_ko(attacker, defender, move, ctx=None, rules=None, max_turns=4):
    """몇 방에 쓰러지는지 — 확정 1타 / 난수 2타 처럼 판정한다.

    ── 왜 "데미지 × N" 이 아닌가 ──
      맞는 도중에 값이 바뀌는 특성이 있다. 스태미나는 맞을 때마다 방어가
      한 단계 오르고, 멀티스케일은 첫 방에만 걸린다. 그래서 한 방씩
      계산하면서 그 사이에 ctx 를 갱신한다.

    ── 기술 데미지만이 아니다 ──
      턴이 끝나면 독이 깎고 모래바람이 깎고 먹다남은음식이 채운다. 그
      정산을 빼면 맹독 깔고 버티는 판을 이 계산기로 물어볼 수 없다.
      맹독은 특히 턴마다 세지므로 "한 방 × N" 으로는 영영 안 나온다.
      계산은 calc/residual.py 가 하고, 여기서는 턴 사이에 끼워 넣는
      순서만 정한다 — 기술이 먼저, 정산이 나중이다.

    돌려주는 값
        {"guaranteed": 확정 N타 (전 난수가 쓰러뜨림) 또는 None,
         "possible":   최소 N타 (최고 난수가 쓰러뜨림) 또는 None,
         "text":       "확정 2타" / "난수 2타 (43.8%)" 같은 표시용 문구,
         "turns":      턴별 [{damage, hp_before, tick}, ...],
         "residual":   턴 끝 정산이 한 번이라도 HP 를 움직였는가}

    ── 확률 계산의 한계 ──
      2타 이상의 정확한 확률은 난수 조합을 전부 세야 나온다(16^N). 여기서는
      "최고 난수만 쓰러뜨리는가 / 전부 쓰러뜨리는가" 두 경계만 본다.
      정확한 확률이 필요해지면 그때 조합을 세는 함수를 따로 만든다.
    """
    ctx = ctx or BattleContext()
    max_hp = defender.stats.h

    turns = []
    # 최소 난수만 맞았을 때와 최대 난수만 맞았을 때를 따로 굴린다.
    # 하나로 굴리면 "중간 난수 기준" 이라는 아무 의미 없는 값이 나온다.
    worst_hp = best_hp = defender.hp_now()
    guaranteed = possible = None
    moved = False               # 정산이 한 번이라도 HP 를 움직였는가

    for turn in range(1, max_turns + 1):
        # 멀티스케일처럼 남은 HP 를 보는 특성이 있어서 매 턴 갱신한다.
        # HP 가 BattlePokemon 에 있으므로 방어자를 갈아끼운다 — 예전에는 ctx 를
        # 갈아끼우고 _tick 에 HP 를 따로 넘겨서, 같은 값이 두 길로 갔다.
        hurt = replace(defender, hp=worst_hp)
        dmg = calc_damage(attacker, hurt, move, ctx, rules)

        best_hp -= dmg.max          # 운이 가장 좋았을 때
        worst_hp -= dmg.min         # 운이 가장 나빴을 때

        # 턴 끝 정산. 기술로 이미 쓰러졌으면 그 턴은 정산이 없다.
        # 두 갈래를 따로 굴리는 이유는 회복이 남은 HP 에서 잘리기
        # 때문이다 — 만피에 가까운 쪽은 먹다남은음식이 덜 들어간다.
        tick = _tick(hurt, ctx, rules, turn) if worst_hp > 0 else None
        best_tick = (_tick(replace(defender, hp=best_hp), ctx, rules, turn)
                     if best_hp > 0 else None)

        turns.append({"damage": dmg, "hp_before": worst_hp + dmg.min,
                      "tick": tick})

        if possible is None and best_hp <= 0:
            possible = turn
        if guaranteed is None and worst_hp <= 0:
            guaranteed = turn
            break

        if best_tick:
            best_hp += best_tick.net
            moved = True
        if tick:
            worst_hp += tick.net
            moved = True

        if possible is None and best_hp <= 0:
            possible = turn
        if worst_hp <= 0:
            guaranteed = turn
            break

        # 기술도 안 통하고 정산도 안 깎으면 영원히 안 쓰러진다.
        # 정산 검사 뒤에 두는 이유: 무효기라도 맹독은 계속 쌓인다.
        if dmg.max == 0 and (tick is None or tick.net >= 0):
            break

    return {
        "guaranteed": guaranteed,
        "possible": possible,
        "text": _ko_text(guaranteed, possible, max_turns, moved),
        "turns": turns,
        "residual": moved,
    }


def _tick(pokemon, ctx, rules, turn):
    """한 마리의 턴 종료 정산. 아무 일도 안 일어나면 None.

    누구의 것인지는 넘기는 BattlePokemon 이 정한다 — 공격자 몫을 재고 싶어지면
    공격자를 넘기면 된다. 예전에는 ctx 에서 defender_* 만 골라 넘겼는데,
    그때는 이 함수가 "방어자 전용" 이 되어 있었다.
    """
    tick = residual.end_of_turn(
        pokemon, pokemon.hp_now(),
        condition=pokemon.condition,
        weather=ctx.weather,
        terrain=ctx.terrain,
        grounded=pokemon.grounded,
        rules=rules,
        # 맹독은 판이 시작하고 몇 턴째인가로 센다. 이 계산의 1턴째가
        # 맹독의 1턴째라는 보장이 없어서 ctx 의 시작값에 더한다.
        toxic_turn=ctx.toxic_turn + turn - 1,
    )
    return tick or None


def _ko_text(guaranteed, possible, max_turns, residual=False):
    """판정 한 줄.

    ── 지속 데미지가 섞이면 '타' 가 '턴' 이 된다 ──
      확정 2타는 "두 방이면 쓰러진다" 는 뜻이다. 그런데 맹독으로 쓰러뜨린
      판은 두 방이 아니라 두 턴이다 — 세 번째 방을 안 넣어도 죽는다.
      같은 말로 적으면 계산기를 믿고 세 방을 준비하게 된다.
    """
    unit = "턴" if residual else "타"
    if guaranteed is not None and guaranteed == possible:
        return f"확정 {guaranteed}{unit}"
    if possible is not None:
        # 최고 난수는 쓰러뜨리는데 최저 난수는 못 쓰러뜨리는 구간
        return f"난수 {possible}{unit}" + (
            f" (확정 {guaranteed}{unit})" if guaranteed is not None else "")
    return f"{max_turns}{unit} 이내로는 쓰러지지 않음"
