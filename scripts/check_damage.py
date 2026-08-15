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
from pokemon_champions.db.repositories import rules_repo
from pokemon_champions.calc.damage import Rules
from pokemon_champions.usecases import battle, roster

# 대조용 기준 케이스. 자속·상성·도구·특성이 골고루 걸리도록 골랐다 —
# 전부 등배 무보정이면 대조해도 얻는 게 없다.
#
# ── 왜 스펙을 여기 적어두나 ──
#   예전에는 my_team.json 에서 이름으로 찾아 썼다. 그런데 엔트리는 바뀌는
#   물건이다. 팀에서 리자몽을 빼는 순간 케이스 다섯 개가 조용히 "건너뜀"
#   으로 바뀌고, 대조 도구가 아무 일도 안 하면서 통과한 것처럼 보인다.
#   기준값은 움직이지 않아야 해서 여기에 못 박는다.
#
#   {} 는 무보정(SP 0 · 성실 · 1번 특성 · 도구 없음)이다.
CASES = [
    # (공격자 스펙, 기술, 방어자 스펙, 설명)
    ({"ko_name": "리자몽", "item": "생명의구슬"}, "화염방사",
     {"ko_name": "이상해꽃"}, "자속 + 약점 2배 + 생명의구슬"),
    ({"ko_name": "리자몽"}, "기합구슬",
     {"ko_name": "잠만보"}, "비자속 + 약점"),
    ({"ko_name": "거북왕"}, "파도타기",
     {"ko_name": "리자몽", "item": "기합의띠"}, "자속 + 약점"),
    ({"ko_name": "이상해꽃", "item": "신비의물방울"}, "기가드레인",
     {"ko_name": "거북왕"}, "자속 + 약점 + 타입강화도구(풀에는 안 걸림)"),
    ({"ko_name": "피카츄", "item": "전기구슬"}, "10만볼트",
     {"ko_name": "거북왕"}, "자속 + 약점 + 전기구슬(공격 2배)"),
    ({"ko_name": "잠만보"}, "지진",
     {"ko_name": "피카츄"}, "비자속 + 약점"),
    ({"ko_name": "루카리오", "item": "구애스카프"}, "인파이트",
     {"ko_name": "잠만보"}, "자속 + 약점 + 구애스카프(속도만)"),
]


def build(conn, specs, want, use_team=True):
    """이름 또는 부분 스펙을 받아 조립 층에 넘길 스펙을 만든다.

    ── 왜 팀에 없어도 세우나 ──
      예전에는 my_team.json 에 있는 6마리만 됐다. 대조는 "이 조합의 값이
      맞는가" 를 보는 일이지 "내가 그 포켓몬을 쓰는가" 와 무관하다.
      엔트리에 없다고 못 재면, 정작 재보고 싶은 상대는 늘 못 잰다.

    ── use_team ──
      CASES 는 False 로 부른다. 기준값이 엔트리를 따라가면 팀을 고칠 때마다
      숫자가 달라져서, 어제 맞춰둔 값과 대조할 수가 없다. 반대로 인자로
      직접 물을 때는 True 다 — 내 잠만보가 실제로 몇 대 버티는지가 궁금한
      것이지, 무보정 잠만보가 궁금한 게 아니다.

      어느 쪽이든 안 적은 칸은 조립 층이 무보정(SP 0 · 성실 · 1번 특성)
      으로 채운다. 웹 계산기·LLM 도구와 같은 코드라 세 쪽 답이 갈리지 않는다.
    """
    want = {"ko_name": want} if isinstance(want, str) else dict(want)
    ko = want["ko_name"]

    base = next((dict(s) for s in specs if s["ko_name"] == ko), None) \
        if use_team else None
    if base is None:
        # 안 적은 칸은 조립 층이 무보정(SP 0 · 성실 · 1번 특성)으로 채운다.
        # 예전에는 그 기본값을 여기 또 적어뒀는데, 웹 계산기·LLM 도구와
        # 세 벌이 되어 하나를 고치면 나머지가 조용히 갈렸다.
        base = {"ko_name": ko}
    base.update({k: v for k, v in want.items() if k != "ko_name"})
    # 기술 검증은 여기서 할 일이 아니다. 재려는 기술 하나만 따로 넘긴다.
    base.pop("moves", None)

    # 엔트리 파일은 ko_name·ko_nature·sp_values 를 쓴다. 파일 모양은 그대로
    # 두고 여기서 조립 층의 칸 이름으로 옮긴다 — 웹의 CalcSide 도 같은
    # 자리에서 같은 일을 한다.
    return {"name": base["ko_name"], "ability": base.get("ability"),
            "item": base.get("item"), "nature": base.get("ko_nature"),
            "sp": base.get("sp_values"), "condition": base.get("condition")}


def show(conn, specs, rules, attacker_spec, move_name, defender_spec, note="",
         use_team=True):
    # 판 설정을 안 넘기면 싱글·랭크 0·맑음이다. 포케챔스 기본값과 맞춘다.
    shot = battle.one_hit(conn, rules,
                          build(conn, specs, attacker_spec, use_team),
                          build(conn, specs, defender_spec, use_team),
                          move_name)
    attacker, defender, move = shot.attacker, shot.defender, shot.move
    dmg, ko = shot.damage, shot.ko
    lo, hi = shot.percent()

    print(f"── {attacker.name} → {move_name} → {defender.name}"
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
        specs = roster.slots()
        rules = Rules(
            chart=rules_repo.fetch_type_chart(conn),
            weathers=rules_repo.fetch_weathers(conn),
            terrains=rules_repo.fetch_terrains(conn),
            conditions=rules_repo.fetch_status_conditions(conn),
        )

        print("포케챔스 계산기: https://pokemon.yodams.com/calc/damage")
        print("싱글 · 랭크 0 · 날씨 없음 · 급소 없음 기준입니다.")
        print()

        if args.names:
            # 인자로 물을 때는 엔트리 스펙을 쓴다. 내 포켓몬이 실제로 몇 대
            # 버티는지가 궁금한 것이지 무보정 값이 궁금한 게 아니다.
            try:
                show(conn, specs, rules, *args.names, use_team=True)
            except ValueError as e:
                # 오타는 사용자 실수지 버그가 아니다. 트레이스백을 쏟으면
                # 무엇을 잘못 적었는지가 그 아래 묻힌다.
                raise SystemExit(str(e))
        else:
            print("기준 케이스는 엔트리와 무관하게 무보정"
                  "(SP 0 · 성실 · 1번 특성)으로 세웁니다.\n")
            for case in CASES:
                try:
                    show(conn, specs, rules, *case, use_team=False)
                except (SystemExit, ValueError) as e:
                    print(f"── {case[0]['ko_name']} → {case[1]}"
                          f" → {case[2]['ko_name']}: 건너뜀 ({e})")
                    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
