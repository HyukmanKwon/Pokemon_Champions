"""
내 포켓몬 6마리의 정보(스펙)를 들고 있다가 Pokemon 객체로 만들어주는 모듈.

스펙(이름/SP/성격/특성/도구/기술)과 실제로 빌드된 Pokemon 객체는 다르다.
배틀 중에는 build_team() 이 만들어준 Pokemon 객체의 rank/condition 이 바뀔 수
있지만, 그건 스펙에는 반영되지 않는다. 배틀이 끝나면 스펙으로 build_team() 을
다시 부르기만 하면 rank/condition 이 없는 배틀 이전 상태로 돌아간다.

여기 있는 함수들은 CLI(main.py)뿐 아니라 나중에 로컬 웹에서도 그대로 재사용할
데이터 계층이라, 입출력(print/input)은 하지 않는다.
"""
import copy
import json
from pathlib import Path

from .database import db
from .stat_calculator import build

SAVE_PATH = Path(__file__).resolve().parent / "my_pokemons.json"

TEAM = [
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


def load_specs():
    """저장된 팀이 있으면 그걸, 없으면 기본 TEAM을 돌려준다."""
    if SAVE_PATH.exists():
        return json.loads(SAVE_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(TEAM)


def save_specs(specs):
    """현재 팀 스펙을 그대로 파일에 저장한다."""
    SAVE_PATH.write_text(
        json.dumps(specs, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def edit_spec(specs, index, **fields):
    """specs[index] 중 fields 로 넘어온 필드만 바꾼다. 나머지는 그대로 둔다."""
    if not 0 <= index < len(specs):
        raise ValueError(f"슬롯은 0~{len(specs) - 1} 사이여야 합니다: {index}")
    specs[index].update(fields)
    return specs[index]


def build_team(conn, specs):
    """스펙 리스트를 읽어 Pokemon 들을 만든다."""
    return [build(conn, **spec) for spec in specs]


def show_team(team):
    """포켓몬 정보를 한 마리씩 확인한다."""
    for i, p in enumerate(team, 1):
        print(f"[{i}]")
        print(p)
        print()


def main():
    conn = db.connect()
    try:
        show_team(build_team(conn, load_specs()))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
