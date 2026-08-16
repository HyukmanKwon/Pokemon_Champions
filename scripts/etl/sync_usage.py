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
  않는다. migrate_roster · sync_moves 와 같은 자리다. (README §2)

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

from .get_items import COLUMNS as ITEM_COLUMNS
from .get_items import fetch_item, parse_item
from .get_moves import COLUMNS as MOVE_COLUMNS
from .get_moves import (STAT_COLUMNS, STAT_TABLE, fetch_move, parse_move,
                        parse_stat_changes)

# 저쪽 갈래 -> 이름을 맞춰볼 우리 표. teammate 는 pokemons 지만 이름 규칙이
# 달라 여기 넣지 않는다 (resolve_pokemon 이 따로 한다).
FILLABLE = {"move": ("moves", "name"), "held_item": ("items", "name")}


# 갈래별로 이름을 맞춰볼 우리 표. usage_rows.linked_name 이 이 결과다.
# teammate 만 따로인 이유는 이름 규칙이 달라서다 (raichu-alola vs
# Alolan Raichu) — resolve_pokemon 이 토큰으로 맞춘다.
LINK_TABLE = {"move": "moves", "held_item": "items", "ability": "abilities"}


def to_row(raw, maps, index):
    """usage_csv 의 rows 한 줄 -> usage_rows 한 줄.

    maps 와 index 는 이름을 우리 것으로 맞추는 데 쓴다. 한 마리에 50줄이
    붙으므로 줄마다 새로 만들면 235배가 된다 — 부르는 쪽이 한 번 만들어
    넘긴다.
    """
    cat, en = raw["category"], raw["name"] or None
    if en is None:
        linked = None
    elif cat == "teammate":
        linked = usage.resolve_pokemon(index, en)
    elif cat in LINK_TABLE:
        linked = maps[LINK_TABLE[cat]].get(usage.slugify(en))
    else:
        linked = None                     # stat_alignment · stat_points

    return {
        "category": cat,
        "rank": raw["rank"],
        "name": en,                       # SP 배분 줄은 이름이 없다
        "linked_name": linked,
        "percent": raw["percentage_value"],
        "stat_up": usage.STAT_KEY.get(raw["stat_up"]),
        "stat_down": usage.STAT_KEY.get(raw["stat_down"]),
        **{c: raw.get(c) for c in usage_csv.SP_COLUMNS},
    }


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
    maps = {t: lookup_repo.fetch_ko_map(conn, t)
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
            usage_repo.save(
                conn,
                {"season": season, "snapshot_date": day, "format": fmt,
                 "battle_name": name, "pokemon_name": ours,
                 "source": entry["path"],
                 # 줄마다 같은 값이 오므로 첫 줄에서 집는다. 그 포켓몬의
                 # 메타 순위이지 줄의 성질이 아니라서 스냅샷 쪽에 둔다.
                 "usage_rank": rows[0].get("column_position")},
                [to_row(r, maps, index) for r in rows],
            )
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


def sync_rankings(conn, fmt, season="Current", dry_run=False):
    """전체 메타 순위를 받아 usage_rankings 에 오늘치로 넣는다.

    요청 한 번이면 235마리가 다 온다. 포켓몬마다 CSV 를 받는 collect() 와
    견주면 235분의 1이라, 날짜별 CSV 를 다 받지 않아도 "지금 누가 제일
    많이 쓰이나" 는 늘 최신으로 둘 수 있다.

    저쪽이 날짜를 안 주므로 받은 날(오늘)로 찍는다. 같은 날 다시 받으면
    갈아끼운다.
    """
    got = usage_source.rankings(fmt=fmt, season=season)
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
    n = usage_repo.save_rankings(conn, date.today(), fmt, got)
    conn.commit()
    return n


def missing_dates(conn, fmt, season=None):
    """저쪽이 아직 주는 날짜 중 우리가 안 받은 것. 오래된 것부터."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT snapshot_date FROM usage_snapshots "
                "WHERE format = %s", (fmt,))
    have = {r[0] for r in cur.fetchall()}
    return [(s, d) for s, d in usage_csv.daily_dates(season)
            if usage_csv.to_date(d) not in have]


def backfill(conn, fmt, season, sleep, limit, dry_run, refetch=False):
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
    todo = ([(s, d) for s, d in usage_csv.daily_dates(season)] if refetch
            else missing_dates(conn, fmt, season))
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
    ap.add_argument("--date", help="저쪽 폴더 이름. 예: 30_07_2026. "
                                   "안 주면 가장 최근 하루")
    ap.add_argument("--refetch", action="store_true",
                    help="이미 받은 날짜도 다시 받는다. 칸을 새로 늘렸을 때 쓴다")
    ap.add_argument("--rankings-only", action="store_true",
                    help="전체 순위만 받는다. 요청 1회, 몇 초")
    ap.add_argument("--backfill", action="store_true",
                    help="안 받은 날짜를 오래된 것부터 전부 받는다. "
                         "--date 는 무시된다")
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

        run = backfill if args.backfill else collect
        saved, skipped, failed = (
            run(conn, args.format, args.season, args.sleep,
                args.limit, args.dry_run, args.refetch)
            if args.backfill else
            run(conn, args.format, args.season, args.date,
                args.sleep, args.limit, args.dry_run, args.refetch))
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
