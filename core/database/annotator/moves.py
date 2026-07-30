"""기술 플래그를 브라우저에서 확인·수정한다.

    cd database
    python annotator/moves.py

브라우저가 자동으로 열린다. 안 열리면 http://localhost:8765 로 접속.

── 왜 psql 대신 이걸 쓰나 ──
  플래그는 498개 × 6칸이다. UPDATE 문으로 치면 오타 한 번에 엉뚱한 기술이
  바뀌고, 무엇을 확인했는지 기억할 방법도 없다. 화면에서는 한 번에 40행씩
  보면서 틀린 것만 고치고, 확인한 것은 표시가 남는다.

── 저장은 두 군데에 동시에 ──
  1. DB의 moves 테이블            즉시 반영. 계산기가 바로 쓴다
  2. overrides/move_flags.json    재구축해도 살아남는다

  DB에만 쓰면 python main.py 한 번에 전부 사라진다. JSON에만 쓰면 다시
  구축하기 전까지 반영이 안 된다. 그래서 둘 다 쓴다.

── 무엇을 확인해야 하나 ──
  12개 플래그 중 9개는 PokeAPI CSV 에서 온 확정값이라 볼 필요가 거의 없다.
  손이 필요한 건 CSV 가 채워 주지 않는 세 개다.

    바람 · 베기   9세대 신규 플래그. CSV 에 아예 없다
    압박         나무위키 분류. 공식 flag 에 대응이 없다

  그리고 move_id 826 이후 신기술 55개는 CSV 에 없어서 12개 전부 추측이다.
  (dire-claw, gigaton-hammer, matcha-gotcha, psychic-noise ...)

── 작업 요령: 계열 칩 ──
  상단의 계열 칩(접촉·펀치·물기 …)을 누르면 그 계열만 남는다.
  이때 '켜진 것'과 '후보'를 같이 띄우는 것이 핵심이다.

    켜진 것   그 플래그가 이미 TRUE
    후보      아직 FALSE 지만 이름에 관련 단어가 있는 기술 (주황 테두리)

  빠뜨린 것은 켜진 것만 봐서는 찾을 수 없다. '베기' 칩을 누르면
  slash/cut/blade/claw/axe/edge/sword 가 든 기술이 전부 올라오므로,
  그중 진짜 베기인 것만 체크하면 끝난다.

  '후보만' 모드로 두면 아직 안 켜진 것만 남아서 더 빠르다.

── 판단에 참고가 되는 값 ──
    우선도  0은 빈칸이라 선공기·후공기만 눈에 띈다
    타수    연속기는 총알 플래그일 가능성이 높다 (2-5 같은 것)
    대상    '자신'인 기술은 접촉이 될 수 없다
"""

# _common 이 database/ 를 sys.path 에 넣는다. 아래 import 보다 먼저여야 한다.
from _common import Spec, serve  # noqa: I001

import db
import move_flags
import overrides

OVERRIDE_KEY = "move_flags"
FLAGS = move_flags.FLAGS
LABELS = move_flags.FLAG_LABELS

INFO_COLUMNS = [
    ("name", "기술"),
    ("ko_name", "한국어"),
    ("type", "타입"),
    ("category", "분류"),
    ("power", "위력", "num"),
    ("accuracy", "명중", "num"),
    ("priority", "우선도", "num"),
    ("hits", "타수", "num"),
    ("target", "대상"),
]

# DB에서 읽되 화면 열로는 안 쓰는 것
EXTRA_COLUMNS = ["min_hits", "max_hits", "effect"]

# PokeAPI 대상 이름을 짧게. 없는 값은 원문 그대로 보여준다.
TARGET_LABELS = {
    "selected-pokemon": "상대",
    "user": "자신",
    "all-opponents": "상대전체",
    "all-other-pokemon": "자신외전체",
    "all-pokemon": "전체",
    "entire-field": "필드",
    "users-field": "자기필드",
    "opponents-field": "상대필드",
    "random-opponent": "랜덤",
    "user-and-allies": "자기편",
    "all-allies": "아군전체",
    "ally": "아군",
    "user-or-ally": "자신/아군",
    "fainting-pokemon": "쓰러진포켓몬",
}


# ─────────────────────────────────────────────────────────────
# 계열별 필터
#
# 상단 칩을 누르면 그 계열의 기술만 남는다. 이때 두 종류를 같이 띄운다.
#   켜진 것   그 플래그가 이미 TRUE 인 기술
#   후보      아직 FALSE 지만 이름에 아래 힌트가 들어 있는 기술
#
# 후보를 같이 보여주는 게 핵심이다. 빠뜨린 것은 "켜진 것"만 봐서는 절대
# 찾을 수 없다. 후보 칸에는 주황 테두리가 붙는다.
#
# 힌트는 넉넉하게 넣었다. 관계없는 게 섞여도 눈으로 걸러내면 되고,
# 좁게 잡아서 놓치는 게 더 나쁘다.
# ─────────────────────────────────────────────────────────────

