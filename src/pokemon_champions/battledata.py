"""배틀 데이터 — championsbattledata.com 에서 받아 data/cache/usage/ 에 캐시한다.

── 왜 이 층에 있나 ──
  assets.py 와 같은 자리다. 프로젝트 바깥에서 받아 캐시하는 일이고 DB 를
  보지 않는다. 한국어로 바꾸고 DB 와 맞추는 것은 usecases/usage.py 가 한다.
  여기서 DB 를 부르면 "네트워크가 안 될 때" 와 "DB 에 없을 때" 가 한 함수
  안에서 섞인다.

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

import csv
import io
import json
import re
import time
import urllib.parse
from datetime import datetime

import requests

from .config import CACHE_DIR

BASE = "https://championsbattledata.com"
USAGE_DIR = CACHE_DIR / "usage"
TTL_SECONDS = 12 * 60 * 60
FORMATS = ("Singles", "Doubles")

# 같은 것을 가리키는 다른 표기. 토큰을 이 표로 한 번 통과시킨 뒤 비교한다.
#
# 빈 문자열은 "이 낱말은 이름에 보태는 것이 없다" 는 뜻이다. 저쪽은 폼을
# 사람이 읽는 문장처럼 적어서(Aegislash Shield Forme, Vivillon Fancy Pattern)
# 우리 슬러그(aegislash-shield)와 낱말 수가 어긋난다. 그 꼬리말을 지운다.
SYNONYM = {
    "alolan": "alola", "galarian": "galar", "hisuian": "hisui",
    "paldean": "paldea", "breed": "", "form": "", "forme": "", "the": "",
    "variety": "", "pattern": "",
    # 펌킨인 제일 큰 크기를 저쪽은 Jumbo, PokeAPI 는 super 라고 부른다.
    "jumbo": "super",
}

# 메가 꼬리. 우리 이름에서 이걸 떼면 원종이 된다.
MEGA_RE = re.compile(r"-mega(-[xy])?$")


def tokens(name):
    """이름을 비교용 토큰 집합으로. 순서와 표기 차이를 지운다.

    usecases/usage.py 도 쓴다 — 함께 쓰는 포켓몬 목록이 저쪽 표기로 오므로
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


# ─────────────────────────────────────────────────────────────
# 지난 날짜 — CSV 로만 받힌다
#
# /api/battle/{fmt}/{key} 는 date 를 줘도 무시하고 늘 최신 하루치를 준다.
# 없는 날짜를 물어도 마찬가지라 에러로도 안 걸린다. 지난 날짜는 색인이
# 알려주는 원본 CSV 경로로 받는 수밖에 없다.
#
# 저쪽은 일자별 폴더를 16일치만 남긴다. 그보다 오래된 것은 색인에서 사라지고
# 다시 받을 방법이 없어서, 받아둔 것을 DB 에 옮기는 것이 유일한 보관이다.
# (scripts/etl/sync_usage.py -> usage_snapshots)
#
# 돌려주는 모양은 fetch_battle() 의 rows 와 같게 맞춘다. 같은 자료를 읽는
# 코드가 받아온 경로에 따라 두 벌로 갈리지 않게 하려는 것이다.
# ─────────────────────────────────────────────────────────────

SP_COLUMNS = ("hp_points", "attack_points", "defense_points",
              "sp_atk_points", "sp_def_points", "speed_points")


def _int(text):
    text = (text or "").strip()
    return int(text) if text.lstrip("-").isdigit() else None


def _percent(text):
    """'99.4%' -> 99.4. 빈 칸(함께 쓰는 포켓몬)은 None."""
    text = (text or "").strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def parse_csv(text):
    """CSV 한 장을 fetch_battle() 의 rows 와 같은 모양으로. 아니면 None.

    없는 날짜나 이름을 물으면 404 가 아니라 화면 HTML 이 200 으로 온다.
    상태 코드로는 못 거르므로 내용을 본다.
    """
    if not text or text.lstrip().startswith("<"):
        return None

    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if not r.get("category"):
            continue
        # 날짜마다 칸이 조금씩 다르다. 25_07 에는 source_time_seconds 가
        # 하나 더 붙어 있었다. 아는 칸만 집어서 그 차이를 여기서 흡수한다.
        row = {
            "category": r["category"],
            "rank": _int(r.get("rank")),
            "name": (r.get("name") or "").strip(),
            "percentage_value": _percent(r.get("percentage")),
            "stat_up": (r.get("stat_up") or "").strip(),
            "stat_down": (r.get("stat_down") or "").strip(),
        }
        row.update({c: _int(r.get(c)) for c in SP_COLUMNS})
        rows.append(row)
    return rows or None


def fetch_csv(path):
    """색인이 준 CSV 경로 하나를 rows 로. 못 받으면 None.

    경로에 공백이 들어간다 (.../Singles/Alolan Raichu.csv). 인코딩해야 한다.
    캐시하지 않는다 — 지난 날짜를 두는 곳은 DB 다.
    """
    try:
        res = requests.get(f"{BASE}/{urllib.parse.quote(path)}", timeout=15)
        res.raise_for_status()
    except requests.RequestException:
        return None
    return parse_csv(res.text)


def to_date(folder):
    """저쪽 폴더 이름 '04_08_2026' -> date. 모양이 다르면 None."""
    try:
        return datetime.strptime(folder, "%d_%m_%Y").date()
    except (ValueError, TypeError):
        return None


def daily_dates(season=None):
    """일자별 자료가 있는 날짜들. 최신이 뒤로 오게 정렬해서 돌려준다.

    돌려주는 값은 (season, 폴더이름) 이다. 폴더 이름은 그대로 둔다 —
    URL 을 만들 때 쓰는 것이 날짜가 아니라 이 문자열이기 때문이다.
    """
    index = fetch_index()
    if not index:
        return []

    out = []
    for folder in index.get("dailyDataFolders", []):
        head, _, tail = folder.partition("/")
        if season and head != season:
            continue
        if to_date(tail):
            out.append((head, tail))
    return sorted(out, key=lambda sd: to_date(sd[1]))


def csv_entries(fmt="Singles", season=None, date=None):
    """그 날짜에 받을 수 있는 CSV 목록. [{battle_name, season, date, path}]

    date 를 안 주면 가장 최근 하루를 고른다. 경로를 우리가 조립하지 않고
    색인이 적어둔 것을 그대로 쓴다 — 어떤 폼이 어느 파일에 들어 있는지는
    저쪽 사정이라, 규칙으로 짐작하면 조용히 어긋난다.
    """
    index = fetch_index()
    if not index:
        return []

    if date is None:
        dates = daily_dates(season)
        if not dates:
            return []
        season, date = dates[-1]

    out = []
    for entry in index.get("pokemon", []):
        name = entry.get("battleName") or entry.get("name")
        if not name:
            continue
        for csv_info in entry.get("battleDataCsvs") or []:
            if (csv_info.get("date") == date
                    and csv_info.get("format") == fmt
                    and (season is None or csv_info.get("season") == season)):
                out.append({"battle_name": name,
                            "season": csv_info.get("season"),
                            "date": date,
                            "path": csv_info["path"]})
                break
    return out


def clear():
    """캐시를 비운다. 이름 맞추기를 고친 뒤 다시 받게 할 때 쓴다."""
    _lookup["by_tokens"] = _lookup["by_base"] = None
    if not USAGE_DIR.exists():
        return 0
    files = list(USAGE_DIR.glob("*.json"))
    for f in files:
        f.unlink()
    return len(files)
