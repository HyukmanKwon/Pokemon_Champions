"""웹 라우트가 내놓는 모양을 박아둔다.

test_tools.py 와 같은 이유, 같은 방법이다. 다른 점은 대상이다 — 여기는
브라우저가 받는 JSON 이고, 저기는 모델이 받는 JSON 이다.

── 왜 둘 다 필요한가 ──
  데미지 계산은 이제 usecases/battle.py 한 곳에서 조립한다. 그래서 한쪽을
  고치면 다른 쪽도 같이 움직인다 — 둘 다 박아둬야 그 움직임이 보인다.

  웹만 받는 칸(리플렉터·빛의장막·상태이상·남은 HP·접지)이 아직 있다.
  도구에도 열어줄지는 따로 정할 일이고, 그때 이 파일이 기준이 된다.

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
    #
    # condition 은 영문 슬러그다. 화면이 keyOf("conditions", ...) 로 바꿔
    # 보내고, 계산도 status_conditions.name 으로 찾는다. 여기 "화상" 이라고
    # 적어 뒀던 동안에는 이 케이스에 화상이 아예 안 걸려 있었다.
    ("calc_damage_전부", "POST", "/api/calc/damage", {
        "attacker": side("메가갸라도스", "틀깨기", ko_nature="고집",
                         sp_values=[0, 32, 0, 0, 0, 32], rank={"a": 2}),
        "defender": side("한카리아스", "모래숨기", condition="burn",
                         hp=100, grounded=True),
        "move": "지진", "weather": "sandstorm", "reflect": True,
        "is_critical": False, "is_doubles": False}),

    # 맹독은 턴마다 n/16 으로 세진다. "데미지 × N" 으로는 안 나오는 판정이
    # 여기서 나와야 한다. 먹다남은음식으로 회복 쪽도 같이 건다.
    ("calc_damage_맹독", "POST", "/api/calc/damage", {
        "attacker": side("맘모꾸리", "둔감"),
        "defender": side("한카리아스", "까칠한피부", item="먹다남은음식",
                         condition="toxic"),
        "move": "고드름떨구기", "toxic_turn": 2, "max_turns": 6}),

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

    fixed_team 이 덱 파일을 임시 폴더로 돌려놓는다. 이게 없으면 테스트가
    사용자의 진짜 덱을 읽고, 더 나쁘게는 고친다.
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


def test_덱_한살이(client):
    """만들고 → 갈아타고 → 이름 바꾸고 → 지운다.

    골든으로 안 박는 이유는 덱 id 가 매번 새로 뽑히기 때문이다. 모양이
    아니라 규칙을 본다.
    """
    first = client.get("/api/decks").json()
    assert len(first["decks"]) == 1
    assert first["decks"][0]["name"] == "테스트 덱"
    assert len(first["decks"][0]["members"]) == 6

    made = client.post("/api/decks", json={"name": "트릭룸"}).json()
    assert made["name"] == "트릭룸"
    # 만들기만 해서는 보고 있는 덱이 안 바뀐다. 편집 중에 화면이 튀면 안 된다.
    assert client.get("/api/decks").json()["active"] == first["active"]

    assert client.post(f"/api/decks/{made['id']}/activate").json()["active"] \
        == made["id"]

    renamed = client.patch(f"/api/decks/{made['id']}",
                           json={"name": "트릭룸 v2"}).json()
    assert renamed["name"] == "트릭룸 v2"

    # 지우면 활성 덱이 남은 것으로 옮겨간다
    left = client.delete(f"/api/decks/{made['id']}").json()["active"]
    assert left == first["active"]
    assert len(client.get("/api/decks").json()["decks"]) == 1


def test_마지막_덱은_못_지운다(client):
    """다 지우면 활성 덱이 없어진다. 그 상태를 다루는 코드를 곳곳에
    두느니 애초에 못 만들게 한다."""
    only = client.get("/api/decks").json()["active"]
    r = client.delete(f"/api/decks/{only}")
    assert r.status_code == 400
    assert "마지막" in r.json()["detail"]


def test_없는_덱은_404(client):
    assert client.delete("/api/decks/없는id").status_code == 404
    assert client.get("/api/team", params={"deck": "없는id"}).status_code == 404


def test_덱마다_따로_고쳐진다(client):
    """한 덱을 고쳐도 다른 덱은 그대로여야 한다. 덱을 나눈 이유 자체다."""
    a = client.get("/api/decks").json()["active"]
    b = client.post("/api/decks/%s/copy" % a).json()["id"]

    before = client.get("/api/team", params={"deck": b}).json()[0]["nature"]["name"]
    client.patch("/api/team/0", params={"deck": a}, json={"ko_nature": "고집"})

    assert client.get("/api/team", params={"deck": a}).json()[0]["nature"]["name"] \
        == "고집"
    assert client.get("/api/team", params={"deck": b}).json()[0]["nature"]["name"] \
        == before


def test_덱_수정은_사본에만_쓴다(client, fixed_team):
    """PATCH 가 진짜 data/decks.json 을 건드리지 않는지.

    덱은 다시 만들 수 없는 파일이다. 픽스처가 새는지를 테스트가 직접
    확인해두지 않으면, 언젠가 한 번 새고 그때는 이미 늦다.
    """
    before = fixed_team.read_text(encoding="utf-8")
    r = client.patch("/api/team/0", json={"ko_nature": "고집"})
    assert r.status_code == 200

    from pokemon_champions.config import DECKS_PATH
    assert fixed_team != DECKS_PATH
    assert fixed_team.read_text(encoding="utf-8") != before
