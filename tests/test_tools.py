"""도구 14개가 내놓는 모양을 통째로 박아둔다.

── 왜 값을 하나씩 확인하지 않나 ──
  이건 "계산이 맞는가" 를 보는 테스트가 아니다. 그건 test_damage.py 가
  한다. 여기서 알고 싶은 것은 하나다 — 조립 층으로 코드를 옮기는 동안
  모델에게 나가는 JSON 이 바뀌었는가.

  칸을 하나씩 골라 검사하면 안 고른 칸이 조용히 바뀐다. 도구 응답은 칸이
  스무 개 넘는 dict 라 반드시 빠뜨린다. 그래서 응답 전체를 golden/ 에
  적어두고 통째로 대조한다.

── 바뀌었을 때 ──
  일부러 바꾼 것이면 다시 적는다:

      UPDATE_GOLDEN=1 pytest tests/test_tools.py

  그리고 git diff 로 무엇이 달라졌는지 눈으로 본 뒤에 커밋한다. 무심코
  다시 적으면 이 파일은 아무것도 지키지 않는다.

── DB 가 있어야 돈다 ──
  conftest.py 의 db 픽스처가 접속을 못 하면 전부 skip 이다.
"""

import json
import os
from pathlib import Path

import pytest

from pokemon_champions.agent import schemas, tools

GOLDEN = Path(__file__).parent / "golden" / "tools.json"

# (이름, 인자). 도구 14개를 전부 한 번씩은 부르고, 갈래가 있는 곳은
# 여러 번 부른다 — 성공/실패, 거르기 있음/없음, 기본값/명시.
CALLS = [
    ("find_pokemon", {"name": "한카리아스"}),
    ("find_pokemon", {"name": "garchomp"}),          # 영문 슬러그도 같은 답
    ("find_pokemon", {"name": "메가입치트"}),          # 메가폼
    ("find_pokemon", {"name": "없는포켓몬"}),          # error 모양

    ("search_pokemon", {"type": "ice", "min_total": 500,
                        "order_by": "spe", "limit": 5}),
    ("search_pokemon", {"order_by": "bst", "limit": 3}),

    ("type_matchup", {"pokemon": "리자몽"}),
    ("type_matchup", {"pokemon": "없는포켓몬"}),
    ("type_effectiveness", {"attack_type": "ground", "defender": "한카리아스"}),

    ("find_move", {"name": "지진"}),
    ("find_move", {"name": "earthquake"}),
    ("find_move", {"name": "없는기술"}),

    ("moves_of", {"pokemon": "한카리아스", "type": "ice"}),   # 0개
    ("moves_of", {"pokemon": "한카리아스", "type": "ground", "min_power": 80}),

    ("find_ability", {"name": "까칠한피부"}),
    ("find_item", {"name": "기합의띠"}),

    ("calc_damage", {"attacker": {"name": "맘모꾸리"},
                     "defender": {"name": "한카리아스"},
                     "move": "고드름떨구기"}),
    ("calc_damage", {"attacker": {"name": "메가갸라도스", "nature": "고집",
                                  "sp": [0, 32, 0, 0, 0, 32]},
                     "defender": {"name": "한카리아스", "rank": {"b": 2}},
                     "move": "지진", "weather": "sandstorm"}),
    ("calc_damage", {"attacker": {"name": "없는포켓몬"},
                     "defender": {"name": "한카리아스"}, "move": "지진"}),

    ("power_index", {"pokemon": {"name": "메타그로스", "nature": "고집"},
                     "moves": ["지진", "아이언헤드", "없는기술"]}),
    ("bulk_index", {"pokemon": {"name": "하마돈"}}),

    ("my_team", {}),                              # 활성 덱
    ("my_team", {"deck": "테스트 덱"}),             # 이름으로 부른 덱
    ("my_team", {"deck": "없는 덱"}),               # 못 찾으면 활성 덱으로
    ("list_decks", {}),
    ("team_weaknesses", {}),
    ("usage_stats", {"pokemon": "한카리아스"}),
]


def _key(name, args):
    """golden 파일 안에서 이 호출을 가리킬 이름."""
    return f"{name}({json.dumps(args, ensure_ascii=False, sort_keys=True)})"


@pytest.fixture
def results(db, fixed_team):
    """도구 14개를 전부 한 번씩 부른 결과.

    db 가 없으면 그 픽스처가 skip 시킨다. fixed_team 은 엔트리를 고정한다.

    도구는 자기 커넥션을 스스로 열고 캐시한다(_state). 끝나면 닫아서 다음
    테스트에 남지 않게 한다 — 지금은 tools 가 conn 을 혼자 들고 있어서
    이렇게 뒤처리를 해야 한다. 조립 층이 생기면 conn 을 인자로 받게 되고
    이 줄은 사라진다.
    """
    out = {}
    for name, args in CALLS:
        out[_key(name, args)] = tools.call(name, args)
    tools.close()
    return out


def test_golden(results):
    """지금 응답이 박아둔 것과 같은가."""
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(
            json.dumps(results, ensure_ascii=False, indent=2,
                       sort_keys=True, default=str) + "\n",
            encoding="utf-8")
        pytest.skip("golden 을 다시 적었습니다. git diff 로 확인하세요")

    assert GOLDEN.exists(), (
        f"{GOLDEN} 가 없습니다. UPDATE_GOLDEN=1 pytest 로 먼저 만드세요")

    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    # dict 를 그대로 비교하면 float·tuple 이 JSON 왕복에서 갈린다.
    have = json.loads(json.dumps(results, ensure_ascii=False, default=str))

    assert set(have) == set(want), "부른 도구 목록이 달라졌습니다"
    for key in want:
        assert have[key] == want[key], f"{key} 의 응답이 달라졌습니다"


def test_모든_도구가_한_번은_불린다():
    """CALLS 가 도구 하나를 빠뜨리면 그 도구는 아무도 안 지킨다."""
    called = {name for name, _ in CALLS}
    assert called == set(tools.HANDLERS), (
        f"안 부른 도구: {sorted(set(tools.HANDLERS) - called)}")


def test_스키마와_함수의_짝():
    """import 때 검사하는 것과 같은 것. 깨지면 여기서도 잡힌다."""
    assert set(schemas.TOOLS) == set(tools.HANDLERS)


def test_없는_도구는_값으로_돌려준다():
    """예외를 올리면 루프가 죽는다. DB 없이도 도는 검사다."""
    assert "error" in tools.call("그런건없다", {})
    assert "error" in tools.call("find_move", {"틀린인자": 1})
