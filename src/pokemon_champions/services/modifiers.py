"""특성·도구가 데미지에 거는 보정을 표로 모아둔 곳.

── 왜 DB가 아니라 여기인가 ──
  abilities.effect 에는 영어 설명문만 있다. "Powers up Fire-type moves when
  the Pokémon's HP is low." 에서 1.5 라는 숫자와 "HP 1/3 이하" 라는 조건을
  코드가 뽑아낼 방법이 없다. 결국 사람이 한 번은 숫자로 적어야 하고,
  그 결과는 수집한 데이터가 아니라 게임 규칙이다. 규칙은 config 와 같은
  자리에 두는 편이 맞다 — 레귤레이션이 바뀌면 여기만 고친다.

── 왜 4096 정수인가 ──
  1.5 가 아니라 6144 로 적는다. 본가가 실수 곱셈을 안 쓰기 때문인데,
  자세한 이유는 services/damage.py 의 첫 주석에 있다.

── 키가 틀리면 조용히 틀린다 ──
  표의 키는 한국어 이름이다. Pokemon 객체가 한국어로 들고 다니기 때문인데,
  오타가 나면 예외가 아니라 "보정이 안 걸린 값"이 나온다. 그래서 검사
  스크립트를 같이 둔다. 표를 고치면 반드시 돌린다.

      python -m scripts.check_modifiers

  DB의 abilities.ko_name / items.ko_name 에 없는 키를 전부 찾아준다.

── 어떻게 늘리나 ──
  아래 표에 (이름, 배수, 조건) 을 한 줄 더한다. 조건은 Situation 하나를
  받아 True/False 를 주는 함수다. 다른 파일은 건드릴 일이 없어야 한다.

  전부 채우지 않았다. 대전에서 실제로 보이는 것부터 넣었고, 빠진 특성은
  보정 없음으로 지나간다. 포케챔스와 대조하다 어긋나면 그게 빠진 줄이다.
"""

from ..config import MOD_ONE

# 자주 쓰는 배수. 4096 = 1.0
X0_5, X0_75 = 2048, 3072
X1_1, X1_2, X1_3, X1_5, X2 = 4506, 4915, 5325, 6144, 8192
LIFE_ORB = 5324          # 1.3 인데 본가 상수가 5324 라 따로 적는다

PHYSICAL, SPECIAL = "physical", "special"


# ─────────────────────────────────────────────────────────────
# 조건에 쓰는 짧은 도우미. 전부 Situation 하나만 받는다.
# 인자를 늘리면 표에 lambda 가 길어지고, 안 읽히는 표는 표가 아니다.
# ─────────────────────────────────────────────────────────────

def _mtype(sit):
    return sit.move["type"]


def _is(category):
    return lambda sit: sit.move["category"] == category


def _flag(name):
    return lambda sit: bool(sit.move.get(name))


def _type_is(name):
    return lambda sit: _mtype(sit) == name


def _pinch(type_name):
    """궁지 특성 — 그 타입 기술이고 공격자 HP 가 1/3 이하일 때만."""
    return lambda sit: (_mtype(sit) == type_name
                        and sit.attacker_hp * 3 <= sit.attacker.stats.h)


def _always(sit):
    return True


# ─────────────────────────────────────────────────────────────
# 공격 실능 보정 — 랭크를 적용한 뒤에 곱한다
# ─────────────────────────────────────────────────────────────

ATTACK_ABILITIES = {
    "의욕":       (X1_5, _is(PHYSICAL)),   # 명중률 0.8 은 데미지와 무관해 여기 없다
    "근성":       (X1_5, lambda s: s.move["category"] == PHYSICAL
                   and bool(s.attacker.condition)),
    "심록":       (X1_5, _pinch("grass")),
    "맹화":       (X1_5, _pinch("fire")),
    "급류":       (X1_5, _pinch("water")),
    "벌레의소식": (X1_5, _pinch("bug")),
    "태양의힘":   (X1_5, lambda s: s.weather == "sun"
                   and s.move["category"] == SPECIAL),
}

ATTACK_ITEMS = {
    "구애머리띠": (X1_5, _is(PHYSICAL)),
    "구애안경":   (X1_5, _is(SPECIAL)),
    # 특정 포켓몬 전용 도구. 이름으로 판정하는 게 께름칙하지만, "이 도구가
    # 누구에게 붙는가" 는 DB 어디에도 없다.
    "전기구슬":   (X2, lambda s: s.attacker.name == "피카츄"),
}

