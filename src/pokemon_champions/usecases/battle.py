"""계산기 조립 — 스펙을 받아 계산에 올리고, 쓰인 것과 결과를 돌려준다.

계산기가 셋이므로 진입점도 셋이다. 바깥은 이 셋 말고는 부르지 않는다.

    power(conn, spec, moves)                    결정력  -> Power
    bulk(conn, spec)                            내구력  -> Bulk
    one_hit(conn, rules, atk, dfn, move, ...)   데미지  -> Shot


── 여기가 세 벌이던 자리다 ──
  웹 라우트도, LLM 도구도, check_damage 도 같은 순서를 각자 적고 있었다:
  이름을 찾고 → 안 준 칸을 무보정으로 채우고 → Pokemon 을 세우고 →
  BattleContext 를 엮고 → calc_damage 와 analyze_ko 를 같은 인자로 부른다.

  기본값(성실 · SP 0 · 1번 특성 · allow_mega)이 세 파일에 글자 그대로
  세 벌 있었고, 하나를 고치면 나머지 둘은 조용히 갈렸다. 이제 한 벌이다.

── 돌려주는 것은 뷰가 아니다 ──
  Shot 은 Pokemon 객체와 DamageRange 를 그대로 들고 있다. JSON 이 아니다.
  API 는 아이콘 URL 과 turns 를, 도구는 ko_name 짝과 한 줄 판정을 붙인다 —
  그 차이는 중복이 아니라 각자의 일이다. 계산은 한 번, 모양은 셋.

── 실패는 ValueError 로 ──
  HTTP 상태코드도 {"error": ...} 규약도 여기서는 모른다. 부르는 쪽이
  400 으로 만들지 error dict 로 만들지 정한다.
"""

from dataclasses import dataclass

from ..config import BULK_FACTOR
from ..db.repositories import move_repo, pokemon_repo
from ..calc import damage
from . import team
from ..calc.damage import BattleContext
from . import naming

# 21종 중 유일한 무보정. 안 말했을 때 이걸로 잰다.
NEUTRAL_NATURE = "성실"

# 계산기는 메가리자몽이 상대로 나오는 판을 그대로 물어보는 곳이다.
# 엔트리 금지 규칙을 여기까지 끌고 오면 절반이 계산 불가가 된다.
ALLOW_MEGA = True


@dataclass
class Shot:
    """한 방을 잰 결과. 계산에 실제로 쓰인 것을 같이 들고 있다.

    쓰인 것을 안 돌려주면 부르는 쪽이 "사용자가 말한 조건으로 계산됐다" 고
    믿는다. 특성·도구·성격은 안 말하면 기본값으로 채워지므로, 무엇으로
    쟀는지가 결과만큼 중요하다.
    """

    attacker: object            # Pokemon
    attacker_en: str            # 영문 이름. 한국어만으로는 폼을 못 가린다
    defender: object
    defender_en: str
    move: dict                  # moves 한 행
    ctx: BattleContext
    damage: object              # DamageRange
    ko: dict                    # analyze_ko 결과
    effect: float               # 타입 상성 배수

    def percent(self):
        """방어자 최대 HP 대비 (최소, 최대) %."""
        return self.damage.percent(self.defender.stats.h)


@dataclass
class Scored:
    """결정력을 잰 기술 하나. row 가 None 이면 그런 기술이 없다는 뜻이다.

    없는 기술을 예외로 올리지 않는 이유는, 기술 넷을 한 번에 재는 자리라
    하나가 오타여도 나머지 셋의 답은 나와야 하기 때문이다. 404 로 만들지
    한 줄에 "없는 기술" 이라 적을지는 부르는 쪽이 정한다.
    """

    asked: str                  # 사용자가 적은 이름 그대로
    row: dict = None            # moves 한 행
    index: int = 0
    stab: bool = False


@dataclass
class Power:
    """결정력 — 기술별 화력. 높은 순으로 정렬돼 있다."""

    pokemon: object             # Pokemon
    en: str
    moves: list                 # [Scored, ...]


@dataclass
class Bulk:
    """내구력 — 물리·특수 각각. factor 는 나눈 상수다.

    나눈 값을 안 밝히면 화면이 "HP × 방어" 라고 적고 다른 숫자를 보여준다.
    """

    pokemon: object             # Pokemon
    en: str
    physical: float
    special: float
    factor: float


def move_row(conn, name):
    """기술 이름(한국어·영문 무엇이든) -> moves 한 행. 없으면 None."""
    en = naming.resolve(conn, "moves", name)
    return move_repo.fetch_detail(conn, en) if en else None


