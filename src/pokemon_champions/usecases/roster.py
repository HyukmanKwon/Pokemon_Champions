"""덱 보관 — 여러 벌을 들고, 지금 보고 있는 한 벌을 가리킨다.

── 왜 DB 가 아닌가 ──
  이 프로젝트의 Postgres 는 ETL 이 PokeAPI 에서 통째로 다시 만드는 참조
  데이터다. 재구축 절차가 손으로 DROP TABLE ... CASCADE 하는 방식이라,
  deck_slots 가 pokemons 를 참조하면 다음 재구축 때 덱까지 같이 날아간다.

  덱은 data/overrides/ 와 같은 성격이다 — 사람이 만든, 다시 만들 수 없는
  값. 그래서 파일이다.

── 왜 한 파일인가 ──
  덱마다 파일을 나누면 파일명이 덱 이름이 되는데, 덱 이름은 한글이고
  공백·슬래시·중복이 다 들어온다. 그걸 전부 막느니 이름은 값으로 두고
  id 로 찾는 편이 낫다.

── 원자적으로 쓴다 ──
  예전 my_team.json 은 6칸짜리라 저장 중에 죽어도 잃는 게 하나였다.
  이제 덱 전부가 한 파일에 있다. 임시 파일에 쓰고 os.replace 로 갈아끼운다.
"""

import copy
import json
import os
import uuid

from ..config import DECKS_PATH, MAX_DECKS, TEAM_PATH, TEAM_SIZE
from . import team

# 처음 열었을 때 보게 될 덱 이름. 마이그레이션에도 이 이름을 쓴다.
FIRST_DECK_NAME = "내 엔트리"


def _new_id():
    """덱 id. 이름이 바뀌어도 가리키는 곳이 안 흔들려야 한다."""
    return uuid.uuid4().hex[:8]


def _deck(name, slots):
    return {"id": _new_id(), "name": name, "slots": copy.deepcopy(slots)}


def load():
    """덱 전부와 활성 덱 id.

    decks.json 이 없으면 만들어 준다:
      my_team.json 이 있으면 그 6칸을 첫 덱으로 옮기고,
      없으면 기본 팀으로 한 벌 만든다.

    옮긴 뒤에도 my_team.json 은 지우지 않는다. 다시 만들 수 없는 파일을
    자동으로 없애는 것은 이 프로젝트가 하지 않기로 한 일이다.
    """
    if DECKS_PATH.exists():
        return json.loads(DECKS_PATH.read_text(encoding="utf-8"))

    slots = (json.loads(TEAM_PATH.read_text(encoding="utf-8"))
             if TEAM_PATH.exists() else copy.deepcopy(team.DEFAULT_TEAM))
    book = {"decks": [_deck(FIRST_DECK_NAME, slots)], "active": None}
    book["active"] = book["decks"][0]["id"]
    save(book)
    return book


