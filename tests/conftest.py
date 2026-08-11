"""테스트 공통 준비.

── overrides 폴더를 격리하는 이유 ──
  data/overrides/ 는 사람이 눈으로 확인해 확정한 값이고 git 에 커밋된다.
  다시 만들 수 없는 파일이라, 테스트가 실수로 한 번 덮어쓰면 그걸로 끝이다
  (실제로 오염된 적이 있다). 그래서 테스트가 도는 동안에는 저장 위치를
  통째로 임시 폴더로 돌려놓는다.

  autouse 라서 overrides 를 쓰지 않는 테스트에도 걸린다. 켜는 것을 잊어서
  진짜 파일이 날아가는 쪽보다, 안 쓰는 테스트에 한 번 더 걸리는 쪽이 낫다.

── DB 를 쓰는 테스트는 따로 ──
  기존 테스트는 조회를 가짜로 바꿔 DB 없이 돈다. 규칙만 검증하니 그게 맞다.

  그런데 agent/tools.py 가 하는 일 자체가 "DB 를 읽어 모델이 읽을 모양으로
  만드는 것" 이다. 조회를 가짜로 바꾸면 내가 적어둔 가짜의 모양을 검증하게
  되고, 정작 알고 싶은 것(진짜 데이터가 어떤 모양으로 나오는가)은 못 본다.

  그래서 db 픽스처는 진짜로 접속하고, 접속이 안 되면 skip 한다. DB 없는
  곳에서도 pytest 는 그대로 초록이다.
"""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_overrides(tmp_path, monkeypatch):
    """overrides 의 저장 위치를 임시 폴더로 바꾼다."""
    from scripts.etl import overrides

    box = tmp_path / "overrides"
    box.mkdir()
    monkeypatch.setattr(overrides, "OVERRIDE_DIR", box)
    # 앞선 테스트가 읽어둔 진짜 파일 내용이 남아 있으면 안 된다.
    monkeypatch.setattr(overrides, "_cache", {})
    return box


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
    """엔트리를 tests/data/team.json 의 사본으로 고정한다.

    ── 왜 고정하나 ──
      my_team·team_weaknesses 는 data/my_team.json 을 읽는다. 그걸 그대로
      쓰면 사용자가 덱을 고칠 때마다 테스트가 깨진다 — 코드가 바뀐 게
      아닌데 빨개지는 테스트는 곧 아무도 안 본다.

    ── 왜 사본인가 ──
      엔트리는 읽기만 하는 게 아니다. PATCH /api/team/{index} 가 파일에
      쓴다. 픽스처 파일을 직접 가리키면 테스트 한 번에 기준값이 덮어써진다.
      overrides 를 임시 폴더로 돌려놓는 것과 같은 이유다.
    """
    from pokemon_champions.services import team

    box = tmp_path / "my_team.json"
    box.write_text(
        (Path(__file__).parent / "data" / "team.json").read_text(encoding="utf-8"),
        encoding="utf-8")
    monkeypatch.setattr(team, "TEAM_PATH", box)
    return box
