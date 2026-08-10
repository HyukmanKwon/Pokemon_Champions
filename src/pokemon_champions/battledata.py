"""배틀 데이터 — championsbattledata.com 에서 받아 data/cache/usage/ 에 캐시한다.

── 왜 이 이름인가 ──
  "배틀 데이터" 는 게임 안 메뉴 이름이자 저 사이트 이름이다. 파일 이름이
  값이 어디서 왔는지를 스스로 밝히게 둔다.

── 왜 이 층에 있나 ──
  assets.py 와 같은 자리다. 프로젝트 바깥에서 받아 캐시하는 일이고 DB 를
  보지 않는다. 한국어로 바꾸고 DB 와 맞추는 것은 services/usage.py 가 한다.
  여기서 DB 를 부르면 "네트워크가 안 될 때" 와 "DB 에 없을 때" 가 한 함수
  안에서 섞인다.

── 왜 이 사이트인가 ──
  포켓몬컴퍼니는 API 를 내지 않는다. 채용률의 원천은 게임 안 "배틀 데이터"
  화면이고 공개된 기계 판독 경로가 없다. 이 사이트가 그 화면을 매일 옮겨
  적어 JSON 으로 내놓는다. 즉 여기 값은 공식 데이터의 사본이지 원본이
  아니다. 틀릴 수 있고 사이트가 멈추면 같이 멈춘다. 그래서 실패해도 묵은
  캐시를 돌려주고, 예외 대신 None 을 준다.

── 이름 맞추기 ──
  이름 규칙이 우리와 다르다. 우리는 PokeAPI 슬러그(raichu-alola), 저쪽은
  사람이 읽는 표기(Alolan Raichu) 다. 꼬리와 머리가 서로 뒤집혀 있어서
  문자열을 잘라 붙이는 방식으로는 안 맞는다.

  그래서 표를 손으로 적지 않고 색인(/api)에서 맞춘다. 이름을 토큰으로
  쪼개 집합으로 비교하면 순서가 달라도 걸린다.
      raichu-alola   -> {raichu, alola}
      Alolan Raichu  -> {alola,  raichu}   ← alolan 을 alola 로 줄여서

── 메가폼은 원종에 합쳐져 있다 ──
  색인에서 Mega Gyarados 의 battleName 이 Gyarados 다. 메가는 배틀 중
  상태라 엔트리 통계는 원종으로 잡히고, 메가스톤을 들었는지는 held_item
  칸에 나온다(Garchompite 1.7% 처럼). 그래서 메가폼을 물으면 원종 데이터를
  돌려주고, 그렇다는 사실을 함께 알린다.

── 하루 한 번 ──
  게임 쪽이 하루 단위로 갱신된다. 그보다 자주 받을 이유가 없고 남의
  서버라 아껴 쓰는 편이 맞다.
"""

import json
import re
import time

import requests

from .config import CACHE_DIR

BASE = "https://championsbattledata.com"
USAGE_DIR = CACHE_DIR / "usage"
TTL_SECONDS = 12 * 60 * 60
FORMATS = ("Singles", "Doubles")

# 같은 것을 가리키는 다른 표기. 토큰을 이 표로 한 번 통과시킨 뒤 비교한다.
SYNONYM = {
    "alolan": "alola", "galarian": "galar", "hisuian": "hisui",
    "paldean": "paldea", "breed": "", "form": "", "the": "",
}

# 메가 꼬리. 우리 이름에서 이걸 떼면 원종이 된다.
MEGA_RE = re.compile(r"-mega(-[xy])?$")


def tokens(name):
    """이름을 비교용 토큰 집합으로. 순서와 표기 차이를 지운다.

    services/usage.py 도 쓴다 — 함께 쓰는 포켓몬 목록이 저쪽 표기로 오므로
    우리 이름과 맞출 때 같은 기준이 필요하다.
    """
    parts = re.split(r"[^a-z0-9]+", name.lower())
    out = {SYNONYM.get(p, p) for p in parts if p}
    return frozenset(t for t in out if t)


