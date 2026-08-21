"""채용률을 받아 DB 에 쌓는다. 날마다 도는 유일한 수집 지점.

    python -m scripts.etl.sync_usage --live           저쪽 오늘 값 (기본 경로)
    python -m scripts.etl.sync_usage --backfill       안 받은 날짜를 전부 (자동 실행용)
    python -m scripts.etl.sync_usage --rankings-only  순위만. 요청 1회, 몇 초
    python -m scripts.etl.sync_usage --dry-run        받아만 보고 넣지 않는다
    python -m scripts.etl.sync_usage --date 30_07_2026
    python -m scripts.etl.sync_usage --fill-missing   처음 보는 기술·도구를 채운다
    python -m scripts.etl.sync_usage --check-names    317마리가 어디에 붙는지 훑는다

── 왜 build.py 에 안 들어가나 ──
  PokeAPI 가 아니고, 한 번 만들고 끝이 아니다. build.py 는 빈 DB 에 한 번
  도는 물건이고 이것은 매일 도는 물건이다. data/sql/ 에도 안 들어간다 —
  날마다 붙는 것을 파일로 굳히면 그 파일이 매일 바뀐다.

── 왜 서두르나 ──
  저쪽은 일자별 자료를 16일치만 남긴다. 오늘 안 받은 날짜는 16일 뒤에
  사라지고 다시 받을 방법이 없다. 그래서 자동 실행은 "오늘 것만" 이
  아니라 --backfill 로 "안 받은 것 전부" 를 부른다.

── 받는 길이 둘인 이유 ──
    --live      저쪽 '오늘 값'. 날짜가 안 붙어 오므로 받은 날로 우리가 찍는다
    --backfill  저쪽이 보관한 날짜별 CSV. 우리가 못 돈 날을 메운다

  저쪽이 오늘 값은 언제든 주지만 날짜별 보관은 거른다(8-05~8-17 열사흘이
  색인에 없다). 그래서 우리 시계열은 --live 로 이어 두고, 저쪽이 남긴
  날짜는 --backfill 로 주워 담는다.

── 이어받기 ──
  이미 있는 (시즌·날짜·포맷·이름) 은 건너뛴다. 중간에 끊겨도 다시 돌리면
  남은 것부터 이어간다. 같은 날을 다시 받으면 행을 갈아끼운다 —
  두 벌이 되면 추세가 조용히 틀어진다. (usage_repo.save)

── 왜 한 파일인가 ──
  전에는 sync/usage.py · sync/usage_csv.py · scripts/check_usage.py 셋이었다.
  셋 다 저쪽 서버에서 채용률을 가져오는 일이고, 이름 맞추는 규칙을 함께
  본다. 갈라 두면 "이름이 안 붙는다" 를 쫓을 때 세 파일을 오가야 한다.

  앱이 요청마다 쓰는 쪽은 여기가 아니다 — usecases/usage_source.py 다.
  그쪽은 배포판에 들어가고 이 파일은 안 들어간다. 생명주기가 달라서
  합치지 않는다.
"""

import argparse
import csv
import io
import json
import sys
import time
import urllib.parse
from datetime import date, datetime

import requests

from pokemon_champions.db import connect
from pokemon_champions.db.repositories import lookup_repo, pokemon_repo, usage_repo
from pokemon_champions.usecases import usage, usage_source
from pokemon_champions.usecases.usage_source import BASE, fetch_index

from .pokeapi import (ITEMS_COLUMNS as ITEM_COLUMNS,
                      MOVES_COLUMNS as MOVE_COLUMNS,
                      MOVE_STAT_COLUMNS as STAT_COLUMNS,
                      MOVE_STAT_TABLE as STAT_TABLE,
                      fetch_item, fetch_move, parse_item, parse_move,
                      parse_stat_changes)


