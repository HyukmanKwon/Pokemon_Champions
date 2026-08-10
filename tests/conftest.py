"""테스트 공통 준비.

── overrides 폴더를 격리하는 이유 ──
  data/overrides/ 는 사람이 눈으로 확인해 확정한 값이고 git 에 커밋된다.
  다시 만들 수 없는 파일이라, 테스트가 실수로 한 번 덮어쓰면 그걸로 끝이다
  (실제로 오염된 적이 있다). 그래서 테스트가 도는 동안에는 저장 위치를
  통째로 임시 폴더로 돌려놓는다.

  autouse 라서 overrides 를 쓰지 않는 테스트에도 걸린다. 켜는 것을 잊어서
  진짜 파일이 날아가는 쪽보다, 안 쓰는 테스트에 한 번 더 걸리는 쪽이 낫다.
"""

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
