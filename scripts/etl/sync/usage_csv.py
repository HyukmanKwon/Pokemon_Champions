"""지난 날짜의 채용률을 CSV 로 받아온다. ETL 전용이다.

    scripts/etl/sync_usage.py 만 쓴다.

── 왜 src/ 가 아니라 여기인가 ──
  앱은 "오늘 이 포켓몬이 얼마나 쓰이나" 만 묻고, 그건
  usecases/usage_source.py 의 fetch_battle() 이 답한다. 지난 날짜를 훑어
  DB 에 쌓는 것은 하루 한 번 도는 수집 작업이지 요청마다 도는 일이 아니다.

  생명주기가 다른 코드를 같이 두면 배포판에 수집기가 딸려 들어가고,
  저쪽 CSV 형식이 바뀔 때 앱까지 같이 깨진다. (CLAUDE.md 규칙 4)

── 왜 CSV 인가 ──
  /api/battle/{fmt}/{key} 는 date 를 줘도 무시하고 늘 최신 하루치를 준다.
  없는 날짜를 물어도 마찬가지라 에러로도 안 걸린다. 지난 날짜는 색인이
  알려주는 원본 CSV 경로로 받는 수밖에 없다.

  저쪽은 일자별 폴더를 16일치만 남긴다. 그보다 오래된 것은 색인에서
  사라지고 다시 받을 방법이 없어서, 받아둔 것을 DB 에 옮기는 것이 유일한
  보관이다. (sync_usage.py -> usage_snapshots)

── 모양은 fetch_battle() 과 같게 ──
  돌려주는 rows 를 usage_source.fetch_battle() 과 맞춘다. 같은 자료를 읽는
  코드가 받아온 경로에 따라 두 벌로 갈리지 않게 하려는 것이다.
"""

import csv
import io
import urllib.parse
from datetime import datetime

import requests

from pokemon_champions.usecases.usage_source import BASE, fetch_index

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
            # 그 포켓몬의 메타 순위. 줄마다 같은 값이 되풀이돼 오지만
            # 버리지 않는다 — 이것이 "가장 많이 쓰이는 포켓몬" 의 답이다.
            # 예전에는 파싱에서 떨어뜨려서, 받아놓고도 못 쓰고 있었다.
            "column_position": _int(r.get("column_position")),
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