# ─────────────────────────────────────────────────────────────
# 지난 날짜 — 색인이 가리키는 CSV 를 받는다
# /api/battle/{fmt}/{key} 는 date 를 줘도 무시하고 늘 최신 하루치를
# 준다. 없는 날짜를 물어도 에러로 안 걸린다. 지난 날짜는 색인이
# 알려주는 원본 CSV 경로로 받는 수밖에 없다.
#
# 돌려주는 rows 는 usage_source.fetch_battle() 과 모양을 맞춘다 —
# 같은 자료를 읽는 코드가 받아온 경로에 따라 갈리지 않게 한다.
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

# ─────────────────────────────────────────────────────────────
# 받은 것을 우리 표로
# ─────────────────────────────────────────────────────────────

# 저쪽 갈래 -> 이름을 맞춰볼 우리 표. teammate 는 pokemons 지만 이름 규칙이
# 달라 여기 넣지 않는다 (resolve_pokemon 이 따로 한다).
FILLABLE = {"move": ("moves", "name"), "held_item": ("items", "name")}


# 갈래별로 이름을 맞춰볼 우리 표. usage_names 가 이 결과를 담는다.
# teammate 만 따로인 이유는 이름 규칙이 달라서다 (raichu-alola vs
# Alolan Raichu) — resolve_pokemon 이 토큰으로 맞춘다.
#
# stat_alignment 는 성격 이름(Jolly)이 오는데 오래 비워 두었었다. 그 줄이
# 37,500개라 "어느 성격을 많이 쓰나" 를 SQL 로 못 냈다. 슬러그가 곧
# pokemon_natures.en_name 이라 다른 갈래와 같은 방식으로 붙는다.
# 지금 시즌과 그 시작일. 저쪽 폴더의 시즌 이름은 갱신되지 않아서
# (2026-08-18 자료도 M4/ 아래 있다) 우리가 따로 적는다. 시즌이 바뀌면
# 이 둘을 고친다.
SEASON = "M5"
SEASON_START = date(2026, 8, 5)


LINK_TABLE = {"move": "moves", "held_item": "items", "ability": "abilities",
              "stat_alignment": "pokemon_natures"}

# 성격만 id 가 아니라 enum 값이다. pokemon_natures 의 기본키가 en_name 이라
# 정수 id 가 아예 없다 — usage_names.nature 도 같은 enum 이다.


def to_rows(raw_rows):
    """usage_csv / fetch_battle 의 rows 를 usage_rows 줄들로.

    갈래가 여섯인데 stat_points 만 모양이 다르다 — 이름이 없고 SP 여섯 칸이
    한 벌로 온다. 한 표에 담되 그쪽은 source_name 이 NULL 이다.

    우리 것으로 옮기는 일은 여기서 안 한다. 그 대응은 usage_names 가
    한 벌만 들고 있고(resolve_names), 이 줄들은 저쪽 표기를 그대로 담는다.
    stat_up / stat_down 도 안 담는다 — 성격이 정해지면 따라오는 값이라
    pokemon_natures 에서 읽으면 된다.
    """
    out = []
    for raw in raw_rows:
        cat, en = raw["category"], raw["name"] or None
        if cat == "stat_points":
            out.append({"category": cat, "rank": raw["rank"],
                        "source_name": None,
                        "percent": raw["percentage_value"],
                        **{c: raw.get(c) for c in SP_COLUMNS}})
        elif en is not None:
            out.append({"category": cat, "rank": raw["rank"],
                        "source_name": en,
                        "percent": raw["percentage_value"]})
    return out


def resolve_names(conn, picks, maps, index):
    """이번에 처음 보는 이름을 usage_names 에 올린다.

    행마다 붙이지 않는다. 이름 726개가 15만 줄에 흩어져 있어서, 대응을
    줄마다 적으면 같은 것을 1,389번까지 되풀이한다. (성격 27개 / 37,500줄)
    """
    by_cat = {}
    for p in picks:
        if p["source_name"] is not None:
            by_cat.setdefault(p["category"], set()).add(p["source_name"])

    for cat, names in by_cat.items():
        if cat == "teammate":
            # 팀원은 포켓몬이라 pokemon 갈래로 올린다.
            for name in names:
                usage_repo.link_battle_name(
                    conn, name, usage.resolve_pokemon(index, name))
        elif cat in LINK_TABLE:
            table = LINK_TABLE[cat]
            usage_repo.link_names(conn, cat, {
                name: maps[table].get(usage.slugify(name)) for name in names})


