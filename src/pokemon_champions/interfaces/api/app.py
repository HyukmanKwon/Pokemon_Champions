"""로컬 웹으로 내 포켓몬 팀을 보고 필드 단위로 바로 고치는 FastAPI 앱.

라우트만 있다. 세 가지를 각자 다른 곳에 두고 여기서는 잇기만 한다.

    무엇을 계산할까   usecases/   (battle · team · roster · naming)
    어떤 칸에 담을까   views.py
    무슨 상태코드일까  여기

CLI(interfaces/cli.py)와 완전히 같은 usecases 를 쓴다 — 검증과 부분수정을
여기서 다시 만들지 않는다. 이 파일에 계산이나 SQL 이 생기면 CLI 와 웹의
동작이 갈라진다.

라우트 본문이 dict 리터럴로 길어지면 views.py 로 옮긴다. 예전에 이 파일이
833줄이었는데 그중 대부분이 그것이었다.
"""

import json
import queue
import threading
from pathlib import Path
from typing import Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import (FileResponse, HTMLResponse, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ... import assets
from ...config import IMAGES_DIR
from ...agent import runner
from ...agent import tools as agent_tools
from ...db import connect, connection
from ...db.repositories import (ability_repo, item_repo, mega_repo,
                                move_repo, nature_repo, pokemon_repo,
                                rules_repo)
from ...usecases import team
from ...calc.damage import Rules
from ...text import normalize
from ...usecases import battle, naming, roster, usage
from . import views

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _fmt(name):
    """싱글/더블. 모르는 값이면 Singles 로 떨어뜨린다."""
    return name if name in ("Singles", "Doubles") else "Singles"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()

# specs 를 캐시하지 않는다. 덱이 여러 벌이 되면서 "지금 보고 있는 덱" 이
# 요청마다 달라질 수 있고, 캐시해두면 덱을 바꿔도 옛 덱이 그려진다.
state = {"conn": None, "rules": None}


@app.on_event("startup")
def on_startup():
    state["conn"] = connect()
    # 참조표는 배틀 중에 안 바뀐다. 계산 한 번마다 324행을 다시 읽으면
    # 확정 N타 분석에서 턴 수만큼 쿼리가 나간다. 뜰 때 한 번만 읽는다.
    state["rules"] = Rules(
        chart=rules_repo.fetch_type_chart(state["conn"]))


@app.on_event("shutdown")
def on_shutdown():
    if state["conn"] is not None:
        state["conn"].close()


class SlotEdit(BaseModel):
    ko_name: Optional[str] = None
    sp_values: Optional[List[int]] = None
    ko_nature: Optional[str] = None
    ability: Optional[str] = None
    item: Optional[str] = None
    moves: Optional[List[str]] = None


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


# 화면을 이루는 css/js. 스프라이트와 달리 이쪽은 StaticFiles 로 건다 —
# 없는 파일이 404 인 게 맞고(오타를 바로 알아야 한다), 받아올 곳도 없다.
#
# ── ETag 만으로는 안 됐다 ──
#   StaticFiles 는 ETag 와 Last-Modified 를 붙이지만 Cache-Control 은 안
#   붙인다. 그러면 브라우저가 물어보지도 않는다 — 캐시 지시가 없을 때
#   쓰는 어림값이 "Last-Modified 로부터 흐른 시간의 10%" 라, 며칠 전에
#   고친 파일은 몇 시간씩 그대로 쓰인다. ETag 는 다시 물어볼 때만 쓰이는
#   것이라 아예 차례가 오지 않는다.
#
#   실제로 css 를 고치고 새로고침해도 옛 화면이 그대로 떴다. 파일도
#   서버도 새것인데 화면만 낡아서, 고친 쪽을 의심하게 되는 종류의 함정이다.
#
#   no-cache 는 "받지 마라" 가 아니라 "쓰기 전에 물어봐라" 다. 그래서
#   그때부터 ETag 가 제 일을 하고, 안 바뀌었으면 304 로 끝난다.
class DevStatic(StaticFiles):
    def file_response(self, *args, **kwargs):
        res = super().file_response(*args, **kwargs)
        res.headers["Cache-Control"] = "no-cache"
        return res


app.mount("/static", DevStatic(directory=STATIC_DIR), name="static")


# ─────────────────────────────────────────────────────────────
# 이미지
#
# StaticFiles 로 통째로 걸지 않는다. 아직 안 받은 그림은 404 가 되어,
# 파일이 없는 것과 저장소에 없는 것이 화면에서 똑같아 보이기 때문이다.
# 여기서 받아 저장하고 내주면 첫 요청 때 캐시가 저절로 채워진다.
#
# 그림이 정말 없는 폼(리전폼·메가에 흔하다)은 404 를 준다. 화면은 그
# 자리를 비워두면 되고, 능력치 조회는 애초에 이 경로를 타지 않는다.
#
# 브라우저가 매번 다시 받지 않도록 캐시 헤더를 길게 준다. 스프라이트는
# 한 번 정해지면 안 바뀌는 그림이라 안전하다.
# ─────────────────────────────────────────────────────────────

CACHE_HEADERS = {"Cache-Control": "public, max-age=604800"}


def _sprite(path):
    if path is None:
        raise HTTPException(404, "이미지가 없습니다.")
    return FileResponse(path, media_type="image/png", headers=CACHE_HEADERS)


@app.get("/sprite/type/{type_name}")
def sprite_type(type_name: str):
    """한국어 타입 배지. 아직 안 그렸으면 404 — 화면이 글자로 대신 쓴다.

        python -m scripts.make_type_icons
    """
    return _sprite(assets.type_icon(type_name))


@app.get("/sprite/pokemon/{pokemon_id}")
def sprite_pokemon(pokemon_id: int):
    """상세용 큰 그림(official-artwork)."""
    return _sprite(assets.ensure_pokemon_sprite(pokemon_id))


@app.get("/sprite/pokemon/{pokemon_id}/icon")
def sprite_pokemon_icon(pokemon_id: int):
    """목록용 96px 도트. 큰 그림을 313개 깔면 화면이 안 뜬다."""
    return _sprite(assets.ensure_pokemon_icon(pokemon_id))


@app.get("/sprite/item/{item_name}")
def sprite_item(item_name: str):
    """도구 아이콘. 저장소 파일명이 영문 슬러그라 items.name 으로 찾는다."""
    return _sprite(assets.ensure_item_sprite(item_name))


# ─────────────────────────────────────────────────────────────
# 도감 — DB 에 있는 것을 그대로 열람한다
#
# 팀 화면(/api/team)과 성격이 다르다. 저쪽은 내 엔트리 6칸을 계산해서
# 보여주고 고치는 곳이고, 이쪽은 DB 내용을 있는 그대로 읽기만 한다.
# 그래서 services 를 거치지 않고 repositories 를 바로 부른다 — 중간에
# 낄 규칙이 없는데 계층만 늘리면 무엇이 어디 있는지 흐려진다.
#
# 목록은 전부 한 번에 보낸다. 가장 큰 moves 가 498줄이라, 검색·정렬은
# 브라우저가 메모리에서 하는 편이 왕복보다 빠르다.
#
# 네 종류가 하는 일이 같다 — 목록은 "repo 에서 받아 그림 주소를 붙여 보낸다",
# 상세는 "repo 에서 받아(없으면 404) 그림 주소를 붙여 보낸다". 그래서 라우트를
# 여덟 개 적지 않고, 무엇을 어느 repo 에서 받아 어떻게 장식할지만 DEX 에
# 적는다. 화면 쪽 dex.js 의 DEX 상수가 네 탭을 한 렌더러로 접는 것과 같은
# 모양이라, 한쪽을 읽으면 다른 쪽도 읽힌다.
# ─────────────────────────────────────────────────────────────

# {URL 의 종류: (조회 모듈, 목록 행 장식, 상세 장식)}
# 목록 장식이 None 이면 repo 가 준 것을 그대로 보낸다 — 특성에는 그림이 없다.
DEX = {
    "pokemons":  (pokemon_repo, views.decorate_pokemon, views.detail_pokemon),
    "moves":     (move_repo,    views.decorate_move,    views.detail_move),
    "abilities": (ability_repo, None,                   views.detail_ability),
    "items":     (item_repo,    views.decorate_item,    views.detail_item),
}


def _dex(kind):
    spec = DEX.get(kind)
    if spec is None:
        raise HTTPException(
            404, f"그런 도감이 없습니다: {kind} "
                 f"(있는 것: {', '.join(DEX)})")
    return spec


def _found(fetch, *args):
    """repositories 의 ValueError('존재하지 않는 …') 를 404 로 바꾼다."""
    try:
        return fetch(*args)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/dex/{kind}")
def dex_list(kind: str):
    repo, decorate, _ = _dex(kind)
    rows = repo.fetch_list(state["conn"])
    return [decorate(r) for r in rows] if decorate else rows


@app.get("/api/dex/{kind}/{name}")
def dex_detail(kind: str, name: str):
    repo, _, decorate = _dex(kind)
    return decorate(_found(repo.fetch_detail, state["conn"], name))


# ─────────────────────────────────────────────────────────────
# 도우미 — 로컬 LLM 에게 묻고, 무엇을 부르는지 실시간으로 보여준다
#
# ── 왜 SSE 인가 ──
#   한 질문에 2분이 걸린다. 다 끝난 뒤에 한 번에 주면 그동안 화면이 죽어
#   있고, 사용자는 멈춘 건지 도는 건지 알 수 없다. runner 가 이미
#   on_tool 콜백으로 "지금 무엇을 부르는지" 를 알려주므로, 그걸 그대로
#   이벤트로 흘린다.
#
#   WebSocket 이 아닌 이유는 방향이 한쪽뿐이어서다. 질문은 POST 한 번이고
#   그 뒤로는 서버가 말하기만 한다.
#
# ── 왜 커넥션을 따로 여나 ──
#   state["conn"] 을 쓰면 이 요청이 2분 동안 그걸 붙잡는다. 그 사이 다른
#   탭이 도감을 열면 같은 psycopg2 커넥션을 두 스레드가 나눠 쓰게 되고,
#   그건 안전하지 않다. 대화 하나가 자기 커넥션을 열고 끝나면 닫는다.
# ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    # 지금 화면이 보고 있는 덱. 모델이 고르는 값이 아니라 화면이 묶는 값이다.
    deck: Optional[str] = None
    model: Optional[str] = None
    # 이어 묻기. 앞 턴이 돌려준 것을 그대로 되돌려준다.
    history: Optional[List[Dict]] = None


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.post("/api/chat")
def chat(req: ChatRequest):
    """질문 하나를 받아 도구 호출과 답을 이벤트로 흘린다.

    이벤트는 셋이다.
      tool    {name, args, result}   도구를 부를 때마다
      answer  {text, history}        다 끝났을 때
      error   {message}              Ollama 가 없거나 죽었을 때
    """
    # ── 왜 스레드인가 ──
    #   runner.ask 는 블로킹이다. on_tool 은 그 안에서 불리므로, 같은
    #   흐름에서 받으면 ask 가 끝난 뒤에야 이벤트를 내보내게 된다 — 그러면
    #   2분을 기다렸다가 한꺼번에 쏟는 셈이라 스트리밍한 값이 없다.
    #   ask 를 스레드에 넣고 큐로 받아야 부르는 즉시 흘러나간다.
    def stream():
        box = queue.Queue()

        def work():
            try:
                with connection() as conn:
                    sess = agent_tools.session(conn, deck_id=req.deck)
                    answer, history = runner.ask(
                        req.question, sess,
                        model=req.model or runner.DEFAULT_MODEL,
                        history=req.history,
                        on_tool=lambda name, args, result: box.put(
                            ("tool", {"name": name, "args": args,
                                      "result": result})))
                    box.put(("answer", {"text": answer, "history": history}))
            except requests.ConnectionError:
                box.put(("error", {"message":
                                   "Ollama 에 연결하지 못했습니다. "
                                   "`ollama serve` 가 떠 있나요?"}))
            except requests.HTTPError as e:
                box.put(("error", {"message": f"Ollama 오류: {e}"}))
            except Exception as e:      # noqa: BLE001 - 화면이 멎으면 안 된다
                box.put(("error", {"message": f"{type(e).__name__}: {e}"}))
            finally:
                box.put(None)

        threading.Thread(target=work, daemon=True).start()

        while True:
            item = box.get()
            if item is None:
                return
            yield _sse(*item)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ─────────────────────────────────────────────────────────────
# 덱 — 여러 벌 중 하나가 "지금 보고 있는" 덱이다
#
# 6칸을 읽고 고치는 것은 아래 /api/team 이 그대로 한다. 여기는 덱 자체를
# 만들고 지우고 갈아타는 것만 다룬다.
# ─────────────────────────────────────────────────────────────

class DeckEdit(BaseModel):
    name: str


@app.get("/api/decks")
def list_decks():
    return roster.summary()


@app.post("/api/decks")
def create_deck(edit: DeckEdit):
    """새 덱. 상한(config.MAX_DECKS)을 넘으면 400.

    _deck_op 을 못 쓴다 — 그건 deck_id 를 첫 인자로 받는 것들의 자리다.
    """
    try:
        return roster.create(edit.name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/decks/{deck_id}/copy")
def copy_deck(deck_id: str):
    return _deck_op(roster.copy_deck, deck_id)


@app.patch("/api/decks/{deck_id}")
def rename_deck(deck_id: str, edit: DeckEdit):
    return _deck_op(roster.rename, deck_id, edit.name)


@app.delete("/api/decks/{deck_id}")
def delete_deck(deck_id: str):
    return {"active": _deck_op(roster.delete, deck_id)}


@app.post("/api/decks/{deck_id}/activate")
def activate_deck(deck_id: str):
    return {"active": _deck_op(roster.set_active, deck_id)}


def _deck_op(fn, deck_id, *args):
    """없는 덱은 404, 규칙 위반(마지막 덱 삭제)은 400."""
    try:
        return fn(deck_id, *args)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/team")
def get_team(deck: Optional[str] = None):
    """지금 보고 있는 덱의 6칸. deck 을 주면 그 덱."""
    try:
        slots = roster.slots(deck)
    except LookupError as e:
        raise HTTPException(404, str(e))
    conn = state["conn"]
    return [views.slot(i, spec, team.slot_data(conn, spec))
            for i, spec in enumerate(slots)]


@app.get("/api/pokemon/{ko_name}/options")
def get_pokemon_options(ko_name: str):
    """아직 등록하지 않은 포켓몬의 특성·기술 목록.

    검증은 스펙 전체를 보므로, 이름만 바꾸면 특성과 기술이 새 포켓몬 것이
    아니라서 반드시 거부된다. 화면은 이 목록을 먼저 받아 특성을 채우고
    기술을 비운 뒤 한 번의 PATCH 로 보낸다. 초기화는 화면 사정이므로
    services 에 두지 않고 여기서 한다.
    """
    conn = state["conn"]
    try:
        meta = pokemon_repo.fetch_meta(conn, ko_name)   # 없는 이름이면 여기서 걸린다
    except ValueError as e:
        raise HTTPException(404, str(e))

    # 메가폼이면 지닐 도구가 정해져 있다. 메가스톤이 없으면 그 폼 자체가
    # 성립하지 않으므로, 고를 여지가 없는 것을 고르게 두지 않는다.
    # (계산기 전용이다 — 엔트리에는 메가폼을 올릴 수 없다)
    forced_item = (mega_repo.fetch_required_item(conn, ko_name)
                   if meta["is_mega"] else None)

    return {
        "selectable_abilities": pokemon_repo.fetch_abilities(conn, ko_name),
        "learnable_moves": move_repo.fetch_learnable(conn, ko_name),
        "is_mega": meta["is_mega"],
        "forced_item": forced_item,
    }


@app.get("/api/pokemons")
def get_pokemons():
    """엔트리에 올릴 수 있는 포켓몬 이름. 메가폼은 빠져 있다."""
    return pokemon_repo.fetch_selectable(state["conn"])


@app.get("/api/items")
def get_items():
    """지닐 수 있는 도구 전역 목록.

    도구는 포켓몬마다 다르지 않으므로 슬롯마다 실어 보내지 않는다. 한 번
    받아서 여섯 카드가 같이 쓴다. 포켓몬을 가리는 것은 메가스톤뿐이고,
    그건 슬롯의 mega_stones 에 따로 들어 있다.
    """
    return item_repo.fetch_selectable(state["conn"])


@app.get("/api/types")
def get_types():
    """18타입의 한국어 표기와 아이콘 주소.

    화면이 이 표를 코드에 적어두고 있었다. DB 의 pokemon_type_names 와
    같은 내용이 두 벌이 되는데, 표기를 다듬으면 한쪽만 고치게 된다.
    LLM 쪽도 같은 표를 읽는다(usecases/naming.type_names).
    """
    return views.types(naming.type_names(state["conn"]))


# ─────────────────────────────────────────────────────────────
# 채용률
#
# 사이트가 아니라 우리 DB 에서 읽는다. 목록에서 한 마리씩 누를 때마다 남의
# 서버를 두드릴 수 없고, 순위와 추세는 DB 에만 있다.
# (LLM 도구의 usage_stats 는 반대로 사이트에 물어 오늘 값을 받는다)
# ─────────────────────────────────────────────────────────────

@app.get("/api/usage")
def usage_ranking(format: str = "Singles", days: int = 7):
    """메타 순위 전체. days 일 전 대비 변화를 같이 준다."""
    return views.usage_ranking(
        usage.ranking_from_db(state["conn"], fmt=_fmt(format), days=days))


@app.get("/api/usage/{ko_name}")
def usage_detail(ko_name: str, format: str = "Singles", top: int = 10):
    """한 마리의 채용 내역 — 기술·도구·특성·성격·SP·팀원을 순위대로."""
    conn = state["conn"]
    en = naming.resolve(conn, "pokemons", ko_name)
    if en is None:
        raise HTTPException(404, f"'{ko_name}' 은(는) 포켓몬 목록에 없습니다.")

    got = views.usage_detail(usage.detail_from_db(
        conn, en, ko_name=naming.ko(conn, "pokemons", en),
        fmt=_fmt(format), top=top))
    # 아직 안 받은 포켓몬은 404 다. 빈 목록을 주면 화면이 "채용률 0%" 로
    # 그리는데, 그건 안 쓰인다는 뜻이 아니라 우리가 안 받았다는 뜻이다.
    if "error" in got:
        raise HTTPException(404, got["error"])
    return got


@app.get("/api/natures")
def get_natures():
    """성격 21종. 이것도 포켓몬을 가리지 않으므로 전역으로 한 번만 준다.

    이름만 주면 화면에서 무엇이 오르고 내리는지 알 수 없으니 능력치 이름을
    같이 붙인다. 성실은 둘 다 None 이다.
    """
    return views.natures(nature_repo.fetch_all(state["conn"]))


@app.patch("/api/team/{index}")
def patch_team(index: int, edit: SlotEdit, deck: Optional[str] = None):
    try:
        slots = roster.slots(deck)
    except LookupError as e:
        raise HTTPException(404, str(e))
    if not 0 <= index < len(slots):
        raise HTTPException(404, f"슬롯 {index}는 존재하지 않습니다.")

    fields = edit.dict(exclude_unset=True)
    merged = {**slots[index], **fields}
    try:
        # slot_data 는 repositories 를 직접 부르므로 build_pokemon 을 거치지
        # 않는다. 여기서 부르지 않으면 CLI 만 검증되고 웹은 무엇이든 통과한다.
        team.validate_spec(state["conn"], merged)
    except ValueError as e:
        # 파일에 쓰기 전에 막는다. 예전에는 고쳤다가 되돌렸는데, 덱이 여러
        # 벌이 되면서 되돌릴 대상이 캐시가 아니라 파일이 됐다.
        raise HTTPException(400, str(e))

    saved = roster.edit_slot(index, deck, **fields)
    return views.slot(index, saved,
                      team.slot_data(state["conn"], saved))


# ─────────────────────────────────────────────────────────────
# 데미지 계산기
#
# calc/damage.py 는 DB 를 안 본다. 여기서 조회해서 숫자만 넘긴다.
# 그 경계 덕에 CLI(scripts/check_damage.py)와 이 라우트가 같은 함수를
# 쓰고, 값이 갈라지지 않는다.
# ─────────────────────────────────────────────────────────────

# 무보정 성격·SP 기본값·메가 허용은 usecases/battle.py 가 한 벌로 들고 있다.
# 여기서 다시 적으면 도구 쪽과 갈린다 — 실제로 갈렸던 자리다.


class CalcSide(BaseModel):
    """계산에 올릴 한쪽. ko_name 만 필수다.

    안 보낸 칸은 조립 층이 채용률에서 채운다 — 그날 가장 많이 쓰인 특성·
    도구·성격·SP 다. 무엇으로 쟀는지는 응답의 side.usage 에 실려 나간다.
    채용률 자료가 없는 폼이면 예전대로 무보정(성실 · SP 0 · 1번 특성)이다.

    use_usage=false 를 주면 채우지 않는다. 순수한 종족값 비교용이다.
    """

    ko_name: str
    ability: Optional[str] = None
    item: Optional[str] = None
    ko_nature: Optional[str] = None
    sp_values: Optional[List[int]] = None
    use_usage: bool = True
    # {"a": 2, "s": -1} — 안 적힌 능력치는 0
    rank: Dict[str, int] = Field(default_factory=dict)
    condition: Optional[str] = None
    # 남은 HP. None 이면 만피. 멀티스케일·궁지 특성이 이걸 본다
    hp: Optional[int] = None
    grounded: bool = True


class CalcRequest(BaseModel):
    attacker: CalcSide
    defender: CalcSide
    move: str                    # 한국어 기술 이름
    weather: Optional[str] = None
    terrain: Optional[str] = None
    is_critical: bool = False
    reflect: bool = False
    light_screen: bool = False
    is_doubles: bool = False
    # 방어자의 맹독이 몇 턴째인가. 맹독은 n/16 으로 세지므로 이제 막
    # 걸었는지 세 턴 버텼는지가 확정타를 가른다.
    toxic_turn: int = 1
    max_turns: int = 4


def _spec(side: CalcSide):
    """CalcSide 를 조립 층이 받는 느슨한 스펙으로.

    칸 이름이 다른 것은 화면이 한국어를 그대로 보내기 때문이다(ko_name,
    ko_nature, sp_values). 요청 모양은 그대로 두고 여기서만 옮긴다 —
    화면 코드를 건드리지 않으려는 것이다.
    """
    return {"name": side.ko_name, "ability": side.ability, "item": side.item,
            "nature": side.ko_nature, "sp": side.sp_values, "rank": side.rank,
            "condition": side.condition, "hp": side.hp,
            "grounded": side.grounded, "use_usage": side.use_usage}


@app.get("/api/calc/rules")
def calc_rules():
    """날씨·필드·상태이상 선택지. 화면의 드롭다운을 이걸로 채운다.

    코드에 목록을 적어두면 DB 에 새 날씨가 생겼을 때 조용히 빠진다.
    """
    # 상태이상도 rules 에 들어 있다. 여기서 다시 SELECT 하면 뜰 때 한 번
    # 읽어둔 뜻이 없다.
    return views.calc_rules(state["rules"])


class IndexRequest(BaseModel):
    """결정력·내구력용. 상대도 판도 없이 한쪽만 본다."""

    side: CalcSide
    moves: List[str] = Field(default_factory=list)


@app.post("/api/calc/power")
def calc_power(req: IndexRequest):
    """결정력 — 공격 실능 × 위력 × 자속. 기술별로 준다.

    상성·랭크·날씨는 상대와 판이 있어야 정해지므로 빠진다. 절대값에는
    의미가 없고 기술끼리·포켓몬끼리 비교하는 데만 쓴다.
    """
    try:
        got = battle.power(state["conn"], _spec(req.side), req.moves)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 웹은 없는 기술을 404 로 막는다. 계산기 화면의 기술 칸은 콤보라 오타가
    # 잘 안 나고, 한 줄만 조용히 빠지면 왜 안 보이는지 알 수 없다.
    for s in got.moves:
        if s.row is None:
            raise HTTPException(404, f"없는 기술입니다: {s.asked}")

    return views.power(got, req.side)


@app.post("/api/calc/bulk")
def calc_bulk(req: IndexRequest):
    """내구력 — HP × 방어 / 0.411, HP × 특수방어 / 0.411.

    HP 만 봐도 방어만 봐도 몇 방 버티는지가 안 나온다. 나눈 상수까지 같이
    주는 이유는 화면이 계산식을 그대로 적어 보여주기 때문이다.
    """
    try:
        got = battle.bulk(state["conn"], _spec(req.side))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return views.bulk(got, req.side)


@app.post("/api/calc/damage")
def calc_damage(req: CalcRequest):
    # 없는 기술은 404, 세울 수 없는 포켓몬은 400. 조립 층은 둘 다
    # ValueError 로 올리므로 기술만 먼저 확인해 갈래를 나눈다.
    if battle.move_row(state["conn"], req.move) is None:
        raise HTTPException(404, f"없는 기술입니다: {req.move}")

    try:
        shot = battle.one_hit(
            state["conn"], state["rules"],
            _spec(req.attacker), _spec(req.defender), req.move,
            max_turns=req.max_turns,
            weather=req.weather, terrain=req.terrain,
            is_critical=req.is_critical, reflect=req.reflect,
            light_screen=req.light_screen, is_doubles=req.is_doubles,
            toxic_turn=req.toxic_turn,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return views.damage(shot, req.attacker, req.defender)
