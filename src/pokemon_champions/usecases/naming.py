"""이름 해석 — 한국어든 영문 슬러그든 받아 DB 의 열쇠로 바꾼다.

── 왜 양방향인가 ──
  화면은 한국어로 말하고, 모델은 한국어 질문을 그대로 옮겨 적기도 하고
  친절하게 영문으로 바꿔 주기도 한다. 채용률 데이터는 아예 영문으로
  들어온다. 어느 쪽이 오든 걸려야 한다 — 둘 중 하나만 받으면 나머지
  절반이 "그런 포켓몬은 없습니다" 가 된다.

── 캐시는 모듈에, 커넥션은 인자로 ──
  도감 목록은 배틀 중에 바뀌지 않는 참조 데이터라 한 번 읽어 계속
  돌려쓴다. 그건 모듈에 들고 있어도 된다 — 두 스레드가 동시에 채워도
  같은 값이 들어가고, 읽는 쪽은 dict 조회 하나다.

  커넥션은 다르다. psycopg2 커넥션은 스레드 간 공유가 안전하지 않다.
  그래서 여기서 열지 않고 부르는 쪽이 넘긴다 — db/connection.py 첫머리에
  적힌 "진입점에서 한 번 열고 인자로 내려보낸다" 가 그 규칙이다.
"""

from ..db.repositories import (ability_repo, item_repo, lookup_repo, move_repo,
                               pokemon_repo, rules_repo)
from ..services import usage
from ..text import normalize

_LISTS = {
    "pokemons": pokemon_repo.fetch_list,
    "moves": move_repo.fetch_list,
    "items": item_repo.fetch_list,
    "abilities": ability_repo.fetch_list,
}

# 참조 데이터 캐시. clear() 로 비운다.
_rows = {}
_names = {}
_types = None


def clear():
    """캐시를 비운다. 테스트와 종료 때 쓴다."""
    global _types
    _rows.clear()
    _names.clear()
    _types = None


def rows_of(conn, table):
    """도감 목록을 {영문 이름: 행} 으로. 한 번만 읽는다.

    이름 하나마다 쿼리를 내면 기술 여덟 개짜리 답에 쿼리가 여덟 번 나간다.
    가장 큰 moves 가 498줄이라 전부 들고 있어도 문제가 없다 — 도감 화면도
    같은 함수로 같은 목록을 통째로 받는다.
    """
    if table not in _rows:
        _rows[table] = {r["name"]: r for r in _LISTS[table](conn)}
    return _rows[table]


def _maps(conn, table):
    """{영문: 한국어} 와 {한국어: 영문} 두 벌."""
    if table not in _names:
        if table == "pokemon_natures":
            # 성격만 도감 목록이 없다. 그 테이블은 이름이 ENUM 이라 name
            # 컬럼이 아예 없어서, en_name 을 읽는 lookup_repo 를 쓴다.
            pairs = list(lookup_repo.fetch_ko_map(conn, table).items())
        else:
            pairs = [(r["name"], r["ko_name"])
                     for r in rows_of(conn, table).values()]
        _names[table] = {
            "ko_by_en": dict(pairs),
            "en_by_ko": {normalize(ko): en for en, ko in pairs if ko},
        }
    return _names[table]


def resolve(conn, table, name):
    """한국어 이름이든 영문 슬러그든 받아 영문 name 을 돌려준다.

    ko_name 을 먼저 본다. 한글과 영문은 문자 집합이 달라 실제로 겹칠 일이
    없지만, 순서를 정해두지 않으면 나중에 겹치는 항목이 생겼을 때 조용히
    갈린다.

    영문은 슬러그로 한 번 더 본다. 사람 읽는 표기(Focus Sash)로 오는 일이
    잦은데 우리 DB 는 focus-sash 다. 채용률 쪽 이름을 맞출 때 쓰는 규칙과
    같은 것을 쓴다 — 두 벌이 되면 한쪽만 고치게 된다.
    """
    if not name:
        return None
    m = _maps(conn, table)
    key = normalize(str(name))
    hit = m["en_by_ko"].get(key)
    if hit:
        return hit
    if key in m["ko_by_en"]:
        return key
    slug = usage.slugify(key)
    return slug if slug in m["ko_by_en"] else None


def ko(conn, table, en):
    """영문 name -> 한국어 이름. 아직 없으면 None."""
    return _maps(conn, table)["ko_by_en"].get(en) if en else None


def to_ko(conn, table, value):
    """받은 이름을 DB 조회에 쓸 한국어로. 못 바꾸면 받은 것 그대로.

    그대로 넘기는 이유는 team.validate_spec 이 이미 "그 포켓몬의 특성이
    아닙니다" 를 사람이 읽을 문장으로 돌려주기 때문이다. 여기서 따로
    막으면 같은 말을 두 곳에서 하게 되고, 문구가 갈린다.
    """
    if not value:
        return None
    return ko(conn, table, resolve(conn, table, value)) or normalize(str(value))


def types_of(conn, en):
    """영문 이름 -> 타입 1~2개.

    pokemon_repo.fetch_meta 를 안 쓰는 이유는 그쪽이 ko_name 을 열쇠로
    써서, 한국어 이름이 아직 없는 폼에는 쓸 수 없기 때문이다.
    """
    row = rows_of(conn, "pokemons")[en]
    return tuple(t for t in (row["type1"], row["type2"]) if t)


def type_names(conn, language="ko"):
    """{영문 타입: 그 언어 표기} 18줄 — pokemon_type_names.

    ── 왜 결과에 안 싣고 프롬프트에 싣나 ──
      다른 이름은 도구 결과에 ko_name 을 나란히 실어 보내지만, 타입만은
      그럴 자리가 없다. type_matchup 의 damage_taken 은 키가 곧 배수라
      열여덟 타입이 값 쪽에 슬러그로 늘어서고, 거기에 한국어를 짝지어
      넣으면 표가 배로 불어난다.

      열여덟 개뿐이고 배틀 내내 안 바뀌므로 시스템 프롬프트에 한 번
      박아두는 편이 싸다. 목적은 같다 — 모델이 fire 를 "화염" 이라고
      옮기는 것을 막는 것.
    """
    global _types
    if _types is None or language != "ko":
        got = rules_repo.fetch_type_names(conn, language)
        if language != "ko":
            return got
        _types = got
    return _types