def collect(conn, fmt, season, date, sleep, limit, dry_run, refetch=False):
    """하루치를 받아 넣는다. (넣음, 건너뜀, 실패) 를 돌려준다."""
    entries = csv_entries(fmt=fmt, season=season, date=date)
    if not entries:
        print("받을 것이 없습니다. 색인을 못 받았거나 그 날짜가 없습니다.")
        return 0, 0, 0

    season = entries[0]["season"]
    date = entries[0]["date"]
    day = to_date(date)
    print(f"{season} · {date} · {fmt} — 대상 {len(entries)}마리")

    have = (usage_repo.known_keys(conn, season, fmt)
            if not dry_run and not refetch else set())
    index = usage.pokemon_index(pokemon_repo.fetch_list(conn))
    # 이름을 우리 것으로 맞추는 표. 한 마리에 50줄이 붙으므로 여기서 한 번만
    # 만든다 — 줄마다 만들면 235마리 × 50줄이 전부 DB 를 다시 읽는다.
    maps = {t: lookup_repo.fetch_id_map(conn, t)
            for t in set(LINK_TABLE.values())}

    saved = skipped = failed = 0
    unlinked = []
    for i, entry in enumerate(entries[:limit] if limit else entries, 1):
        name = entry["battle_name"]
        if (day, name) in have:
            skipped += 1
            continue

        rows = fetch_csv(entry["path"])
        if rows is None:
            failed += 1
            print(f"  ✗ {name} — 못 받았습니다")
            continue

        ours = usage.resolve_pokemon(index, name)
        if ours is None:
            unlinked.append(name)

        if not dry_run:
            rows_ = to_rows(rows)
            resolve_names(conn, rows_, maps, index)
            usage_repo.save(
                conn,
                {"season": season, "snapshot_date": day, "format": fmt,
                 "battle_name": name, "pokemon_name": ours},
                rows_,
            )
            # 순위도 같이 넣는다. 줄마다 같은 값이 오므로 첫 줄에서 집는다.
            # 색인이 주는 것과 같은 사실이라 한 표로 모은다.
            position = rows[0].get("column_position")
            if position is not None:
                usage_repo.save_rankings(conn, day, fmt, season, [
                    {"position": position, "battle_name": name}])
            conn.commit()      # 한 마리씩 확정한다. 끊겨도 앞의 것은 남는다
        saved += 1

        if i % 25 == 0 or i == len(entries):
            print(f"  {i}/{len(entries)} …")
        time.sleep(sleep)

    if unlinked:
        print(f"\n우리 로스터에 없는 이름 {len(unlinked)}개는 "
              f"pokemon_name 을 비워 두고 넣었습니다: {', '.join(unlinked)}")
    return saved, skipped, failed


def find_missing(conn, day, fmt):
    """받은 이름 중 우리 표에 없는 것. {갈래: [(영문, 슬러그)]}"""
    cur = conn.cursor()
    out = {}
    for category, (table, column) in FILLABLE.items():
        cur.execute(f"SELECT {column} FROM {table}")
        have = {r[0] for r in cur.fetchall()}
        gaps = [(en, usage.slugify(en))
                for en in usage_repo.distinct_names(
                    conn, category, snapshot_date=day, fmt=fmt)
                if usage.slugify(en) not in have]
        if gaps:
            out[category] = gaps
    return out