def save(book):
    """통째로 저장한다. 쓰다 죽어도 이전 파일이 그대로 남는다."""
    DECKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DECKS_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(book, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    os.replace(tmp, DECKS_PATH)


def find(book, deck_id=None):
    """덱 하나. deck_id 가 없으면 활성 덱. 없는 덱이면 LookupError.

    ── 왜 기본값이 활성 덱인가 ──
      "내 팀" 은 사용자가 화면에서 보고 있는 덱이다. 부르는 쪽이 매번
      어느 덱인지 정하게 하면, 어딘가 한 곳이 빠뜨리고 엉뚱한 덱을 답한다.

    ── 왜 LookupError 인가 ──
      "없는 덱" 과 "규칙 위반(마지막 덱 삭제)" 은 부르는 쪽이 다르게
      다뤄야 한다 — 웹에서는 404 와 400 이다. 둘 다 ValueError 로 올리면
      메시지 글자를 보고 갈라야 하고, 문구를 다듬는 순간 조용히 깨진다.
    """
    wanted = deck_id or book["active"]
    for d in book["decks"]:
        if d["id"] == wanted:
            return d
    raise LookupError(f"그런 덱이 없습니다: {deck_id}")


def by_name(book, name):
    """이름으로 덱 찾기. 없으면 None.

    모델이 "트릭룸 덱은 한카리아스 버텨?" 라고 물을 수 있어야 한다. 다만
    이름은 사람이 붙인 것이라 겹칠 수 있으므로 먼저 찾은 것을 쓴다.
    """
    if not name:
        return None
    key = str(name).strip()
    return next((d for d in book["decks"] if d["name"].strip() == key), None)


def slots(deck_id=None):
    """그 덱의 6칸. 계산과 화면이 다 이걸 통해서 읽는다."""
    return find(load(), deck_id)["slots"]


def summary():
    """덱 목록. 6칸 전부가 아니라 목록에 필요한 것만."""
    book = load()
    return {
        "active": book["active"],
        # 화면이 "새 덱" 버튼을 언제 잠글지 알아야 한다. 눌러보고 나서
        # 오류를 받는 것보다 못 누르게 하는 편이 낫다.
        "max": MAX_DECKS,
        "decks": [{"id": d["id"], "name": d["name"],
                   "size": len(d["slots"]),
                   "members": [s["ko_name"] for s in d["slots"]]}
                  for d in book["decks"]],
    }


# ─────────────────────────────────────────────────────────────
# 고치기 — 전부 파일을 다시 쓴다
# ─────────────────────────────────────────────────────────────

def create(name, slots=None):
    """새 덱. 칸을 안 주면 기본 팀으로 채운다. 상한을 넘으면 ValueError.

    빈 덱으로 시작하지 않는 이유는 화면 때문이다. 여섯 칸이 다 비면
    고칠 대상이 없어서 아무것도 누를 수 없다.

    ── 왜 상한이 있나 ──
      규칙이 아니라 화면의 사정이다(config.MAX_DECKS). 몇 벌이든 만들 수
      있으면 목록이 길어져 어느 덱을 보고 있는지 한눈에 안 들어온다.
      복제 버튼이 한 번에 한 벌씩 늘리는 자리라 특히 그렇다.
    """
    book = load()
    if len(book["decks"]) >= MAX_DECKS:
        raise ValueError(
            f"덱은 {MAX_DECKS}벌까지 만들 수 있습니다. "
            "쓰지 않는 덱을 지우고 다시 시도하세요.")
    deck = _deck(name or "새 덱", slots or team.DEFAULT_TEAM)
    book["decks"].append(deck)
    save(book)
    return deck


def copy_deck(deck_id, name=None):
    """덱 복제. 배분만 바꿔 견줘보는 일이 잦다."""
    src = find(load(), deck_id)
    return create(name or f"{src['name']} 사본", src["slots"])


def rename(deck_id, name):
    book = load()
    deck = find(book, deck_id)
    deck["name"] = name
    save(book)
    return deck


def delete(deck_id):
    """덱 삭제. 마지막 한 벌은 지우지 못한다.

    다 지우면 화면에 아무것도 없고 활성 덱도 없어진다. 그 상태를 다루는
    코드를 곳곳에 두느니 애초에 못 만들게 한다.
    """
    book = load()
    # 있는 덱인지 먼저 본다. 순서가 뒤집히면 없는 id 를 지우려 할 때
    # "마지막 덱은 못 지운다" 는 엉뚱한 말이 나온다.
    deck = find(book, deck_id)
    if len(book["decks"]) <= 1:
        raise ValueError("마지막 덱은 지울 수 없습니다.")
    book["decks"].remove(deck)
    if book["active"] == deck["id"]:
        book["active"] = book["decks"][0]["id"]
    save(book)
    return book["active"]


def set_active(deck_id):
    book = load()
    book["active"] = find(book, deck_id)["id"]
    save(book)
    return book["active"]


def save_slots(slots, deck_id=None):
    """덱의 6칸을 통째로 갈아끼운다. CLI 처럼 여러 칸을 고치고 한 번에
    저장하는 쪽이 쓴다 — 칸마다 저장하면 파일을 여섯 번 다시 쓴다."""
    book = load()
    find(book, deck_id)["slots"] = slots
    save(book)
    return slots


def edit_slot(index, deck_id=None, **fields):
    """한 칸의 일부 필드만 바꾼다. 검증은 team.validate_spec 이 한다."""
    book = load()
    deck = find(book, deck_id)
    if not 0 <= index < len(deck["slots"]):
        raise ValueError(f"슬롯은 0~{len(deck['slots']) - 1} 사이여야 합니다: "
                         f"{index}")
    deck["slots"][index].update(fields)
    save(book)
    return deck["slots"][index]


def check_size(deck):
    """덱 한 벌이 여섯 칸인가. 파일을 손으로 고친 경우를 잡는다."""
    if len(deck["slots"]) != TEAM_SIZE:
        raise ValueError(f"덱은 {TEAM_SIZE}칸이어야 합니다: "
                         f"{deck['name']} ({len(deck['slots'])}칸)")
