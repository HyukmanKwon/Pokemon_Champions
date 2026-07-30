"""내 포켓몬 6마리의 스펙을 들고 있다가 Pokemon 객체로 만들어주는 모듈.

스펙(이름/SP/성격/특성/도구/기술)과 실제로 빌드된 Pokemon 객체는 다르다.
배틀 중에는 build_team() 이 만들어준 Pokemon 객체의 rank/condition 이 바뀔 수
있지만, 그건 스펙에는 반영되지 않는다. 배틀이 끝나면 스펙으로 build_team() 을
다시 부르기만 하면 배틀 이전 상태로 돌아간다.

── 여기에는 print/input 이 없다 ──
  CLI 와 웹 API 가 이 모듈을 그대로 공유한다. 출력 형식을 여기서 정하는
  순간 둘 중 하나는 못 쓰게 된다.

── 저장 위치 ──
  data/my_team.json (config.TEAM_PATH). 패키지 안이 아니라 data/ 에 둔다.
  사용자 데이터라서, 코드를 재설치해도 살아남아야 한다.
"""

import copy
import json

from ..config import TEAM_PATH
from ..db.repositories import nature_repo, pokemon_repo
from ..domain import Pokemon
from ..text import normalize
from .stats import calc_stats, make_sp

DEFAULT_TEAM = [
    dict(ko_name="리자몽", sp_values=(0, 0, 0, 32, 2, 32), ko_nature="겁쟁이",
         ability="맹화", item="생명의구슬",
         moves=["냉동빔", "10만볼트", "파도타기", "대지의힘"]),
    dict(ko_name="이상해꽃", sp_values=(2, 0, 0, 32, 32, 0), ko_nature="차분",
         ability="심록", item="신비의물방울",
         moves=["리프블레이드", "씨뿌리기", "수면가루", "벌크업"]),
    dict(ko_name="거북왕", sp_values=(2, 0, 32, 0, 32, 0), ko_nature="의젓",
         ability="급류", item="기합의띠",
         moves=["파도타기", "지진", "고속스핀", "벌크업"]),
    dict(ko_name="피카츄", sp_values=(0, 0, 0, 32, 2, 32), ko_nature="명랑",
         ability="정전기", item="전기구슬",
         moves=["10만볼트", "볼트태클", "아이언테일", "전광석화"]),
    dict(ko_name="잠만보", sp_values=(32, 0, 0, 2, 32, 0), ko_nature="신중",
         ability="먹보", item="맹독구슬",
         moves=["지진", "파도타기", "벌크업", "번개"]),
    dict(ko_name="루카리오", sp_values=(0, 32, 0, 0, 2, 32), ko_nature="고집",
         ability="정의의마음", item="구애스카프",
         moves=["인파이트", "아이언헤드", "대지의힘", "벌크업"]),
]


# ─────────────────────────────────────────────────────────────
# 스펙 저장/수정
# ─────────────────────────────────────────────────────────────

def load_specs():
    """저장된 팀이 있으면 그걸, 없으면 기본 팀을 돌려준다."""
    if TEAM_PATH.exists():
        return json.loads(TEAM_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(DEFAULT_TEAM)


def save_specs(specs):
    """현재 팀 스펙을 그대로 파일에 저장한다."""
    TEAM_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEAM_PATH.write_text(
        json.dumps(specs, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def edit_spec(specs, index, **fields):
    """specs[index] 중 fields 로 넘어온 필드만 바꾼다. 나머지는 그대로 둔다."""
    if not 0 <= index < len(specs):
        raise ValueError(f"슬롯은 0~{len(specs) - 1} 사이여야 합니다: {index}")
    specs[index].update(fields)
    return specs[index]


# ─────────────────────────────────────────────────────────────
# 조립
# ─────────────────────────────────────────────────────────────

def build_pokemon(conn, ko_name, sp_values, ko_nature,
                  ability, item=None, moves=None, condition=None):
    """DB를 읽어 Pokemon 하나를 만든다.

    조회는 repositories 에, 계산은 services.stats 에 맡기고 여기서는
    순서만 정한다.
    """
    ko_name = normalize(ko_name)
    base = pokemon_repo.fetch_base(conn, ko_name)
    sp = make_sp(sp_values)
    nature = nature_repo.fetch_modifiers(conn, ko_nature)

    return Pokemon(
        name=ko_name,
        stats=calc_stats(base, sp, nature),
        ability=ability,
        item=normalize(item) if item else None,
        moves=[normalize(m) for m in (moves or [])],
        condition=condition,
        nature=normalize(ko_nature),
    )


def build_team(conn, specs):
    """스펙 리스트를 읽어 Pokemon 들을 만든다."""
    return [build_pokemon(conn, **spec) for spec in specs]