def fill_moves(conn, gaps):
    """없는 기술을 PokeAPI 에서 받아 moves 와 move_stat_changes 에 넣는다."""
    cur = conn.cursor()
    done = []
    for en, slug in gaps:
        data = fetch_move(slug)
        if data is None:
            print(f"  ✗ {en} ({slug}) — PokeAPI 에 없습니다")
            continue
        row = parse_move(data)
        cur.execute(
            f"INSERT INTO moves ({', '.join(MOVE_COLUMNS)})"
            f" VALUES ({', '.join(['%s'] * len(MOVE_COLUMNS))})"
            " ON CONFLICT (name) DO NOTHING",
            tuple(row[c] for c in MOVE_COLUMNS))
        for change in parse_stat_changes(data):
            cur.execute(
                f"INSERT INTO {STAT_TABLE} ({', '.join(STAT_COLUMNS)})"
                " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", change)
        done.append(slug)
        print(f"  + {en:<20} {slug:<20} {row['ko_name'] or '(한국어 없음)'}")
    conn.commit()
    return done


def fill_items(conn, gaps):
    """없는 도구를 PokeAPI 에서 받아 items 에 넣는다."""
    cur = conn.cursor()
    done = []
    for en, slug in gaps:
        data = fetch_item(slug)
        if data is None:
            print(f"  ✗ {en} ({slug}) — PokeAPI 에 없습니다")
            continue
        row = parse_item(data)
        cur.execute(
            f"INSERT INTO items ({', '.join(ITEM_COLUMNS)})"
            f" VALUES ({', '.join(['%s'] * len(ITEM_COLUMNS))})"
            " ON CONFLICT (name) DO NOTHING",
            tuple(row[c] for c in ITEM_COLUMNS))
        done.append(slug)
        print(f"  + {en:<20} {slug:<20} {row['ko_name'] or '(한국어 없음)'}")
    conn.commit()
    return done


def sync_rankings(conn, fmt, season=SEASON, dry_run=False):
    """전체 메타 순위를 받아 usage_snapshots 에 오늘치로 넣는다.

    요청 한 번이면 235마리가 다 온다. 포켓몬마다 CSV 를 받는 collect() 와
    견주면 235분의 1이라, 날짜별 CSV 를 다 받지 않아도 "지금 누가 제일
    많이 쓰이나" 는 늘 최신으로 둘 수 있다.

    저쪽이 날짜를 안 주므로 받은 날(오늘)로 찍는다. 같은 날 다시 받으면
    갈아끼운다.

    시즌도 우리가 적는다. 저쪽 색인은 "Current" 라고만 하고 폴더 이름은
    갱신되지 않아서, 둘 다 우리 시즌을 말해 주지 않는다. (SEASON)
    """
    got = usage_source.rankings(fmt=fmt)
    if not got:
        print(f"{fmt}: 순위를 못 받았습니다.")
        return 0

    index = usage.pokemon_index(pokemon_repo.fetch_list(conn))
    unlinked = []
    for r in got:
        r["pokemon_name"] = usage.resolve_pokemon(index, r["battle_name"])
        if r["pokemon_name"] is None:
            unlinked.append(r["battle_name"])

    top = ", ".join(f"{r['position']}.{r['battle_name']}" for r in got[:5])
    print(f"{fmt} 순위 {len(got)}마리 — {top} …")
    if unlinked:
        print(f"  우리 로스터에 없는 이름 {len(unlinked)}개는 "
              f"pokemon_name 을 비워 둡니다: {', '.join(unlinked[:8])}")

    if dry_run:
        return 0
    n = usage_repo.save_rankings(conn, date.today(), fmt, season, got)
    conn.commit()
    return n


