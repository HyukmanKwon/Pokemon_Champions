"""채용률 기록 — 하루 한 벌씩 쌓이는 스냅샷.

다른 repo 와 달리 쓰기가 있다. 이 표만 ETL 이 만들고 끝나는 것이 아니라
계속 자라기 때문이다. (scripts/etl/sync_usage.py)

── 같은 날을 두 번 받아도 한 벌이어야 한다 ──
  받다가 끊기면 이어서 다시 돌리게 된다. 그때 이미 넣은 것이 두 벌이 되면
  추세가 조용히 틀어진다. 그래서 (시즌·날짜·포맷·이름) 이 같으면 새 스냅샷을
  만들지 않고 그 자리의 행을 갈아끼운다.
"""

from ._rows import one, rows

ROW_COLUMNS = [
    "snapshot_id", "category", "rank", "name", "linked_name", "percent",
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
    source · usage_rank 일곱 개다. rows 는 ROW_COLUMNS 에서 snapshot_id 를
    뺀 dict 들.
    """
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO usage_snapshots
            (season, snapshot_date, format, battle_name, pokemon_name,
             source, usage_rank)
        VALUES (%(season)s, %(snapshot_date)s, %(format)s,
                %(battle_name)s, %(pokemon_name)s, %(source)s, %(usage_rank)s)
        ON CONFLICT (season, snapshot_date, format, battle_name) DO UPDATE
            SET pokemon_name = EXCLUDED.pokemon_name,
                source       = EXCLUDED.source,
                usage_rank   = EXCLUDED.usage_rank,
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


def save_rankings(conn, taken_on, fmt, rows):
    """전체 순위 한 벌을 넣거나 갈아끼운다. 넣은 줄 수를 돌려준다.

    rows 는 [{position, battle_name, season, pokemon_name}] 다.

    같은 날을 다시 받으면 갈아끼운다. 저쪽 순위가 하루 안에 바뀌면 옛 줄이
    남아 (taken_on, format, position) UNIQUE 에 걸리므로 먼저 지운다.
    """
    cur = conn.cursor()
    cur.execute("DELETE FROM usage_rankings WHERE taken_on = %s AND format = %s",
                (taken_on, fmt))
    cur.executemany(
        """
        INSERT INTO usage_rankings
            (taken_on, format, season, position, battle_name, pokemon_name)
        VALUES (%(taken_on)s, %(format)s, %(season)s, %(position)s,
                %(battle_name)s, %(pokemon_name)s)
        """,
        [{"taken_on": taken_on, "format": fmt, **r} for r in rows],
    )
    return len(rows)


def fetch_ranking(conn, fmt="Singles", limit=20):
    """가장 최근에 받은 전체 순위. 1위부터.

    "가장 많이 쓰이는 포켓몬" 에 답하는 유일한 자료다. usage_rows 의
    percent 는 전부 그 포켓몬 안에서의 비율이라 이 질문에 못 쓴다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.position, r.battle_name, r.pokemon_name, p.ko_name,
               p.id AS pokemon_id, p.type1, p.type2,
               r.taken_on, r.season
        FROM usage_rankings r
        LEFT JOIN pokemons p ON p.name = r.pokemon_name
        WHERE r.format = %s
          AND r.taken_on = (SELECT max(taken_on) FROM usage_rankings
                            WHERE format = %s)
        ORDER BY r.position
        LIMIT %s
        """,
        # None 이면 전부. psycopg2 가 NULL 로 넘기고 Postgres 의 LIMIT NULL
        # 은 "제한 없음" 이다 — 파이썬에서 문자열을 갈아 끼우지 않아도 된다.
        (fmt, fmt, limit),
    )
    return rows(cur)


def fetch_rank_of(conn, pokemon_name, fmt="Singles"):
    """그 포켓몬의 최신 순위 한 줄. 없으면 None.

    usage_stats 응답에 실어, 모델이 기술 채용률을 순위로 오해하지 않게 한다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT position, taken_on,
               (SELECT count(*) FROM usage_rankings
                WHERE format = r.format AND taken_on = r.taken_on) AS total
        FROM usage_rankings r
        WHERE pokemon_name = %s AND format = %s
        ORDER BY taken_on DESC
        LIMIT 1
        """,
        (pokemon_name, fmt),
    )
    return one(cur)


def fetch_detail(conn, pokemon_name, fmt="Singles", top=10):
    """한 마리의 가장 최근 스냅샷 전부. 갈래별로 top 개까지.

    fetch_top_build 와 다르다. 저쪽은 계산기 기본값을 채우려고 1위만 뽑고,
    이쪽은 화면에 늘어놓으려고 순위대로 다 가져온다.

    저쪽 원본이 갈래마다 주는 개수가 다르다 — 기술·도구·팀원·성격은 10개,
    SP 배분은 8개, 특성은 2개다. top 으로 자르되 없는 것을 만들지 않는다.

    linked_name 을 같이 준다. 화면이 그 이름을 눌러 도감으로 건너뛰려면
    우리 DB 의 키가 필요한데, 저쪽 표기(Focus Sash)로는 못 찾는다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        WITH latest AS (
            SELECT id, snapshot_date, season, usage_rank
            FROM usage_snapshots
            WHERE pokemon_name = %s AND format = %s
            ORDER BY snapshot_date DESC, id DESC
            LIMIT 1
        )
        SELECT r.category, r.rank, r.name, r.linked_name, r.percent,
               r.stat_up, r.stat_down,
               r.hp_points, r.attack_points, r.defense_points,
               r.sp_atk_points, r.sp_def_points, r.speed_points,
               l.snapshot_date, l.season, l.usage_rank,
               -- 화면에 그림을 붙이는 데 쓴다. 기술은 타입 배지, 팀원은
               -- 아이콘이라 각자 다른 표에서 온다. linked_name 을 굳혀
               -- 둔 덕에 조인 한 번으로 끝난다.
               m.type AS move_type,
               tp.id  AS teammate_id
        FROM usage_rows r
        JOIN latest l ON l.id = r.snapshot_id
        LEFT JOIN moves    m  ON r.category = 'move'     AND m.name  = r.linked_name
        LEFT JOIN pokemons tp ON r.category = 'teammate' AND tp.name = r.linked_name
        WHERE r.rank <= %s
        ORDER BY r.category, r.rank
        """,
        (pokemon_name, fmt, top),
    )
    return rows(cur)


def fetch_rank_delta(conn, fmt="Singles", days=7):
    """{저쪽 이름: {순위, 변화}}. 변화는 오른 만큼 양수.

    3위였다가 1위가 되면 +2 다. 순위 숫자는 줄었지만 사람이 읽을 때는
    "두 계단 올랐다" 이므로 부호를 뒤집어 둔다 — 화면에서 다시 뒤집게
    하면 한쪽은 반드시 틀린다.

    ── 왜 직전 스냅샷과 안 견주나 ──
      저쪽이 매일 갱신하지 않는다. 실제로 07-30 과 08-04 는 235마리 순위가
      한 마리도 안 달랐다. 직전과만 견주면 화면이 늘 "변화 없음" 이 되어
      쓸모가 없다.

      대신 days 일 전과 견준다. 16일을 통틀어 보면 235마리 중 225마리의
      순위가 움직였다 — 그 정도 간격이어야 신호가 보인다.

    비교할 앞날이 없으면 delta 가 None 이다. 자료가 days 일보다 짧거나
    새로 올라온 포켓몬이 그렇다.
    """
    cur = conn.cursor()
    cur.execute(
        """
        WITH latest AS (
            SELECT max(snapshot_date) AS d FROM usage_snapshots
            WHERE format = %(fmt)s AND usage_rank IS NOT NULL
        ),
        base AS (
            -- days 일 전에 가장 가까운 스냅샷. 그날이 없으면 그 앞의 것.
            SELECT max(snapshot_date) AS d FROM usage_snapshots
            WHERE format = %(fmt)s AND usage_rank IS NOT NULL
              AND snapshot_date <= (SELECT d FROM latest) - %(days)s::int
        )
        SELECT now.battle_name, now.pokemon_name,
               now.usage_rank, was.usage_rank - now.usage_rank AS delta,
               now.snapshot_date, was.snapshot_date AS compared_to
        FROM usage_snapshots now
        LEFT JOIN usage_snapshots was
               ON was.battle_name = now.battle_name
              AND was.format = now.format
              AND was.snapshot_date = (SELECT d FROM base)
        WHERE now.format = %(fmt)s
          AND now.snapshot_date = (SELECT d FROM latest)
        """,
        {"fmt": fmt, "days": days},
    )
    return {r["battle_name"]: r for r in rows(cur)}
