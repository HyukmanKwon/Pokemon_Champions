"""채용률 하루치를 받아 DB 에 쌓는다.

    python -m scripts.etl.sync_usage                  최신 하루, Singles
    python -m scripts.etl.sync_usage --dry-run        받아만 보고 넣지 않는다
    python -m scripts.etl.sync_usage --date 30_07_2026
    python -m scripts.etl.sync_usage --format Doubles
    python -m scripts.etl.sync_usage --fill-missing   처음 보는 기술·도구를 채운다
    python -m scripts.etl.sync_usage --backfill       안 받은 날짜를 전부 (자동 실행용)

── 왜 build.py 에 안 들어가나 ──
  PokeAPI 가 아니고, 한 번 만들고 끝이 아니다. build.py 는 빈 DB 에 한 번
  도는 물건이고 이것은 매일 도는 물건이다. 성질이 달라서 STEPS 에 넣지
  않는다. migrate_roster · fill_moves 와 같은 자리다. (README §2)

── 왜 서두르나 ──
  저쪽은 일자별 자료를 16일치만 남긴다. 오늘 안 받은 날짜는 16일 뒤에
  사라지고 다시 받을 방법이 없다.

── 이어받기 ──
  이미 있는 (시즌·날짜·포맷·이름) 은 건너뛴다. 중간에 끊겨도 다시 돌리면
  남은 것부터 이어간다. 같은 날을 다시 받으면 행을 갈아끼운다 —
  두 벌이 되면 추세가 조용히 틀어진다. (usage_repo.save)

── 처음 보는 기술·도구 ──
  우리 moves · items 는 사람이 고른 목록이다. 저쪽에는 그 목록에 없는 것이
  나올 수 있다(요정의깃털). 이름은 텍스트로 저장하므로 적재는 막히지
  않지만, 한국어 이름이 안 붙고 계산기에서도 못 고른다. --fill-missing 을
  주면 PokeAPI 에서 받아 채운다.

  채운 것은 get_moves.moves_M_B / get_items.EXTRA_ITEMS 에도 손으로
  넣어야 한다. 그 목록이 재구축의 출처라서, 안 넣으면 다시 지어질 때
  사라진다. 무엇을 넣어야 하는지는 끝에 출력한다.
"""

import argparse
import sys
import time
from datetime import date

from pokemon_champions.db import connect
from pokemon_champions.db.repositories import lookup_repo, pokemon_repo, usage_repo
from pokemon_champions.usecases import usage, usage_source

from . import usage_csv

from ..get.items import COLUMNS as ITEM_COLUMNS
from ..get.items import fetch_item, parse_item
from ..get.moves import COLUMNS as MOVE_COLUMNS
from ..get.moves import (STAT_COLUMNS, STAT_TABLE, fetch_move, parse_move,
                        parse_stat_changes)

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


def split_rows(raw_rows):
    """usage_csv 의 rows 를 (picks, spreads) 로 가른다.

    저쪽이 한 CSV 에 여섯 갈래를 섞어 준다. 모양이 둘이라 표도 둘이다 —
    이름이 있는 줄과, 이름 없이 여섯 칸이 한 벌로 오는 SP 배분.

    우리 것으로 옮기는 일은 여기서 안 한다. 그 대응은 usage_names 가
    한 벌만 들고 있고(link_names), 이 줄들은 저쪽 표기를 그대로 담는다.
    stat_up / stat_down 도 안 담는다 — 성격이 정해지면 따라오는 값이라
    pokemon_natures 에서 읽으면 된다.
    """
    picks, spreads = [], []
    for raw in raw_rows:
        cat, en = raw["category"], raw["name"] or None
        if cat == "stat_points":
            spreads.append({"rank": raw["rank"],
                            "percent": raw["percentage_value"],
                            **{c: raw.get(c) for c in usage_csv.SP_COLUMNS}})
        elif en is not None:
            picks.append({"category": cat, "rank": raw["rank"],
                          "source_name": en,
                          "percent": raw["percentage_value"]})
    return picks, spreads


def resolve_names(conn, picks, maps, index):
    """이번에 처음 보는 이름을 usage_names · battle_names 에 올린다.

    행마다 붙이지 않는다. 이름 726개가 15만 줄에 흩어져 있어서, 대응을
    줄마다 적으면 같은 것을 1,389번까지 되풀이한다. (성격 27개 / 37,500줄)
    """
    by_cat = {}
    for p in picks:
        by_cat.setdefault(p["category"], set()).add(p["source_name"])

    for cat, names in by_cat.items():
        if cat == "teammate":
            # 팀원은 포켓몬이라 battle_names 가 이미 그 역할이다.
            for name in names:
                usage_repo.link_battle_name(
                    conn, name, usage.resolve_pokemon(index, name))
        elif cat in LINK_TABLE:
            table = LINK_TABLE[cat]
            usage_repo.link_names(conn, cat, {
                name: maps[table].get(usage.slugify(name)) for name in names})


def collect(conn, fmt, season, date, sleep, limit, dry_run, refetch=False):
    """하루치를 받아 넣는다. (넣음, 건너뜀, 실패) 를 돌려준다."""
    entries = usage_csv.csv_entries(fmt=fmt, season=season, date=date)
    if not entries:
        print("받을 것이 없습니다. 색인을 못 받았거나 그 날짜가 없습니다.")
        return 0, 0, 0

    season = entries[0]["season"]
    date = entries[0]["date"]
    day = usage_csv.to_date(date)
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

        rows = usage_csv.fetch_csv(entry["path"])
        if rows is None:
            failed += 1
            print(f"  ✗ {name} — 못 받았습니다")
            continue

        ours = usage.resolve_pokemon(index, name)
        if ours is None:
            unlinked.append(name)

        if not dry_run:
            picks, spreads = split_rows(rows)
            resolve_names(conn, picks, maps, index)
            usage_repo.save(
                conn,
                {"season": season, "snapshot_date": day, "format": fmt,
                 "battle_name": name, "pokemon_name": ours,
                 "source": entry["path"]},
                picks, spreads,
            )
            # 순위도 같이 넣는다. 줄마다 같은 값이 오므로 첫 줄에서 집는다.
            # 색인이 주는 것과 같은 사실이라 한 표로 모은다 (source 로 구분).
            position = rows[0].get("column_position")
            if position is not None:
                usage_repo.save_rankings(conn, day, fmt, season, "csv", [
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
    """전체 메타 순위를 받아 usage_rankings 에 오늘치로 넣는다.

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
    n = usage_repo.save_rankings(conn, date.today(), fmt, season, "index", got)
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
            picks, spreads = split_rows(data["rows"])
            resolve_names(conn, picks, maps, index)
            usage_repo.save(
                conn,
                {"season": season, "snapshot_date": today, "format": fmt,
                 "battle_name": name, "pokemon_name": ours, "source": "live"},
                picks, spreads,
            )
            usage_repo.save_rankings(conn, today, fmt, season, "live", [
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
    for s, d in usage_csv.daily_dates(season):
        day = usage_csv.to_date(d)
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
    todo = ([(s, d) for s, d in usage_csv.daily_dates(season)
             if not since or usage_csv.to_date(d) >= since] if refetch
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
    args = ap.parse_args(argv)

    conn = connect()
    try:
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

        entries = usage_csv.csv_entries(
            fmt=args.format, season=args.season, date=args.date)
        day = usage_csv.to_date(entries[0]["date"]) if entries else None
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

        print("\n재구축 때 사라지지 않게 아래 목록에도 넣으세요.")
        for where, names in added.items():
            if names:
                print(f"  {where}: {', '.join(repr(n) for n in names)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