def snapshot_live(conn, fmt, sleep, limit, dry_run, season=SEASON):
    """저쪽 '오늘 값' 을 235마리 받아 오늘 날짜로 쌓는다.

    ── 왜 필요한가 ──
      저쪽은 오늘 값을 언제든 준다. 그런데 그것을 날짜별로 보관해 주지
      않는다 — 2026-08-05 부터 8-17 까지 열사흘이 색인에 아예 없다.
      지난 달과 비교하려면 우리가 찍어 두는 수밖에 없다.

      backfill 은 저쪽이 보관한 날짜를 받아온다. 이쪽은 보관 여부와
      무관하게 오늘 값을 우리 시계열에 넣는다. 저쪽이 하루를 거르든
      말든 우리 쪽은 안 끊긴다.

    ── 날짜와 시즌은 우리가 찍는다 ──
      오늘 값에는 날짜가 안 붙어 온다. 받은 날로 찍는다. 시즌도 저쪽
      폴더 이름이 갱신되지 않아 우리가 적는다 (SEASON).

      같은 날 다시 돌리면 갈아끼운다. usage_snapshots 의 UNIQUE 가
      (시즌·날짜·포맷·이름) 이라 두 벌이 되지 않는다.
    """
    got = usage_source.rankings(fmt=fmt)
    if not got:
        print(f"{fmt}: 순위를 못 받아 대상 목록을 만들 수 없습니다.")
        return 0, 0, 0

    today = date.today()
    print(f"{SEASON} · {today} · {fmt} — 오늘 값 {len(got)}마리")

    index = usage.pokemon_index(pokemon_repo.fetch_list(conn))
    maps = {t: lookup_repo.fetch_id_map(conn, t)
            for t in set(LINK_TABLE.values())}

    saved = failed = 0
    unlinked = []
    for i, r in enumerate(got[:limit] if limit else got, 1):
        name = r["battle_name"]
        data = usage_source.fetch_battle(name, fmt)
        if not data or not data.get("rows"):
            failed += 1
            print(f"  ✗ {name} — 못 받았습니다")
            continue

        ours = usage.resolve_pokemon(index, name)
        if ours is None:
            unlinked.append(name)

        if not dry_run:
            rows_ = to_rows(data["rows"])
            resolve_names(conn, rows_, maps, index)
            usage_repo.save(
                conn,
                {"season": season, "snapshot_date": today, "format": fmt,
                 "battle_name": name, "pokemon_name": ours},
                rows_,
            )
            usage_repo.save_rankings(conn, today, fmt, season, [
                {"position": r["position"], "battle_name": name}])
            conn.commit()      # 한 마리씩 확정한다. 끊겨도 앞의 것은 남는다
        saved += 1

        if i % 25 == 0 or i == len(got):
            print(f"  {i}/{len(got)} …")
        time.sleep(sleep)

    if unlinked:
        print(f"\n우리 로스터에 없는 이름 {len(unlinked)}개는 "
              f"연결을 비워 두고 넣었습니다: {', '.join(unlinked[:8])}")
    return saved, 0, failed


def missing_dates(conn, fmt, season=None, since=None):
    """저쪽이 아직 주는 날짜 중 우리가 안 받은 것. 오래된 것부터.

    ── 시즌 이름으로는 못 거른다 ──
      저쪽 폴더 이름의 시즌은 갱신되지 않는다. 2026-08-18 자료도 M4/ 아래
      들어 있어서, --season 으로 걸러도 지난 시즌이 딸려 온다. 그래서
      기간은 since(날짜)로 자른다.
    """
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT snapshot_date FROM usage_snapshots "
                "WHERE format = %s", (fmt,))
    have = {r[0] for r in cur.fetchall()}
    out = []
    for s, d in daily_dates(season):
        day = to_date(d)
        if day in have or (since and day < since):
            continue
        out.append((s, d))
    return out


def backfill(conn, fmt, season, sleep, limit, dry_run, refetch=False,
             since=None):
    """받을 수 있는데 아직 안 받은 날짜를 오래된 것부터 전부.

    ── 왜 필요한가 ──
      저쪽은 일자별 자료를 16일치만 남긴다. 하루라도 거르면 16일 뒤에
      사라지고 다시 받을 방법이 없다. 매일 도는 자동 실행이 며칠 못 돌면
      (노트북을 안 켰다거나) 그 구멍을 여기서 메운다.

      그래서 자동 실행도 이 갈래로 부른다 — "오늘 것만" 이 아니라
      "안 받은 것 전부" 다. 이미 받은 날짜는 collect() 가 건너뛴다.

    ── 오래된 것부터 ──
      중간에 끊기면 사라지기 직전의 것부터 남아 있어야 한다.
    """
    todo = ([(s, d) for s, d in daily_dates(season)
             if not since or to_date(d) >= since] if refetch
            else missing_dates(conn, fmt, season, since))
    if not todo:
        print(f"{fmt}: 받을 수 있는 날짜를 전부 받았습니다.")
        return 0, 0, 0

    print(f"{fmt}: 안 받은 날짜 {len(todo)}개 — {', '.join(d for _, d in todo)}\n")
    total = [0, 0, 0]
    for i, (s, d) in enumerate(todo, 1):
        print(f"── [{i}/{len(todo)}] {d} " + "─" * 30)
        got = collect(conn, fmt, s, d, sleep, limit, dry_run, refetch)
        total = [a + b for a, b in zip(total, got)]
    return tuple(total)