# 상대 특성이 내 공격을 깎는 경우. 방어 보정으로 넣으면 화상·랭크와
# 곱셈 순서가 달라져 1 이 어긋난다. 본가가 공격 쪽에 거는 것을 따른다.
ATTACK_DEBUFF_BY_DEFENDER = {
    "두꺼운지방": (X0_5, lambda s: _mtype(s) in ("fire", "ice")),
}


# ─────────────────────────────────────────────────────────────
# 방어 실능 보정
# ─────────────────────────────────────────────────────────────

DEFENSE_ABILITIES = {
    "이상한비늘": (X1_5, lambda s: s.move["category"] == PHYSICAL
                   and bool(s.defender.condition)),
}

DEFENSE_ITEMS = {
    "돌격조끼": (X1_5, _is(SPECIAL)),
    # 진화의휘석은 "진화가 남은 포켓몬"만 받는다. 그 판정에 필요한 진화
    # 관계가 DB에 없어서 지녔으면 걸리는 것으로 둔다. 진화 테이블이
    # 생기면 조건을 넣는다.
    "진화의휘석": (X1_5, _always),
}


# ─────────────────────────────────────────────────────────────
# 기술 위력 보정
# ─────────────────────────────────────────────────────────────

POWER_ABILITIES = {
    "테크니션": (X1_5, lambda s: (s.move.get("power") or 0) <= 60),
    "철주먹":   (X1_2, _flag("is_punch")),
    "옹골찬턱": (X1_5, _flag("is_bite")),
    "예리함":   (X1_5, _flag("is_slicing")),
    "메가런처": (X1_5, _flag("is_pulse")),
    # 반동기는 drain 이 음수다 (schema.py: "준 데미지의 % 회복. 음수면 반동")
    "이판사판": (X1_2, lambda s: (s.move.get("drain") or 0) < 0),
    "우격다짐": (X1_3, lambda s: (s.move.get("ailment_chance") or 0) > 0),
}

POWER_ITEMS = {
    "펀치글러브": (X1_1, _flag("is_punch")),
    "힘의머리띠": (X1_1, _is(PHYSICAL)),
    "박식안경":   (X1_1, _is(SPECIAL)),
}
# 여기 없는 것 중 자주 물어보는 것들:
#   조임밴드   조이기 지속 데미지를 올린다. 기술 위력이 아니라 턴 끝 정산이라
#              residual.py 쪽이고, 조이기 상태를 아직 안 들고 있다
#   메트로놈   같은 기술을 연속으로 쓴 횟수를 세야 한다. 한 방을 재는
#              이 계산기에는 그 횟수가 없다

# 타입 강화 도구는 전부 1.2 라서 한 줄씩 적지 않고 여기 모은다.
# 어느 도구가 어느 타입인지는 DB에 없다 — items.category 가
# 'type-enhancement' 라는 것까지만 알려준다.
TYPE_BOOST_ITEMS = {
    "이상한부적": "normal",   "검은띠": "fighting",   "예리한부리": "flying",
    "독바늘": "poison",       "부드러운모래": "ground", "단단한돌": "rock",
    "은빛가루": "bug",        "영혼의구슬": "ghost",  "메탈코트": "steel",
    "목탄": "fire",           "신비의물방울": "water", "기적의씨": "grass",
    "자석": "electric",       "구부러진스푼": "psychic", "녹지않는얼음": "ice",
    "용의이빨": "dragon",     "검은안경": "dark",     "요정의깃털": "fairy",
}


# ─────────────────────────────────────────────────────────────
# 최종 보정 — 자속·상성·화상을 다 곱한 맨 마지막에 걸린다
#
# 순서가 중요하다. 색안경(반감을 2배로)은 상성을 곱한 뒤에 걸려야
# "반감인데 2배" 가 되지, 상성 전에 걸면 그냥 위력 2배가 된다.
# ─────────────────────────────────────────────────────────────

FINAL_ATTACKER_ABILITIES = {
    "색안경":   (X2, lambda s: s.type_eff < 1),
    "스나이퍼": (X1_5, lambda s: s.ctx.is_critical),
}

