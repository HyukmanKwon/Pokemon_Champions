"""테스트 공통 준비.

── DB 를 쓰는 테스트는 따로 ──
  기존 테스트는 조회를 가짜로 바꿔 DB 없이 돈다. 규칙만 검증하니 그게 맞다.

  그런데 agent/tools.py 가 하는 일 자체가 "DB 를 읽어 모델이 읽을 모양으로
  만드는 것" 이다. 조회를 가짜로 바꾸면 내가 적어둔 가짜의 모양을 검증하게
  되고, 정작 알고 싶은 것(진짜 데이터가 어떤 모양으로 나오는가)은 못 본다.

  그래서 db 픽스처는 진짜로 접속하고, 접속이 안 되면 skip 한다. DB 없는
  곳에서도 pytest 는 그대로 초록이다.
"""

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def db():
    """진짜 DB 커넥션. 못 열면 그 테스트들만 건너뛴다."""
    from pokemon_champions.db import connect

    try:
        conn = connect()
    except Exception as e:      # noqa: BLE001 - 접속 실패 사유는 여럿이다
        pytest.skip(f"DB 에 접속할 수 없습니다: {type(e).__name__}")
    yield conn
    conn.close()


@pytest.fixture
def fixed_team(tmp_path, monkeypatch):
    """덱 파일을 임시 폴더에 하나 만들어 그것만 보게 한다.

    ── 왜 고정하나 ──
      my_team·team_weaknesses 는 사용자의 덱을 읽는다. 진짜 파일을 그대로
      쓰면 덱을 고칠 때마다 테스트가 깨진다 — 코드가 바뀐 게 아닌데
      빨개지는 테스트는 곧 아무도 안 본다.

    ── 왜 사본인가 ──
      덱은 읽기만 하는 게 아니다. PATCH /api/team/{index} 와 덱 만들기·
      지우기가 전부 파일에 쓴다. 진짜 파일을 가리키면 테스트 한 번에
      사용자의 덱이 덮어써진다. 다시 만들 수 없는 파일을 지키는 것과
      같은 이유이고, 이쪽이 더 위험하다 — 덱은 다시 만들 수 없다.

    ── my_team.json 도 막는다 ──
      decks.json 이 없으면 roster 가 my_team.json 에서 옮겨온다. 그
      경로도 임시 폴더로 돌려놓지 않으면 테스트가 사용자의 엔트리를 읽는다.
    """
    from pokemon_champions.usecases import roster

    box = tmp_path / "decks.json"
    slots = json.loads(
        (Path(__file__).parent / "data" / "team.json").read_text(encoding="utf-8"))
    box.write_text(json.dumps(
        {"active": "test1",
         "decks": [{"id": "test1", "name": "테스트 덱", "slots": slots}]},
        ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(roster, "DECKS_PATH", box)
    monkeypatch.setattr(roster, "TEAM_PATH", tmp_path / "없는-my_team.json")
    return box