_tokens = tokens   # 이 모듈 안에서 쓰던 이름


def _cached(path, url):
    """TTL 안이면 캐시, 아니면 받아서 저장. 실패하면 묵은 캐시라도.

    남의 서버가 잠깐 죽었다고 어제 받아둔 채용률까지 못 쓰게 되면 곤란하다.
    """
    if path.exists() and time.time() - path.stat().st_mtime < TTL_SECONDS:
        return json.loads(path.read_text(encoding="utf-8"))

    try:
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data = res.json()
    except (requests.RequestException, ValueError):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def fetch_index():
    """전체 색인. 어떤 이름이 있는지, 폼이 어디로 합쳐지는지가 여기 있다."""
    return _cached(USAGE_DIR / "index.json", f"{BASE}/api")


_lookup = {"by_tokens": None, "by_base": None}


def _build_lookup():
    """색인을 {이름 토큰: battleName} 과 {원종 토큰: battleName} 두 벌로.

    원종 쪽은 두 번 훑는다. 한 번에 하면 색인이 가나다순이라 Alolan Raichu
    가 Raichu 보다 먼저 나오고, 그러면 "라이츄" 를 물었을 때 알로라 쪽이
    잡힌다. 이름과 원종이 같은 항목(진짜 원종)을 먼저 채우고, 남은 자리만
    폼으로 메운다.

    남은 자리를 메우는 게 필요한 이유는 원종 항목이 아예 없는 경우가 있기
    때문이다. 돌핀맨은 "Palafin Zero Form" 만 있고 "Palafin" 이 없다 —
    마이티폼이 배틀 중 상태라 나이브폼으로 집계되기 때문이다.
    """
    index = fetch_index()
    if not index:
        return False

    entries = [e for e in index.get("pokemon", []) if e.get("name")]
    by_tokens = {_tokens(e["name"]): (e.get("battleName") or e["name"])
                 for e in entries}

    by_base = {}
    for want_exact in (True, False):
        for e in entries:
            if e.get("isForm"):
                continue        # 메가는 원종 대표가 될 수 없다
            base = _tokens(e.get("baseName") or e["name"])
            if want_exact != (base == _tokens(e["name"])):
                continue
            by_base.setdefault(base, e.get("battleName") or e["name"])

    _lookup["by_tokens"], _lookup["by_base"] = by_tokens, by_base
    return True


def battle_name(en_name):
    """우리 영문 이름 -> 채용률 쪽 이름. 못 찾으면 None.

    돌려주는 값은 (이름, 메가였는가). 메가폼은 원종으로 접혀 나간다.
    """
    if _lookup["by_tokens"] is None and not _build_lookup():
        return None, False

    was_mega = bool(MEGA_RE.search(en_name))
    base = MEGA_RE.sub("", en_name)

    # 1) 이름 전체가 맞는가 (알로라 라이츄 같은 지역폼)
    hit = _lookup["by_tokens"].get(_tokens(base))
    if hit:
        return hit, was_mega

    # 2) 안 맞으면 원종으로. 저쪽이 폼을 안 나누는 경우다 —
    #    펌킨인 크기, 킬가르도 폼, 모르페코 모양은 한 줄로 합쳐져 있다.
    species = base.split("-")[0]
    hit = _lookup["by_base"].get(_tokens(species))
    return (hit, was_mega) if hit else (None, was_mega)


def fetch_battle(name, fmt="Singles"):
    """한 마리의 채용 데이터. 못 받으면 None."""
    if fmt not in FORMATS:
        return None
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return _cached(USAGE_DIR / f"{fmt}_{key}.json",
                   f"{BASE}/api/battle/{fmt}/{key}")


def clear():
    """캐시를 비운다. 이름 맞추기를 고친 뒤 다시 받게 할 때 쓴다."""
    _lookup["by_tokens"] = _lookup["by_base"] = None
    if not USAGE_DIR.exists():
        return 0
    files = list(USAGE_DIR.glob("*.json"))
    for f in files:
        f.unlink()
    return len(files)