FINAL_DEFENDER_ABILITIES = {
    "멀티스케일": (X0_5, lambda s: s.defender_hp >= s.defender.stats.h),
    "하드록":     (X0_75, lambda s: s.type_eff > 1),
    "필터":       (X0_75, lambda s: s.type_eff > 1),
    "프리즘아머": (X0_75, lambda s: s.type_eff > 1),
}

FINAL_ATTACKER_ITEMS = {
    "생명의구슬": (LIFE_ORB, _always),
    "달인의띠":   (X1_2, lambda s: s.type_eff > 1),
}

# ── 약점 반감 열매 ────────────────────────────────────────────
# 그 타입의 "효과가 뛰어난" 기술을 맞을 때만 데미지가 반으로 준다. 한 번
# 쓰면 없어지지만, 이 계산기는 한 방을 재는 곳이라 소모는 보지 않는다 —
# 두 방째를 물어보고 싶으면 도구를 빼고 다시 재면 된다.
#
# 이름은 data/overrides/item_ko_names.json 에서 가져왔다. 사람이 확인한
# 값이라 추측이 섞이지 않는다. 오타가 나도 예외가 아니라 "열매가 영영 안
# 걸린 값" 이 나오므로 python -m scripts.check_modifiers 로 거른다.
RESIST_BERRIES = {
    "오카열매": "fire",       "꼬시개열매": "water",   "초나열매": "electric",
    "린드열매": "grass",      "플카열매": "ice",       "로플열매": "fighting",
    "으름열매": "poison",     "슈캐열매": "ground",    "바코열매": "flying",
    "야파열매": "psychic",    "리체열매": "bug",       "루미열매": "rock",
    "수불열매": "ghost",      "하반열매": "dragon",    "마코열매": "dark",
    "바리비열매": "steel",    "로셀열매": "fairy",
}

# 카리열매만 규칙이 다르다. 노말은 약점이 될 수 없어서 "효과가 뛰어날 때"
# 조건을 달면 영영 안 걸린다. 등배에서도 반감한다.
CHILAN_BERRY = "카리열매"


# ─────────────────────────────────────────────────────────────
# 타입 면역 — 배수가 0 이 아니라 특성·도구가 통째로 막는 경우
# ─────────────────────────────────────────────────────────────

IMMUNE_ABILITIES = {
    "부유":         _type_is("ground"),
    "타오르는불꽃": _type_is("fire"),
    "저수":         _type_is("water"),
    "마중물":       _type_is("water"),
    "축전":         _type_is("electric"),
    "피뢰침":       _type_is("electric"),
    "전기엔진":     _type_is("electric"),
    "초식":         _type_is("grass"),
    "흙먹기":       _type_is("ground"),
    "방음":         _flag("is_sound"),
    "방탄":         _flag("is_bullet"),
    "방진":         _flag("is_powder"),
    "바람타기":     _flag("is_wind"),
    "풍력발전":     _flag("is_wind"),
}

IMMUNE_ITEMS = {
    "방진고글": _flag("is_powder"),
}

# 적응력만 자속이 2배다. 나머지는 전부 1.5
STAB_ABILITIES = {"적응력": X2}


# ─────────────────────────────────────────────────────────────
# 표를 읽어 배수 목록을 만드는 함수들
#
# 부르는 쪽(damage.py)은 이 여섯 함수만 안다. 표가 어떻게 생겼는지,
# 특성인지 도구인지는 몰라도 된다.
# ─────────────────────────────────────────────────────────────

def _collect(table, key, sit):
    """표에서 key 를 찾아 조건이 맞으면 배수를, 아니면 아무것도 안 준다."""
    entry = table.get(key)
    if entry is None:
        return []
    mult, when = entry
    return [mult] if when(sit) else []


def attack_mods(sit):
    return (_collect(ATTACK_ABILITIES, sit.attacker.ability, sit)
            + _collect(ATTACK_ITEMS, sit.attacker.item, sit)
            + _collect(ATTACK_DEBUFF_BY_DEFENDER, sit.defender.ability, sit))


