"""터미널로 내 포켓몬 팀을 보고 고치는 진입점.

    python main.py

── 화면 표현이 여기 있는 이유 ──
  format_pokemon() 은 예전에 Pokemon.__str__ 이었다. 한글 폭을 계산해 표를
  맞추는 코드인데, 그건 터미널 사정이지 포켓몬의 성질이 아니다. 웹은 같은
  Pokemon 객체를 JSON 으로 내보낸다 — 표현을 도메인 밖으로 빼야 둘 다 된다.
"""

import sys
import unicodedata

from ..db import connect
from ..domain import STAT_LABELS, STAT_ORDER
from ..usecases import team
from ..usecases import roster
from ..text import normalize

FIELDS = ["ko_name", "sp_values", "ko_nature", "ability", "item", "moves"]
LABELS = {
    "ko_name": "이름",
    "sp_values": "SP (H A B C D S, 공백으로 구분)",
    "ko_nature": "성격",
    "ability": "특성",
    "item": "도구",
    "moves": "기술 (쉼표로 구분, 최대 4개)",
}


# ─────────────────────────────────────────────────────────────
# 표현
# ─────────────────────────────────────────────────────────────

def _visual_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text, width):
    return text + " " * (width - _visual_width(text))


def format_pokemon(p):
    """Pokemon 한 마리를 터미널용 여러 줄 문자열로 만든다."""
    labels = [STAT_LABELS[k] for k in STAT_ORDER]
    values = [str(p.stats[k]) for k in STAT_ORDER]
    widths = [_visual_width(label) + 2 for label in labels]
    header = "".join(_pad(label, w) for label, w in zip(labels, widths))
    row = "".join(_pad(value, w) for value, w in zip(values, widths))

    return "\n".join([
        p.name,
        header,
        row,
        p.nature or "-",
        p.item or "없음",
        p.condition or "정상",
        " / ".join(p.moves) if p.moves else "없음",
    ])


def show_slots(specs):
    for i, spec in enumerate(specs, 1):
        print(f"{i}. {spec['ko_name']} ({spec['ability']}, {spec['item']})")


def show_team(pokemons):
    for i, p in enumerate(pokemons, 1):
        print(f"[{i}]")
        print(format_pokemon(p))
        print()


# ─────────────────────────────────────────────────────────────
# 입력
# ─────────────────────────────────────────────────────────────

def ask(prompt):
    return normalize(input(prompt))


def _parse(field, text):
    if field == "sp_values":
        return tuple(map(int, text.split()))
    if field == "moves":
        return [m.strip() for m in text.split(",") if m.strip()]
    return text


def edit_slot(conn, specs, index):
    """빈 입력은 기존 값 유지. build_pokemon()으로 검증하고 실패하면 되돌린다."""
    spec = specs[index]
    before = dict(spec)

    fields = {}
    for field in FIELDS:
        text = ask(f"{LABELS[field]} [{spec[field]}]: ")
        if text:
            fields[field] = _parse(field, text)
    if not fields:
        return

    team.edit_spec(specs, index, **fields)
    try:
        team.build_pokemon(conn, **specs[index])
    except ValueError as e:
        specs[index] = before
        print(f"입력 오류, 수정을 취소합니다: {e}")


# ─────────────────────────────────────────────────────────────

def main():
    conn = connect()
    # 지금 보고 있는 덱. CLI 는 덱을 바꾸지 않는다 — 그건 화면의 일이다.
    specs = roster.slots()
    try:
        while True:
            print()
            show_slots(specs)
            choice = ask("번호를 선택해 수정, v로 상세 보기, q로 종료: ")
            if choice == "q":
                break
            if choice == "v":
                print()
                show_team(team.build_team(conn, specs))
                continue
            if not choice.isdigit() or not (1 <= int(choice) <= len(specs)):
                print("1~6, v, q 중에서 입력하세요.")
                continue
            edit_slot(conn, specs, int(choice) - 1)
    except KeyboardInterrupt:
        print()
    finally:
        roster.save_slots(specs)
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