def build_side(conn, spec, move_ko=None):
    """느슨한 스펙을 Pokemon 으로. 돌려주는 값은 (Pokemon, 영문 이름).

    스펙은 name 만 필수다. 나머지는 무보정으로 채운다:
    SP 0 · 성실 · 1번 특성 · 도구 없음.

        {"name", "ability", "item", "nature", "sp", "rank",
         "condition", "hp", "grounded"}

    ── 왜 다시 한국어로 되돌리나 ──
      바깥과는 영문으로도 주고받지만, team.build_pokemon 과 그 아래 조회는
      ko_name 을 열쇠로 쓴다. 엔트리 파일을 사람이 한국어로 적기 때문이다.
      그 경계가 여기다. 한국어 이름이 아직 없는 폼은 계산에 못 올리므로
      그렇다고 밝힌다 — 조용히 다른 폼으로 세우면 숫자만 어긋난다.
    """
    en = naming.resolve(conn, "pokemons", spec["name"])
    if en is None:
        raise ValueError(f"'{spec['name']}' 은(는) 포켓몬 목록에 없습니다.")
    ko = naming.ko(conn, "pokemons", en)
    if ko is None:
        raise ValueError(f"'{en}' 은(는) 한국어 이름이 아직 없어 "
                         "계산에 올릴 수 없습니다.")

    ability = naming.to_ko(conn, "abilities", spec.get("ability"))
    if not ability:
        # 특성을 안 말했으면 1번 특성. 무엇으로 쟀는지는 결과에 실려 나간다.
        cands = pokemon_repo.fetch_abilities(conn, ko)
        ability = cands[0] if cands else None

    p = team.build_pokemon(
        conn, ko_name=ko,
        sp_values=spec.get("sp") or [0] * 6,
        ko_nature=(naming.to_ko(conn, "pokemon_natures", spec.get("nature"))
                   or NEUTRAL_NATURE),
        ability=ability,
        item=naming.to_ko(conn, "items", spec.get("item")),
        moves=[move_ko] if move_ko else None,
        condition=spec.get("condition"),
        rank=spec.get("rank"),
        hp=spec.get("hp"),
        grounded=spec.get("grounded", True),
        allow_mega=ALLOW_MEGA,
    )
    return p, en


def context(**battle):
    """판 설정을 BattleContext 하나로.

    한쪽에게 걸리는 것(랭크·상태이상·접지·남은 HP)은 여기 없다. 그건
    build_side 가 Pokemon 에 실어 준다 — 예전에는 같은 스펙을 두 군데로
    나눠 적었고, 그래서 화상 하나를 재는 데 burn 을 두 번 적어야 했다.
    """
    return BattleContext(
        weather=battle.get("weather") or None,
        terrain=battle.get("terrain") or None,
        is_critical=bool(battle.get("is_critical")),
        reflect=bool(battle.get("reflect")),
        light_screen=bool(battle.get("light_screen")),
        is_doubles=bool(battle.get("is_doubles")),
        # 맹독이 몇 턴째인가. 방어자에게 걸린 상태이지만 지금 맹독을 재는
        # 쪽이 방어자뿐이라 판 쪽에 둔다. 공격자 맹독까지 재게 되면
        # 그때 Pokemon 으로 옮긴다.
        toxic_turn=int(battle.get("toxic_turn") or 1),
    )


def one_hit(conn, rules, attacker, defender, move, max_turns=4, **battle):
    """한 방을 잰다. 없는 기술·없는 포켓몬이면 ValueError.

    calc_damage 와 analyze_ko 를 반드시 같은 ctx·rules 로 부른다. 두
    호출이 갈라지면 "데미지는 40% 인데 확정 2타" 같은 답이 나오고, 그건
    읽는 쪽에서 알아챌 방법이 없다.
    """
    m = move_row(conn, move)
    if m is None:
        raise ValueError(f"'{move}' 이라는 기술이 없습니다.")

    atk, atk_en = build_side(conn, attacker, m["ko_name"] or m["name"])
    dfn, dfn_en = build_side(conn, defender)
    ctx = context(**battle)

    return Shot(
        attacker=atk, attacker_en=atk_en,
        defender=dfn, defender_en=dfn_en,
        move=m, ctx=ctx,
        damage=damage.calc_damage(atk, dfn, m, ctx, rules),
        ko=damage.analyze_ko(atk, dfn, m, ctx, rules, max_turns=max_turns),
        effect=damage.type_multiplier(m["type"], dfn.types, rules.chart),
    )


def power(conn, spec, moves):
    """결정력을 잰다. 세울 수 없는 포켓몬이면 ValueError.
    """
    p, en = build_side(conn, spec)

    scored = []
    for asked in moves:
        if not asked:
            continue
        row = move_row(conn, asked)
        if row is None:
            scored.append(Scored(asked=asked))
            continue
        scored.append(Scored(asked=asked, row=row,
                             index=damage.power_index(p, row),
                             stab=row["type"] in p.types))

    # 없는 기술은 0 이라 자연히 뒤로 간다. 결정력이 0 인 변화기와 같은
    # 자리인데, 둘 다 "화력이 없다" 이므로 갈라 놓을 이유가 없다.
    scored.sort(key=lambda s: -s.index)
    return Power(pokemon=p, en=en, moves=scored)


def bulk(conn, spec):
    """내구력을 잰다. 세울 수 없는 포켓몬이면 ValueError."""
    p, en = build_side(conn, spec)
    b = damage.bulk_index(p)
    return Bulk(pokemon=p, en=en, physical=b["physical"],
                special=b["special"], factor=BULK_FACTOR)