# ─────────────────────────────────────────────────────────────
# 붙음 점검 — DB 를 건드리지 않는다
# ─────────────────────────────────────────────────────────────

def check_names(conn, fmt, miss_only=False):
    """317마리가 채용률 자료의 어느 이름에 붙는지 한 번에 훑는다.

    ── 왜 필요한가 ──
      이름 맞추기를 표로 적지 않고 색인에서 자동으로 한다. 자동이라
      조용히 틀릴 수 있다 — 엉뚱한 포켓몬에 붙어도 에러가 안 난다.
      그래서 317줄을 눈으로 훑을 수 있게 뽑아준다.

      특히 볼 것: 메가폼이 원종으로 접히는지, 지역폼이 제 이름으로
      붙는지, 펌킨인·킬가르도·모르페코처럼 저쪽이 안 나누는 폼이 한
      곳으로 모이는지.
    """
    if usage_source.fetch_index() is None:
        print("색인을 못 받았습니다. 네트워크를 확인하세요.")
        return 1

    rows = pokemon_repo.fetch_list(conn)
    hit = miss = mega = 0
    for r in sorted(rows, key=lambda r: r["name"]):
        name, was_mega = usage_source.battle_name(r["name"])
        if name is None:
            miss += 1
            print(f"  ✗ {r['ko_name'] or r['name']:<18} {r['name']}")
            continue
        hit += 1
        mega += bool(was_mega)
        if not miss_only:
            tag = " (메가→원종)" if was_mega else ""
            print(f"  · {r['ko_name'] or r['name']:<18} -> {name}{tag}")

    print(f"\n붙음 {hit} · 못 붙음 {miss} · 그중 메가 접힘 {mega}")
    print("못 붙은 것은 랭크배틀 표본이 적어 자료에 안 실린 경우가 많습니다.")
    return 0 if miss == 0 else 1