GROUP_HINTS = {
    "is_contact": [],          # 물리 기술 대부분이라 이름 힌트가 의미 없다
    "is_punch": ["punch", "fist", "mash", "bash"],
    "is_bite": ["bite", "fang", "crunch", "chomp", "jaw"],
    "is_sound": ["voice", "song", "roar", "sing", "screech", "buzz",
                 "noise", "howl", "snarl", "boom", "aria", "chatter",
                 "whistle", "sonic", "bell", "round", "uproar", "snore",
                 "scales", "soul", "yell", "cheer", "shot", "spell"],
    "is_powder": ["powder", "spore", "dust", "pollen"],
    "is_bullet": ["ball", "bomb", "blast", "cannon", "shot", "seed",
                  "sphere", "missile", "beam", "puff"],
    "is_wind": ["wind", "storm", "gust", "blizzard", "twister",
                "hurricane", "gale", "tornado", "breeze", "sand"],
    "is_slicing": ["slash", "cut", "blade", "claw", "axe", "edge",
                   "sword", "cleave", "scissor", "razor", "sever",
                   "ace", "leaf"],
    "is_dance": ["dance", "step", "waltz"],
    "is_pulse": ["pulse", "wave", "sphere", "aura"],
    "is_gravity": ["fly", "bounce", "jump", "rise", "sky", "float",
                   "press", "drop"],
    "is_press": ["slam", "stomp", "press", "roller", "crash", "rush",
                 "bomber", "stamp", "dive", "body"],
}

GROUPS = [
    {"field": f, "label": LABELS[f], "hints": GROUP_HINTS[f]}
    for f in FLAGS
]


def fetch():
    """DB에서 기술 목록을 읽고 보기 좋게 다듬는다."""
    conn = db.connect()
    cur = conn.cursor()
    # hits 는 min/max 를 합쳐 만드는 가상 열이라 SELECT 목록에서 뺀다
    cols = [c[0] for c in INFO_COLUMNS if c[0] != "hits"] \
        + EXTRA_COLUMNS + list(FLAGS) + ["reviewed"]
    cur.execute(f"SELECT {', '.join(cols)} FROM moves ORDER BY id")
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    for r in rows:
        # 0은 빈칸으로 둔다. 그러면 선공기·후공기만 눈에 띈다
        r["priority"] = f"{r['priority']:+d}" if r["priority"] else None
        r["target"] = TARGET_LABELS.get(r["target"], r["target"])
        r["hits"] = fmt_hits(r["min_hits"], r["max_hits"])
    return rows


def fmt_hits(lo, hi):
    """연속기 타수. 단타는 빈칸. 총알 플래그를 볼 때 참고가 된다."""
    if not lo and not hi:
        return None
    if lo == hi:
        return str(lo)
    return f"{lo}-{hi}"


def save(name, flags, reviewed):
    """DB와 override JSON에 동시에 쓴다. 기본값과 다른 부분을 돌려준다."""
    conn = db.connect()
    cur = conn.cursor()
    sets = ", ".join(f"{f} = %s" for f in FLAGS)
    cur.execute(
        f"UPDATE moves SET {sets}, reviewed = %s WHERE name = %s "
        f"RETURNING id, category",
        [flags[f] for f in FLAGS] + [reviewed, name],
    )
    row = cur.fetchone()
    conn.commit()
    conn.close()
    if row is None:
        raise KeyError(f"{name} 이라는 기술이 DB에 없습니다")

    # 기본값(CSV 또는 추측)과 다른 필드만 JSON에 남긴다. CSV 가 갱신되거나
    # move_flags.py 의 규칙이 좋아지면 항목이 저절로 줄어든다.
    data = overrides.load(OVERRIDE_KEY, refresh=True)
    base, _ = move_flags.resolve(row[0], name, row[1])
    diff = {f: flags[f] for f in FLAGS if flags[f] != base[f]}

    if diff:
        data["values"][name] = diff
    else:
        data["values"].pop(name, None)
    if reviewed:
        data["reviewed"] = sorted(set(data["reviewed"]) | {name})
    else:
        data["reviewed"] = [n for n in data["reviewed"] if n != name]
    overrides.save(OVERRIDE_KEY, data)
    return diff


def check_schema():
    """플래그 컬럼이 없으면 안내하고 끝낸다."""
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'moves'")
    have = {r[0] for r in cur.fetchall()}
    conn.close()
    missing = [f for f in FLAGS + ["reviewed"] if f not in have]
    if missing:
        print("moves 테이블에 플래그 컬럼이 없습니다:", ", ".join(missing))
        print("\nREADME §6 으로 DB를 지우고 python main.py 를 다시 돌리세요.")
        raise SystemExit(1)


def summary():
    data = overrides.load(OVERRIDE_KEY, refresh=True)
    print(f"확인 {len(data['reviewed'])}개 / "
          f"추측과 다른 항목 {len(data['values'])}개")
    print(f"저장 위치: {overrides.path(OVERRIDE_KEY)}")


SPEC = Spec(
    title="기술 플래그 확인",
    info_columns=INFO_COLUMNS,
    check_columns=[(f, LABELS[f]) for f in FLAGS],
    fetch=fetch,
    save=save,
    key_field="name",
    search_fields=("name", "ko_name", "type", "category", "target"),
    detail_field="effect",
    port=8765,
    summary=summary,
    labels=LABELS,
    groups=GROUPS,
)


def main():
    check_schema()
    serve(SPEC)


if __name__ == "__main__":
    main()
