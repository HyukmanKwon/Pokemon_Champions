"""채용률 기록 — 하루 한 벌씩 쌓이는 스냅샷.

다른 repo 와 달리 쓰기가 있다. 이 표만 ETL 이 만들고 끝나는 것이 아니라
계속 자라기 때문이다. (scripts/etl/sync_usage.py)

── 같은 날을 두 번 받아도 한 벌이어야 한다 ──
  받다가 끊기면 이어서 다시 돌리게 된다. 그때 이미 넣은 것이 두 벌이 되면
  추세가 조용히 틀어진다. 그래서 (시즌·날짜·포맷·이름) 이 같으면 새 스냅샷을
  만들지 않고 그 자리의 행을 갈아끼운다.
"""

from ._rows import rows

ROW_COLUMNS = [
    "snapshot_id", "category", "rank", "name", "percent",
    "stat_up", "stat_down",
    "hp_points", "attack_points", "defense_points",
    "sp_atk_points", "sp_def_points", "speed_points",
]


def known_keys(conn, season, fmt):
    """이미 받아둔 (날짜, 저쪽 이름) 집합. 이어받을 때 무엇을 건너뛸지 정한다."""
    cur = conn.cursor()
    cur.execute(
        "SELECT snapshot_date, battle_name FROM usage_snapshots"
        " WHERE season = %s AND format = %s", (season, fmt))
    return {(d, n) for d, n in cur.fetchall()}


def save(conn, meta, rows):
    """스냅샷 한 장을 넣거나 갈아끼운다. snapshot_id 를 돌려준다.

    meta 는 season · snapshot_date · format · battle_name · pokemon_name ·
    source 여섯 개다. rows 는 ROW_COLUMNS 에서 snapshot_id 를 뺀 dict 들.
    """
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO usage_snapshots
            (season, snapshot_date, format, battle_name, pokemon_name, source)
        VALUES (%(season)s, %(snapshot_date)s, %(format)s,
                %(battle_name)s, %(pokemon_name)s, %(source)s)
        ON CONFLICT (season, snapshot_date, format, battle_name) DO UPDATE
            SET pokemon_name = EXCLUDED.pokemon_name,
                source       = EXCLUDED.source,
                fetched_at   = now()
        RETURNING id
        """,
        meta,
    )
    snapshot_id = cur.fetchone()[0]

    # 갈아끼우기다. 저쪽 순위가 바뀌면 없어진 줄이 생기는데, 지우지 않으면
    # 옛 줄이 남아 한 스냅샷에 두 시점이 섞인다.
    cur.execute("DELETE FROM usage_rows WHERE snapshot_id = %s", (snapshot_id,))

    fields = ROW_COLUMNS[1:]
    cur.executemany(
        f"INSERT INTO usage_rows ({', '.join(ROW_COLUMNS)})"
        f" VALUES (%(snapshot_id)s, {', '.join('%(' + f + ')s' for f in fields)})",
        [{"snapshot_id": snapshot_id, **{f: r.get(f) for f in fields}}
         for r in rows],
    )
    return snapshot_id


def distinct_names(conn, category, season=None, snapshot_date=None, fmt=None):
    """그 갈래에 등장한 영문 이름 전부. 우리 표에 없는 것을 찾을 때 쓴다."""
    sql = ["SELECT DISTINCT r.name FROM usage_rows r",
           "JOIN usage_snapshots s ON s.id = r.snapshot_id",
           "WHERE r.category = %s AND r.name IS NOT NULL"]
    args = [category]
    for column, value in (("s.season", season), ("s.snapshot_date", snapshot_date),
                          ("s.format", fmt)):
        if value is not None:
            sql.append(f"AND {column} = %s")
            args.append(value)

    cur = conn.cursor()
    cur.execute(" ".join(sql), args)
    return sorted(r[0] for r in cur.fetchall())


def counts(conn):
    """(스냅샷 수, 행 수, 가장 이른 날, 가장 늦은 날). 쌓인 것을 한눈에."""
    cur = conn.cursor()
    cur.execute(
        "SELECT (SELECT count(*) FROM usage_snapshots),"
        "       (SELECT count(*) FROM usage_rows),"
        "       (SELECT min(snapshot_date) FROM usage_snapshots),"
        "       (SELECT max(snapshot_date) FROM usage_snapshots)")
    return cur.fetchone()


def fetch_top_build(conn, pokemon_name, fmt="Singles", moves=4):
    """그 포켓몬의 가장 최근 스냅샷에서 카테고리별 1위. 없으면 빈 리스트.

    기술만 여러 줄이다(기본 4개). 나머지는 1위 한 줄뿐이라 rank = 1 로
    거른다 — 2위 이하를 여기서 주면 부르는 쪽이 다시 골라야 한다.

    ── 왜 최신 하루만 보나 ──
      여러 날을 평균 내면 "아무도 안 쓰는 조합" 이 나온다. 도구 1위가
      기합의띠인 날과 구애머리띠인 날을 섞으면 그 중간이 되는데, 실제로
      그렇게 쓰는 사람은 없다. 하루치 1위는 적어도 그날 실제로 가장
      많이 쓰인 값이다.

      추세를 보고 싶으면 그건 다른 질문이고 다른 함수다.

    돌려주는 것은 저쪽 표기 그대로(Focus Sash)다. 한국어로 옮기는 것은
    usecases/usage.py 가 한다 — repositories 는 이름을 안 만진다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        WITH latest AS (
            SELECT id FROM usage_snapshots
            WHERE pokemon_name = %s AND format = %s
            ORDER BY snapshot_date DESC, id DESC
            LIMIT 1
        )
        SELECT r.category, r.rank, r.name, r.percent,
               r.stat_up, r.stat_down,
               r.hp_points, r.attack_points, r.defense_points,
               r.sp_atk_points, r.sp_def_points, r.speed_points,
               s.snapshot_date, s.season
        FROM usage_rows r
        JOIN latest l ON l.id = r.snapshot_id
        JOIN usage_snapshots s ON s.id = r.snapshot_id
        WHERE (r.category = 'move' AND r.rank <= %s) OR r.rank = 1
        ORDER BY r.category, r.rank
        """,
        (pokemon_name, fmt, moves),
    )
    return rows(cur)
