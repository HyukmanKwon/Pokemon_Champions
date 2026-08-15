"""생성기 열두 개가 함께 쓰는 조각들.

여기 있는 것은 전부 "여러 생성기가 글자 그대로 같게 적고 있던 것" 이다.
한 곳에서만 쓰는 것은 그 파일에 둔다 — 여기로 올리면 그 파일을 읽는
사람이 규칙을 찾아 두 파일을 오가야 한다.
"""

import requests

from . import overrides


def get_json(url):
    """GET 후 JSON을 돌려준다. 200이 아니면 None."""
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        return None
    return resp.json()


def endpoint(base):
    """이름 하나를 받아 그 자원의 JSON 을 돌려주는 함수를 만든다.

        fetch_move = endpoint("https://pokeapi.co/api/v2/move")
        fetch_move("fire-punch")        # -> dict 또는 None

    기술·특성·도구·포켓몬 네 생성기가 똑같이 세 줄짜리 fetch_X 를 적고
    있었다. 함수로 남기는 이유는 collect() 가 이걸 인자로 받기 때문이다.
    """
    def fetch(name):
        return get_json(f"{base}/{name}")
    return fetch


def pick_korean(entries, key_text="name"):
    """names 리스트에서 한국어(ko) 항목을 고른다. 없으면 None."""
    for e in entries:
        if e["language"]["name"] == "ko":
            return e[key_text]
    return None


def pick_korean_flavor(entries, key="flavor_text"):
    """flavor_text_entries에서 한국어 설명을 고른다(가장 마지막=최신 우선).

    본문 키가 자료마다 다르다.
      - move, ability : "flavor_text"
      - item          : "text"
    """
    ko = [e[key] for e in entries if e["language"]["name"] == "ko"]
    if not ko:
        return None
    # 줄바꿈·제어문자 정리
    return ko[-1].replace("\n", " ").replace("\f", " ").strip()


def pick_english_effect(entries):
    """effect_entries에서 영어 효과 설명(short_effect)을 고른다."""
    for e in entries:
        if e["language"]["name"] == "en":
            return e.get("short_effect", "").replace("\n", " ").strip()
    return None


def korean(data, override_key, flavor_key="flavor_text"):
    """한국어 이름·설명을 뽑고 override 를 덮어씌운다. -> dict

    기술·특성·도구 셋이 같은 다섯 줄을 적고 있었다. PokeAPI 의 한국어는
    옛 세대 번역이거나 아예 없는 경우가 있어서, annotator 로 손본 값이
    항상 마지막에 온다.

        python -m scripts.etl.annotator.ko_names moves

    flavor_key 가 인자인 이유는 본문 키가 자료마다 다르기 때문이다 —
    기술·특성은 "flavor_text", 도구는 "text".
    """
    ko = {
        "ko_name": pick_korean(data["names"]),
        "description": pick_korean_flavor(data["flavor_text_entries"],
                                          key=flavor_key),
    }
    overrides.apply(override_key, data["name"], ko)
    return ko


def render(ddl, table, columns, rows):
    """DDL + INSERT 를 합쳐 SQL 파일 전문을 만든다.

    rows 는 cur.mogrify 로 만든 "    (...)" 문자열들의 리스트.
    """
    body = f"INSERT INTO {table}\n    ({', '.join(columns)})\nVALUES\n"
    body += ",\n".join(rows) + ";\n"
    return ddl + "\n" + body


def mogrify_rows(cur, values_list, width):
    """값 튜플 리스트를 SQL 리터럴 행 문자열 리스트로 바꾼다."""
    placeholder = "    (" + ", ".join(["%s"] * width) + ")"
    return [cur.mogrify(placeholder, v).decode("utf-8") for v in values_list]


def sql_of(cur, ddl, table, columns, values):
    """값 튜플 목록을 DDL + INSERT 한 덩어리로. 생성기 build() 의 마지막 줄.

    열두 생성기가 전부 이 한 줄로 끝난다. render 와 mogrify_rows 를 따로
    부르면 len(columns) 를 두 번 적게 되고, 그 둘이 어긋나면 mogrify 가
    "not enough arguments" 로 터진다 — 칼럼을 하나 늘렸을 때 실제로 겪는
    실수다. 여기서 한 번만 적는다.
    """
    return render(ddl, table, columns, mogrify_rows(cur, values, len(columns)))


def to_values(rows, columns):
    """parse 가 돌려준 dict 목록에서 COLUMNS 순서의 튜플 목록을 뽑는다.

    dict 에 COLUMNS 에 없는 키가 있어도 된다. get_moves 의 _source 처럼
    통계에만 쓰고 DB 에는 안 넣는 값이 그렇다.
    """
    return [tuple(r[c] for c in columns) for r in rows]


def collect(names, fetch, parse):
    """이름 목록을 하나씩 받아 파싱한 dict 목록으로 만든다.

    포켓몬·기술·특성·도구 넷이 같은 모양이다 — 받고, 못 받으면 건너뛰고,
    파싱하고, 한국어 이름이 비었으면 세어 두고, 진행 상황을 한 줄씩 찍는다.

    실패와 '한국어 이름 없음' 은 돌려주지 않고 여기서 세어 찍기만 한다.
    부르는 쪽이 그 값으로 하는 일이 없기 때문이다 — 실패가 0이 아닐 때
    이 SQL 을 쓸지 말지는 사람이 화면을 보고 정한다. (README §4)

    parse 는 dict 를 돌려줘야 하고 그 안에 name·ko_name 이 있어야 한다.
    값 튜플이 아니라 dict 를 돌려주는 이유는, 기술처럼 한 응답에서 두
    테이블이 나오는 생성기가 COLUMNS 밖의 값도 같이 들고 가야 하기
    때문이다. 튜플로 만드는 것은 to_values 가 한다.

    ── 여기 안 들어오는 것 ──
      get_pokemon_moves 는 이름 하나가 행 수십 개가 되고 ko_name 이 없다.
      끼워 넣으려면 이 함수에 분기가 둘 생기는데, 그러면 네 생성기가
      공유하는 뜻이 흐려진다. 그쪽은 자기 루프를 그대로 둔다.
    """
    rows, no_ko, failed = [], [], []
    for name in names:
        data = fetch(name)
        if data is None:
            failed.append(name)
            print(f"{name} - failed")
            continue
        row = parse(data)
        if row["ko_name"] is None:
            no_ko.append(row["name"])
        rows.append(row)
        print(f"{row['name']} -> {row['ko_name']}")

    print(f"\n수집 {len(rows)}개")
    print(f"한국어 이름 없음: {len(no_ko)}개 - {no_ko}")
    print(f"실패: {len(failed)}개 - {failed}")
    return rows


def literal_build(conn, ddl, table, columns, values, echo=None):
    """코드에 적힌 행 목록을 그대로 SQL 로. API 를 안 부르는 생성기의 build().

    타입 상성·성격·날씨·필드·랭크·상태이상 여섯 개가 하는 일이 같다 — 파일에
    적어둔 튜플 목록을 굳혀 SQL 로 만든다. 그 두 줄을 여섯 벌 두는 대신
    여기 한 벌 둔다. 각 파일에는 포켓몬 규칙만 남는다.

    echo 는 한 행을 어떻게 찍을지 정하는 함수다. 생성기마다 보고 싶은 칸이
    달라서(성격은 이름만, 날씨는 이름+한글) 형식까지 통일하지는 않는다.
    None 이면 아무것도 안 찍는다.
    """
    if echo is not None:
        for v in values:
            print(echo(v))
    return sql_of(conn.cursor(), ddl, table, columns, values)
