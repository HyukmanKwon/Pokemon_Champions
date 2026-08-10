"""내 계산기의 값을 포케챔스에 그대로 입력해 대조할 수 있게 뽑아준다.

    python -m scripts.check_damage                  기본 케이스 묶음
    python -m scripts.check_damage 리자몽 화염방사 거북왕    한 판만

포케챔스 데미지 계산기: https://pokemon.yodams.com/calc/damage

── 왜 자동 대조가 아닌가 ──
  그 사이트는 JavaScript 로 그려지고 계산도 브라우저에서 한다. 서버에
  값을 물어볼 주소가 없어서 코드로 긁을 수 없다. 그래서 여기서는
  "입력할 조건" 과 "내 계산 결과" 를 나란히 찍어주기만 하고, 눈으로
  맞춰보는 것은 사람이 한다.

  어긋나면 대개 원인이 셋 중 하나다.
    1. modifiers.py 에 그 특성·도구가 아직 없다  (가장 흔하다)
    2. 이름 오타로 표가 안 걸렸다  -> python -m scripts.check_modifiers
    3. 포챔스가 본가와 다른 규칙을 쓴다  -> 그때는 이 프로젝트가 맞다,
       사이트가 아니라 실제 게임과 맞춰야 한다

── 어긋난 케이스를 찾으면 ──
  tests/test_damage.py 에 실제 수치로 박아둔다. 그 테스트 묶음이
  계산기의 신뢰도 그 자체다. (README §5)
"""

import argparse
import sys

from pokemon_champions.db import connection
from pokemon_champions.db.repositories import move_repo, rules_repo
from pokemon_champions.services import damage, team
from pokemon_champions.services.damage import BattleContext, Rules

# 내 팀 기본 엔트리에서 뽑은 조합. 자속·상성·도구·특성이 골고루 걸리도록
# 골랐다 — 전부 등배 무보정이면 대조해도 얻는 게 없다.
CASES = [
    # (공격자, 기술, 방어자, 설명)
    ("리자몽", "화염방사", "이상해꽃", "자속 + 약점 2배 + 생명의구슬"),
    ("리자몽", "기합구슬", "잠만보", "비자속 + 약점"),
    ("거북왕", "파도타기", "리자몽", "자속 + 약점 + 기합의띠(데미지 무관)"),
    ("이상해꽃", "기가드레인", "거북왕", "자속 + 약점 + 신비의물방울"),
    ("피카츄", "10만볼트", "거북왕", "자속 + 약점 + 전기구슬"),
    ("잠만보", "지진", "피카츄", "자속 아님 + 약점"),
    ("루카리오", "인파이트", "잠만보", "자속 + 약점 + 구애스카프"),
]


def fetch_move(conn, ko_name):
    """기술 한 행을 계산에 필요한 모양으로."""
    en = move_repo.fetch_en_name(conn, ko_name)
    if en is None:
        raise SystemExit(f"없는 기술입니다: {ko_name}")
    return move_repo.fetch_detail(conn, en)


def spec_of(specs, ko_name):
    for s in specs:
        if s["ko_name"] == ko_name:
            return s
    raise SystemExit(f"내 팀에 없는 포켓몬입니다: {ko_name}")


def show(conn, specs, rules, attacker_name, move_name, defender_name, note=""):
    attacker = team.build_pokemon(conn, **spec_of(specs, attacker_name))
    defender = team.build_pokemon(conn, **spec_of(specs, defender_name))
    move = fetch_move(conn, move_name)

    # 싱글·랭크 0·맑음. 포케챔스 기본값과 맞춘다.
    ctx = BattleContext()
    dmg = damage.calc_damage(attacker, defender, move, ctx, rules)
    ko = damage.analyze_ko(attacker, defender, move, ctx, rules)
    lo, hi = dmg.percent(defender.stats.h)

    print(f"── {attacker_name} → {move_name} → {defender_name}"
          + (f"  ({note})" if note else ""))
    print(f"   공격자  {attacker.stats.a}/{attacker.stats.c} "
          f"타입 {'·'.join(attacker.types)} "
          f"특성 {attacker.ability} 도구 {attacker.item or '없음'}")
    print(f"   방어자  HP {defender.stats.h} 방어 {defender.stats.b} "
          f"특방 {defender.stats.d} 타입 {'·'.join(defender.types)} "
          f"특성 {defender.ability} 도구 {defender.item or '없음'}")
    print(f"   기술    {move['ko_name']} {move['type']} {move['category']} "
          f"위력 {move['power']}")
    print(f"   데미지  {dmg.min}~{dmg.max}  ({lo:.1f}~{hi:.1f}%)  {ko['text']}")
    print(f"   난수 16 {dmg.rolls}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*",
                        help="공격자 기술 방어자 (안 주면 기본 묶음 전부)")
    args = parser.parse_args()

    if args.names and len(args.names) != 3:
        parser.error("공격자, 기술, 방어자 셋을 주세요.")

    with connection() as conn:
        specs = team.load_specs()
        rules = Rules(
            chart=rules_repo.fetch_type_chart(conn),
            weathers=rules_repo.fetch_weathers(conn),
            terrains=rules_repo.fetch_terrains(conn),
        )

        print("포케챔스 계산기: https://pokemon.yodams.com/calc/damage")
        print("싱글 · 랭크 0 · 날씨 없음 · 급소 없음 기준입니다.")
        print()

        if args.names:
            show(conn, specs, rules, *args.names)
        else:
            for case in CASES:
                try:
                    show(conn, specs, rules, *case)
                except (SystemExit, ValueError) as e:
                    print(f"── {case[0]} → {case[1]} → {case[2]}: 건너뜀 ({e})")
                    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