def defense_mods(sit):
    mods = (_collect(DEFENSE_ABILITIES, sit.defender.ability, sit)
            + _collect(DEFENSE_ITEMS, sit.defender.item, sit))

    # 날씨의 방어 보정은 특성·도구가 아니라 판 상태다. 모래바람의 바위
    # 특수방어 1.5, 눈의 얼음 방어 1.5 — 어느 능력치에 붙는지가 서로
    # 달라서 weathers 테이블이 def_boost_stat 을 따로 들고 있다.
    w = sit.weather_rule
    if w and w.get("def_boost_type") in sit.defender.types:
        wanted = "b" if sit.move["category"] == PHYSICAL else "d"
        if w.get("def_boost_stat") == wanted and w.get("def_boost_mult"):
            mods.append(round(w["def_boost_mult"] * MOD_ONE))
    return mods


def power_mods(sit):
    mods = (_collect(POWER_ABILITIES, sit.attacker.ability, sit)
            + _collect(POWER_ITEMS, sit.attacker.item, sit))

    if TYPE_BOOST_ITEMS.get(sit.attacker.item) == _mtype(sit):
        mods.append(X1_2)

    # 필드는 접지된 쪽에만 걸린다. 위력이 오르는 건 공격자가 접지했을 때,
    # 드래곤 기술이 깎이는 건 방어자가 접지했을 때다.
    t = sit.terrain_rule
    if t:
        if (t.get("boost_type") == _mtype(sit) and t.get("boost_mult")
                and sit.ctx.attacker_grounded):
            mods.append(round(t["boost_mult"] * MOD_ONE))
        if (t.get("weaken_type") == _mtype(sit) and t.get("weaken_mult")
                and sit.ctx.defender_grounded):
            mods.append(round(t["weaken_mult"] * MOD_ONE))
    return mods


def final_mods(sit):
    mods = (_collect(FINAL_ATTACKER_ABILITIES, sit.attacker.ability, sit)
            + _collect(FINAL_ATTACKER_ITEMS, sit.attacker.item, sit)
            + _collect(FINAL_DEFENDER_ABILITIES, sit.defender.ability, sit))

    # 약점 반감 열매. 표가 (배수, 조건) 이 아니라 (이름 -> 타입) 이라
    # _collect 를 못 쓴다 — TYPE_BOOST_ITEMS 와 같은 모양이다.
    item = sit.defender.item
    if RESIST_BERRIES.get(item) == _mtype(sit) and sit.type_eff > 1:
        mods.append(X0_5)
    elif item == CHILAN_BERRY and _mtype(sit) == "normal":
        mods.append(X0_5)

    # 스크린. 급소에는 뚫린다 — 본가 규칙이다.
    # 더블은 0.5 가 아니라 2732/4096 (약 0.667) 이다.
    if not sit.ctx.is_critical:
        screen = (sit.ctx.reflect if sit.move["category"] == PHYSICAL
                  else sit.ctx.light_screen)
        if screen:
            mods.append(2732 if sit.ctx.is_doubles else X0_5)
    return mods


def stab_mod(sit, is_stab):
    if not is_stab:
        return MOD_ONE
    return STAB_ABILITIES.get(sit.attacker.ability, X1_5)


def is_immune(sit):
    """특성·도구가 이 기술을 통째로 막는가. 타입 상성 0배와는 별개다."""
    ability = IMMUNE_ABILITIES.get(sit.defender.ability)
    if ability and ability(sit):
        return True
    item = IMMUNE_ITEMS.get(sit.defender.item)
    return bool(item and item(sit))


def all_ability_keys():
    """검사 스크립트가 쓴다 — 표에 등장하는 특성 이름 전부."""
    return set().union(ATTACK_ABILITIES, ATTACK_DEBUFF_BY_DEFENDER,
                       DEFENSE_ABILITIES, POWER_ABILITIES,
                       FINAL_ATTACKER_ABILITIES, FINAL_DEFENDER_ABILITIES,
                       IMMUNE_ABILITIES, STAB_ABILITIES)


def all_item_keys():
    """검사 스크립트가 쓴다 — 표에 등장하는 도구 이름 전부."""
    return set().union(ATTACK_ITEMS, DEFENSE_ITEMS, POWER_ITEMS,
                       TYPE_BOOST_ITEMS, FINAL_ATTACKER_ITEMS, IMMUNE_ITEMS,
                       RESIST_BERRIES, {CHILAN_BERRY})
