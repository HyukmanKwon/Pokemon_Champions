"""덱 보관 테스트 — 파일에 쓰는 쪽.

── DB 없이 돈다 ──
  roster 는 DB 가 아니라 data/decks.json 을 읽고 쓴다. 그래서 여기서
  막을 것은 커넥션이 아니라 **파일 경로** 다. 진짜 경로를 그대로 쓰면
  테스트 한 번에 사용자의 덱이 날아간다 — 다시 만들 수 없는 파일이다.

  conftest 의 fixed_team 픽스처와 같은 이유이고, 이쪽은 덱을 만들고
  지우는 것까지 하므로 더 위험하다.
"""

import pytest

from pokemon_champions.config import MAX_DECKS
from pokemon_champions.usecases import roster


@pytest.fixture(autouse=True)
def isolated_decks(tmp_path, monkeypatch):
    """덱 파일을 임시 폴더로 돌려놓는다. my_team.json 경로도 같이 막는다.

    my_team.json 을 안 막으면, decks.json 이 없을 때 roster 가 사용자의
    엔트리를 읽어 첫 덱으로 옮긴다.
    """
    monkeypatch.setattr(roster, "DECKS_PATH", tmp_path / "decks.json")
    monkeypatch.setattr(roster, "TEAM_PATH", tmp_path / "없는-my_team.json")
    return tmp_path


def fill_to_max():
    """상한까지 채운다. 첫 덱은 load() 가 만들어 두므로 하나 적게 만든다."""
    while len(roster.load()["decks"]) < MAX_DECKS:
        roster.create(f"덱{len(roster.load()['decks'])}")


def test_처음_열면_덱이_한_벌_생긴다():
    book = roster.load()
    assert len(book["decks"]) == 1
    assert book["active"] == book["decks"][0]["id"]
    assert book["decks"][0]["name"] == roster.FIRST_DECK_NAME


def test_상한까지는_만들어진다():
    fill_to_max()
    assert len(roster.load()["decks"]) == MAX_DECKS


def test_상한을_넘으면_거부한다():
    fill_to_max()
    with pytest.raises(ValueError, match=f"{MAX_DECKS}벌"):
        roster.create("일곱번째")
    # 거부당한 뒤에도 파일이 멀쩡해야 한다
    assert len(roster.load()["decks"]) == MAX_DECKS


def test_복제도_같은_상한에_걸린다():
    # 복제는 create 를 거친다. 여기가 갈리면 복제 버튼으로만 넘길 수 있다.
    fill_to_max()
    active = roster.load()["active"]
    with pytest.raises(ValueError, match=f"{MAX_DECKS}벌"):
        roster.copy_deck(active)


def test_지우면_다시_만들_수_있다():
    fill_to_max()
    roster.delete(roster.load()["decks"][-1]["id"])
    made = roster.create("자리가 났다")
    assert made["name"] == "자리가 났다"
    assert len(roster.load()["decks"]) == MAX_DECKS


def test_마지막_덱은_지울_수_없다():
    only = roster.load()["decks"][0]["id"]
    with pytest.raises(ValueError, match="마지막 덱"):
        roster.delete(only)


def test_목록은_상한을_같이_알려준다():
    # 화면이 '새 덱' 버튼을 언제 잠글지 이 값으로 정한다.
    assert roster.summary()["max"] == MAX_DECKS


def test_덱마다_여섯_칸이다():
    fill_to_max()
    for deck in roster.load()["decks"]:
        roster.check_size(deck)     # 어긋나면 ValueError
