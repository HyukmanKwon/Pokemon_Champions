"""웹 라우트가 내놓는 모양을 박아둔다.

test_tools.py 와 같은 이유, 같은 방법이다. 다른 점은 대상이다 — 여기는
브라우저가 받는 JSON 이고, 저기는 모델이 받는 JSON 이다.

── 왜 둘 다 필요한가 ──
  지금 데미지 계산은 app.py 와 tools.py 가 각자 조립한다. 둘을 조립 층
  하나로 합칠 때 알고 싶은 것은 "합쳐도 양쪽 답이 그대로인가" 다. 한쪽만
  박아두면 나머지 한쪽이 조용히 바뀐다.

  실제로 지금도 갈려 있다. 웹 계산기는 리플렉터·빛의장막·상태이상·남은
  HP·접지를 받는데 도구는 못 받는다. 합칠 때 이 차이를 어느 쪽으로
  맞출지가 결정 사항이고, 그때 이 파일이 기준이 된다.

── 다시 적기 ──
      UPDATE_GOLDEN=1 pytest tests/test_api.py
"""

import json
import os
from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "golden" / "api.json"

# 무보정 한 쪽. ko_name 과 ability 만 필수다.
def side(ko_name, ability, **kw):
    return {"ko_name": ko_name, "ability": ability, **kw}


# (이름, method, 경로, 본문). 본문이 None 이면 GET.
CALLS = [
    ("dex_pokemon", "GET", "/api/dex/pokemons/garchomp", None),
    ("dex_move", "GET", "/api/dex/moves/earthquake", None),
    ("dex_ability", "GET", "/api/dex/abilities/rough-skin", None),
    ("dex_item", "GET", "/api/dex/items/focus-sash", None),
    ("dex_없는것", "GET", "/api/dex/pokemons/없는포켓몬", None),

    ("team", "GET", "/api/team", None),
    ("natures", "GET", "/api/natures", None),
    ("calc_rules", "GET", "/api/calc/rules", None),
    ("options", "GET", "/api/pokemon/한카리아스/options", None),

    ("calc_damage_기본", "POST", "/api/calc/damage", {
        "attacker": side("맘모꾸리", "둔감"),
        "defender": side("한카리아스", "모래숨기"),
        "move": "고드름떨구기"}),

    # 도구 쪽에는 없는 칸들 — 조립 층으로 합칠 때 이 답이 유지돼야 한다
    ("calc_damage_전부", "POST", "/api/calc/damage", {
        "attacker": side("메가갸라도스", "틀깨기", ko_nature="고집",
                         sp_values=[0, 32, 0, 0, 0, 32], rank={"a": 2}),
        "defender": side("한카리아스", "모래숨기", condition="화상",
                         hp=100, grounded=True),
        "move": "지진", "weather": "sandstorm", "reflect": True,
        "is_critical": False, "is_doubles": False}),

    ("calc_damage_없는기술", "POST", "/api/calc/damage", {
        "attacker": side("맘모꾸리", "둔감"),
        "defender": side("한카리아스", "모래숨기"),
        "move": "없는기술"}),

    # 그 포켓몬의 특성이 아니면 400 과 함께 가능한 목록을 준다.
    # 조립 층으로 옮길 때 이 문구가 사라지기 쉬운 자리다.
    ("calc_damage_틀린특성", "POST", "/api/calc/damage", {
        "attacker": side("맘모꾸리", "옹골참"),
        "defender": side("한카리아스", "모래숨기"),
        "move": "고드름떨구기"}),

    ("calc_power", "POST", "/api/calc/power", {
        "side": side("메타그로스", "클리어바디", ko_nature="고집"),
        "moves": ["지진", "아이언헤드"]}),

    ("calc_bulk", "POST", "/api/calc/bulk", {
        "side": side("하마돈", "모래날림")}),
]


@pytest.fixture
def client(db, fixed_team):
    """startup 이 도는 TestClient. db 가 없으면 skip 된다.

    fixed_team 을 먼저 받는 이유는 startup 이 team.load_specs() 를
    부르기 때문이다. 순서가 뒤집히면 진짜 엔트리를 읽는다.
    """
    from fastapi.testclient import TestClient

    from pokemon_champions.interfaces.api import app as api

    with TestClient(api.app) as c:
        yield c


@pytest.fixture
def responses(client):
    out = {}
    for name, method, path, body in CALLS:
        r = client.get(path) if body is None else client.post(path, json=body)
        out[name] = {"status": r.status_code, "body": r.json()}
    return out


def test_golden(responses):
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(
            json.dumps(responses, ensure_ascii=False, indent=2,
                       sort_keys=True, default=str) + "\n",
            encoding="utf-8")
        pytest.skip("golden 을 다시 적었습니다. git diff 로 확인하세요")

    assert GOLDEN.exists(), (
        f"{GOLDEN} 가 없습니다. UPDATE_GOLDEN=1 pytest 로 먼저 만드세요")

    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    have = json.loads(json.dumps(responses, ensure_ascii=False, default=str))

    assert set(have) == set(want), "부른 경로 목록이 달라졌습니다"
    for key in want:
        assert have[key] == want[key], f"{key} 의 응답이 달라졌습니다"


def test_엔트리_수정은_사본에만_쓴다(client, fixed_team):
    """PATCH 가 진짜 data/my_team.json 을 건드리지 않는지."""
    before = fixed_team.read_text(encoding="utf-8")
    r = client.patch("/api/team/0", json={"ko_nature": "고집"})
    assert r.status_code == 200

    from pokemon_champions.config import TEAM_PATH
    assert fixed_team != TEAM_PATH
    assert fixed_team.read_text(encoding="utf-8") != before