def check_one(conn, ko_name, fmt):
    """한 마리만 실제로 받아 무엇이 오는지 그대로 찍는다."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM pokemons WHERE ko_name = %s", (ko_name,))
    row = cur.fetchone()
    if row is None:
        print(f"'{ko_name}' 은(는) DB 에 없습니다.")
        return 1
    print(json.dumps(usage.usage_of(conn, row[0], ko_name, fmt),
                     ensure_ascii=False, indent=2))
    return 0

# ─────────────────────────────────────────────────────────────
# 실행
# ─────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--format", default="Singles",
                    choices=list(usage_source.FORMATS))
    ap.add_argument("--season", help="예: M4. 안 주면 색인의 최신 시즌")
    ap.add_argument("--since", type=lambda v: date.fromisoformat(v),
                    metavar="YYYY-MM-DD", default=SEASON_START,
                    help=f"이 날짜부터만 받는다 (기본 {SEASON_START}, "
                         "지금 시즌 시작일). --since 1970-01-01 이면 전부")
    ap.add_argument("--date", help="저쪽 폴더 이름. 예: 30_07_2026. "
                                   "안 주면 가장 최근 하루")
    ap.add_argument("--refetch", action="store_true",
                    help="이미 받은 날짜도 다시 받는다. 칸을 새로 늘렸을 때 쓴다")
    ap.add_argument("--rankings-only", action="store_true",
                    help="전체 순위만 받는다. 요청 1회, 몇 초")
    ap.add_argument("--backfill", action="store_true",
                    help="저쪽이 보관한 날짜 중 안 받은 것을 전부 받는다. "
                         "--date 는 무시된다")
    ap.add_argument("--live", action="store_true",
                    help="저쪽 '오늘 값' 을 받아 오늘 날짜로 쌓는다. "
                         "저쪽이 날짜별 보관을 거르므로 이쪽이 기본 수집 경로다")
    ap.add_argument("--dry-run", action="store_true",
                    help="받아만 보고 DB 를 건드리지 않는다")
    ap.add_argument("--fill-missing", action="store_true",
                    help="처음 보는 기술·도구를 PokeAPI 에서 받아 채운다")
    ap.add_argument("--limit", type=int, help="앞의 N 마리만 (시험용)")
    ap.add_argument("--sleep", type=float, default=0.3,
                    help="요청 간격(초). 남의 서버다 (기본 0.3)")

    # 넣지 않고 보기만 하는 갈래. 이름이 조용히 어긋나는 것을 잡는다.
    ap.add_argument("--check-names", action="store_true",
                    help="317마리가 저쪽 어느 이름에 붙는지 훑는다. DB 를 안 건드린다")
    ap.add_argument("--check-miss", action="store_true",
                    help="--check-names 중 못 붙은 것만 찍는다")
    ap.add_argument("--check-one", metavar="한국어이름",
                    help="한 마리만 실제로 받아 응답을 그대로 찍는다")
    ap.add_argument("--clear-cache", action="store_true",
                    help="받아둔 채용률 캐시를 비우고 시작한다")
    args = ap.parse_args(argv)

    conn = connect()
    try:
        if args.clear_cache:
            print(f"캐시 {usage_source.clear()}개 삭제")
        if args.check_one:
            return check_one(conn, args.check_one, args.format)
        if args.check_names or args.check_miss:
            return check_names(conn, args.format, args.check_miss)

        # 순위는 늘 같이 받는다. 요청 한 번이라 공짜에 가깝고, 이게 없으면
        # "가장 많이 쓰이는 포켓몬" 에 답할 자료가 아예 없다.
        sync_rankings(conn, args.format, dry_run=args.dry_run)
        if args.rankings_only:
            return 0
        print()

        if args.live:
            saved, skipped, failed = snapshot_live(
                conn, args.format, args.sleep, args.limit, args.dry_run)
        elif args.backfill:
            saved, skipped, failed = backfill(
                conn, args.format, args.season, args.sleep,
                args.limit, args.dry_run, args.refetch, args.since)
        else:
            saved, skipped, failed = collect(
                conn, args.format, args.season, args.date,
                args.sleep, args.limit, args.dry_run, args.refetch)
        print(f"\n넣음 {saved} · 건너뜀(이미 있음) {skipped} · 못 받음 {failed}")
        if args.dry_run:
            print("--dry-run 이라 DB 는 그대로입니다.")
            return 0

        total, rows, first, last = usage_repo.counts(conn)
        print(f"쌓인 것: 스냅샷 {total}장 · {rows}행 · {first} ~ {last}")

        entries = csv_entries(
            fmt=args.format, season=args.season, date=args.date)
        day = to_date(entries[0]["date"]) if entries else None
        gaps = find_missing(conn, day, args.format)
        if not gaps:
            print("\n우리 표에 없는 기술·도구는 없습니다.")
            return 0

        for category, items in gaps.items():
            print(f"\n{FILLABLE[category][0]} 에 없는 이름 {len(items)}개: "
                  f"{', '.join(en for en, _ in items)}")
        if not args.fill_missing:
            print("\n--fill-missing 을 주면 PokeAPI 에서 받아 채웁니다.")
            return 0

        added = {}
        if "move" in gaps:
            print("\n기술 채우기")
            added["moves_M_B"] = fill_moves(conn, gaps["move"])
        if "held_item" in gaps:
            print("\n도구 채우기")
            added["EXTRA_ITEMS"] = fill_items(conn, gaps["held_item"])

        print("\n재구축 때 사라지지 않게 pokeapi.py 의 아래 목록에도 넣으세요.")
        for where, names in added.items():
            if names:
                print(f"  {where}: {', '.join(repr(n) for n in names)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
