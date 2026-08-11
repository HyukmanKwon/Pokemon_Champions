# Pokemon Champions

포켓몬 챔피언스(레귤레이션 M-B) 대전 도우미. PokeAPI 데이터를 PostgreSQL에 쌓고,
그 위에 도감 · 엔트리 · 데미지 계산기를 올린 뒤, 마지막에 그것들을 툴로 호출하는
LLM 도우미를 붙이는 것이 목표다.

레귤레이션 M-B의 특수 규칙은 레벨 50 · 개체값 31 고정, 노력치 대신 **SP**(총 66,
능력치당 최대 32), 성격 21종이다. 관련 상수는 전부
[`src/pokemon_champions/config.py`](src/pokemon_champions/config.py)에 있다.

---

## 1. 빠른 시작

```bash
pip install -e ".[web,dev]"      # 한 번만. 어느 폴더에서 실행하든 import가 통한다
createdb pokemon
python -m scripts.etl.build      # PokeAPI -> SQL -> DB (약 1,900회 호출)

python main.py                   # 터미널에서 내 팀 보기/고치기
python web.py                    # http://127.0.0.1:8000
pytest                           # DB 없이 도는 계산 테스트
```

로컬 LLM 도우미는 Ollama 가 따로 떠 있어야 한다.

```bash
ollama serve                     # 한 번만, 별도 터미널
ollama pull qwen3.5:9b

python -m scripts.chat --tools   # 어떤 도구를 불렀는지 보면서 대화
python -m scripts.chat "메가갸라도스 지진이 한카리아스를 몇 방에 보내?"
```

접속 정보는 환경변수로 바꾼다. `.env.example` 참고.

DB 구축 과정은 [`scripts/etl/README.md`](scripts/etl/README.md)에 따로 정리돼 있다.

---

## 2. 폴더 구조

```
Pokemon_Champions/
├── main.py                     CLI 진입점 (cli.main() 호출뿐)
├── web.py                      웹 진입점 (uvicorn 설정뿐)
├── pyproject.toml              패키지 정의 · 의존성
├── .env.example
│
├── data/                       코드가 아닌 것. 전부 여기
│   ├── sql/                    DB 를 만드는 SQL 12개       (git 제외)
│   ├── overrides/              사람이 확정한 값 4개         (git 커밋)
│   ├── cache/                                            (git 제외)
│   │   ├── move_flag_map.csv   PokeAPI 기술 플래그 원본
│   │   └── usage/              배틀 데이터(채용률) 응답
│   ├── images/                 스프라이트·타입 아이콘 캐시  (git 제외)
│   └── my_team.json            내 엔트리 6마리             (git 제외)
│
├── scripts/                    손으로 돌리는 것. 런타임 아님
│   ├── chat.py                 LLM 도우미와 대화
│   ├── check_damage.py         계산 결과를 알려진 값과 대조
│   ├── check_modifiers.py      보정 표를 대조
│   ├── check_usage.py          채용률을 대조
│   ├── fetch_assets.py         스프라이트 내려받기
│   │
│   └── etl/                    PokeAPI -> SQL -> DB
│       ├── build.py            빈 DB 에 전체 구축 (약 1,900회 호출)
│       ├── dump_sql.py         반대 방향 — 지금 DB 를 data/sql/ 로
│       ├── schema.py           모든 DDL의 단일 출처
│       ├── get_*.py            단계별 생성기 12개
│       ├── sync_moves.py       기술만 추가 (전체 재구축 없이)
│       ├── migrate_roster.py   로스터 증감만 반영
│       ├── pin_ko_names.py     DB 의 한국어 표기를 override 로 고정
│       ├── check_moves.py      외부 목록과 기술 대조
│       ├── overrides.py        사람이 확정한 값 읽기/쓰기
│       ├── move_flags.py       기술 플래그 (CSV + 이름 규칙)
│       ├── translation.py      이름 한↔영, 폼 이름 조립
│       ├── parse_utils.py      PokeAPI 파싱 + SQL 조립
│       ├── paths.py            data/ 경로 (config.py 재사용)
│       ├── annotator/          브라우저로 손수 확정하는 도구
│       └── README.md
│
├── src/pokemon_champions/      실제로 배포되는 패키지
│   ├── config.py               레귤레이션 상수 · 경로 · 접속 정보
│   ├── text.py                 NFC 정규화
│   ├── assets.py               스프라이트 다운로드 캐시
│   ├── battledata.py           배틀 데이터 받아오기 + 캐시
│   │
│   ├── agent/                  LLM 도우미. 모델은 도구만 고르고 계산은 안 한다
│   │   ├── tools.py            도구 13개 + 스키마 (repositories/services 호출)
│   │   └── runner.py           Ollama 도구 호출 루프
│   │
│   ├── domain/                 "포켓몬이란 무엇인가"만 안다
│   │   ├── stats.py            Stats — 능력치 6칸
│   │   └── pokemon.py          Pokemon
│   │
│   ├── db/
│   │   ├── connection.py       connect() — 커넥션을 여는 유일한 지점
│   │   └── repositories/       SQL이 존재해도 되는 유일한 곳
│   │       ├── pokemon_repo.py     fetch_base, fetch_meta, fetch_abilities …
│   │       ├── move_repo.py        fetch_type, fetch_learnable …
│   │       ├── ability_repo.py     fetch_effect …
│   │       ├── item_repo.py        fetch_usable …
│   │       ├── mega_repo.py        fetch_form, fetch_stones
│   │       ├── nature_repo.py      fetch_modifiers, fetch_all
│   │       ├── rules_repo.py       타입상성·날씨·필드·상태이상 참조표
│   │       ├── lookup_repo.py      영문 -> 한국어 대응표
│   │       └── _rows.py            커서 -> dict
│   │
│   ├── services/               비즈니스 로직
│   │   ├── stats.py            [순수] make_sp, calc_stats
│   │   ├── damage.py           [순수] calc_damage, analyze_ko,
│   │   │                              power_index, bulk_index
│   │   ├── modifiers.py        [순수] 특성·도구 보정을 4096 정수로
│   │   ├── team.py             [조립] 내 엔트리 로드·검증·빌드
│   │   ├── usage.py            [조립] 채용률을 DB 의 한국어와 잇기
│   │   └── opponent.py         상대 엔트리 (아직 비어 있다 — §5)
│   │
│   └── interfaces/             print/input/HTTP는 여기서만
│       ├── cli.py
│       └── api/
│           ├── app.py          FastAPI
│           └── static/index.html
│
└── tests/                      DB 없이 도는 계산 테스트 64개
    ├── conftest.py             overrides 폴더 격리 (autouse)
    ├── test_damage.py          40개
    ├── test_stats.py           10개
    └── test_team.py            14개
```

`data/sql/` 은 `build.py` 가 만들지만, DB 는 빌드 이후로도 애노테이터 ·
`sync_moves` · `migrate_roster` 로 계속 움직인다. 그래서 파일이 DB 보다 뒤처지는데,
`dump_sql.py` 가 그 반대 방향을 맡는다 — 지금 DB 를 그대로 받아 적는다.

---

## 3. 지켜야 할 규칙 4개

구조는 취향이 아니라 **변경에 대한 방어**다. 각 규칙마다 무엇을 막는지 적어 둔다.

### 규칙 1 — 의존 방향은 한쪽으로만 흐른다

```
interfaces  ──▶  services  ──▶  db.repositories  ──▶  db.connection
                    │
                    ▼
                 domain  (프로젝트 내 무엇도 import 하지 않는다)
```

역방향 import는 없다. `services`가 `interfaces`를 부르는 순간 둘 중 어느 것도 혼자
테스트할 수 없고 혼자 재사용할 수도 없다. 사실상 한 파일이 된다.

더 실질적인 이유가 있다. 이 프로젝트는 개인 배포용 앱과 웹 서비스를 **둘 다** 목표로
한다. 단방향이면 `services/`를 그대로 두고 `interfaces/` 아래에 하나 더 만들면 끝난다.
양방향이면 웹을 붙이는 순간 계산 로직까지 다시 써야 한다. 지금의 분리가 나중에 절약할
작업의 정확한 크기다.

### 규칙 2 — SQL은 `db/repositories/` 밖으로 나오지 않는다

세 가지를 막는다.

- **테스트** — 함수 안에 `SELECT`가 있으면 PostgreSQL이 떠 있고 데이터까지 들어 있어야
  돌릴 수 있다. 결과가 틀렸을 때 계산이 틀린 건지 데이터가 틀린 건지 구분되지 않는다.
- **성능** — 로직 안에 조회가 숨어 있으면 반복문 안에서 도는 것도 안 보인다. 6마리 ×
  4기술 × 상대 6마리를 돌리면 쿼리가 수백 번 나간다. 조회를 밖으로 빼면 "먼저 다
  가져오고 계산은 메모리에서"가 자연스러워진다.
- **스키마 변경** — 컬럼명을 바꿀 때 grep할 곳이 폴더 하나다.

### 규칙 3 — 계산은 순수 함수로 쓴다

```python
# services/stats.py — conn이 없다
def calc_stats(base, sp, nature) -> Stats

# services/damage.py — 조회 결과를 인자로 받는다
def calc_damage(attacker, defender, move, ctx=None, chart=None) -> DamageRange
```

같은 입력이면 항상 같은 출력. DB도 안 읽고 파일도 안 쓴다. 이유가 셋이다.

1. **검증 가능성.** 데미지 공식은 실제 게임 값과 대조해서 맞춰야 한다. `@smogon/calc`를
   쓰지 않고 직접 구현하기로 했으니, 알려진 케이스를 박아둔 테스트 묶음이 곧 계산기의
   신뢰도 그 자체다. 순수 함수면 공식을 고칠 때마다 1초 만에 전부 재검증된다.
2. **LLM 툴로서.** "LLM은 계산하지 않고 라우팅만 한다"는 원칙을 코드로 강제한다. 입력이
   전부 인자로 드러나 있으면 툴 스키마는 시그니처를 옮겨 적는 수준이 된다. 반대로 함수가
   안에서 DB를 뒤지면, 이름을 잘못 넘겼을 때 조회 실패인지 계산 실패인지 알 수 없고
   에러 메시지도 LLM에게 쓸모없어진다.
3. **재현성.** "이 계산 왜 이렇게 나왔냐"는 질문에, 로그에 남긴 인자를 다시 넣으면 된다.

날씨 · 필드 · 랭크 · 상태이상처럼 **계산 도중에 값이 변하는 것**은 `BattleContext` 하나로
묶는다. 인자로 하나씩 늘리면 새 특성 하나 지원할 때마다 모든 호출부를 고쳐야 한다.
확정 N방 분석은 본질적으로 "context를 한 턴씩 바꾸며 같은 함수를 반복 호출"이라,
상태가 한 덩어리여야 깔끔하게 표현된다. 스태미나 같은 특성이 정확히 이 모양이다.

### 규칙 4 — `scripts/`는 `src/`를 import해도 되지만, 반대는 절대 안 된다

ETL은 몇 달에 한 번 손으로 돌리는 코드고 `src/`는 요청마다 도는 코드다. **생명주기가
다르다.** 섞으면 앱 배포판에 PokeAPI 파싱 코드가 딸려 들어가고, PokeAPI 응답 형식이
바뀔 때 앱까지 같이 깨진다.

`pyproject.toml`의 `where = ["src"]`가 이걸 물리적으로 보장한다. `scripts/`는 설치되지
않는다.

---

## 4. 개별 결정의 이유

### `src/` 레이아웃과 `pip install -e .`

Python은 "현재 실행 위치"를 기준으로 모듈을 찾는다. 파일이 평평하게 놓여 있으면
`python get_moves.py`는 되는데 `python scripts/get_moves.py`는 ImportError가 난다.
그래서 초보 프로젝트에 `sys.path.append('..')`가 생기는데, 이게 붙는 순간 **실행 위치가
코드의 일부**가 된다. (실제로 옮기기 전 `annotator/_common.py`가 이 조작을 하고 있었다.)

`pip install -e .` 이후에는 어디서 실행하든 `import pokemon_champions`가 통한다. 나중에
앱으로 배포하거나 컨테이너에 올릴 때 이 차이가 결정적이다. `src/`로 한 겹 감싸는 것은
"설치되는 패키지"와 "저장소 루트의 잡동사니"를 물리적으로 못 섞이게 하려는 것이다.

### `domain/`이 아무것도 import하지 않는 이유

`Pokemon`과 `Stats`는 DB에서 왔는지 PokeAPI에서 왔는지 JSON에서 왔는지 모른다.

이게 없으면 테이블 구조가 코드 전체로 새어나간다. `pokemons` 테이블의 컬럼명을 바꿀 때
몇 개 파일을 고쳐야 할지 생각해 보면 된다. domain이 중간에 있으면 repository 한 곳만
고치면 된다.

이미 겪은 문제이기도 하다. PokeAPI의 `data["stats"]`를 인덱스로 접근하면 깨진다는 걸
알고 slot/name 기반 파싱으로 바꿨다. 같은 원리다. **외부 데이터의 모양에 내 코드가
직접 붙으면 외부가 바뀔 때 내가 깨진다.** domain은 그 사이의 완충재다.

### `Pokemon.__str__`을 없앤 이유

한글 폭을 계산해 표를 그리던 코드는 `interfaces/cli.py`의 `format_pokemon()`으로 갔다.
그건 터미널 사정이지 포켓몬의 성질이 아니다. 웹은 같은 `Pokemon` 객체를 JSON으로
내보낸다 — 표현을 도메인 밖에 둬야 둘 다 가능하다.

### `config.py`에 상수를 몰아둔 이유

레벨 50, 개체값 31, SP 총합 66, 능력치당 32 — 전부 **레귤레이션 M-B의 규칙**이지 물리
법칙이 아니다. 흩어져 있으면 다음 레귤레이션에서 66을 몇 군데 고쳐야 하는지 아무도
모른다. 한 파일에 있으면 그 파일이 곧 현재 규칙 명세서가 된다.

`HP_OFFSET = 75`, `STAT_OFFSET = 20`도 마찬가지다. 이 숫자는 레벨과 개체값이 고정이라
미리 접어 둔 값이라는 사실이 주석에 남아 있다.

### `data/`를 코드 밖에 둔 이유

타입 상성표와 성격은 "정적 데이터를 SQL 파일로 배포"하기로 한 것이고, 그 SQL은 코드가
아니라 **데이터**다. 코드 폴더에 있으면 리뷰할 때, 검색할 때, 배포할 때 계속 섞인다.

`data/` 안에서도 커밋 여부가 갈린다.

| 폴더 | git | 이유 |
|---|---|---|
| `overrides/` | 커밋 | 사람이 눈으로 확인해 확정한 값. 다시 만들 수 없다 |
| `sql/` `cache/` `images/` | 제외 | 스크립트가 언제든 다시 만든다 |
| `my_team.json` | 제외 | 개인 데이터 |

내려받은 이미지를 패키지 폴더가 아니라 `data/images/`에 두는 이유도 같다. wheel로
설치하면 패키지 폴더에 쓰기 권한이 없어 깨진다.

### 마이그레이션 폴더를 만들지 않은 이유

일반적으로는 `migrations/`에 번호 붙은 파일을 쌓아 스키마 이력을 남긴다. 이 프로젝트는
다르다. `scripts/etl/schema.py`가 모든 DDL의 단일 출처이고, DB는 언제든 **전체 재구축**이
가능하다. 여기에 마이그레이션을 얹으면 스키마 정의가 두 군데가 되고, 둘이 어긋나는 순간
어느 쪽이 진실인지 알 수 없게 된다.

운영 DB가 생겨서 "데이터를 유지한 채 스키마만 바꿔야" 할 때 그때 도입하면 된다.
지금은 필요 없다.

### 빈 폴더를 만들지 않은 이유

`agent/`(LLM 툴 계층)와 `interfaces/api/routers/`는 처음에 만들지 않았다. 빈 폴더는
거짓말을 한다 — 열었는데 아무것도 없으면 뭘 놓쳤나 싶고, 어떻게 생길지 모르는
상태에서 미리 만든 구조는 십중팔구 틀린다.

더 중요한 건, **계산기를 순수 함수로 제대로 만들면 agent 계층이 거의 저절로 결정된다는
점**이었다. 툴 목록은 services의 공개 함수 목록이 되고, 툴 스키마는 시그니처가 된다.
순서를 이렇게 잡으면 나중 설계를 지금 추측할 필요가 없다.

**그 예상대로 됐다.** `agent/`는 계산기가 순수 함수로 자리잡은 뒤에 만들었고, 도구
13개 중 계산을 하는 것은 하나도 없다. `calc_damage` · `power_index` · `bulk_index`는
`services/damage.py`의 같은 이름 함수를 인자만 바꿔 부르고, 조회 도구는
`db/repositories/`를 그대로 부른다. `tools.py`가 하는 일은 이름을 찾아 주고(한국어
이름 → DB 행) 결과를 한국어로 돌려주는 것뿐이다.

`interfaces/api/routers/`는 아직도 없다. `app.py` 하나로 충분해서다.

---

## 5. 앞으로

### 지나온 순서

원래 여기 적어 둔 1 · 2 · 3 은 전부 끝났다. 순서를 지킨 것이 실제로 값을 했으므로
무엇이 어떻게 자리잡았는지만 남긴다.

**1. 입력 검증** — `services/team.py`의 `validate_spec()` 하나로 모았다. 특성은
`pokemon_repo.fetch_abilities`, 기술은 `move_repo.fetch_learnable`, 도구는
`item_repo.fetch_usable`을 본다. CLI와 웹이 서로 다른 경로로 들어오는데(웹은
`build_pokemon`을 거치지 않는다) 검증을 services에 둔 덕에 둘 다 같은 함수를
부른다.

**2. 도감** — `services/dex.py`는 만들지 않았다. 도감은 조회와 필터뿐이라 끼워 넣을
로직이 없어서, `db/repositories/`의 `fetch_list` · `fetch_detail`을 `app.py`가 바로
부른다. services 를 한 겹 두면 인자를 옮겨 적기만 하는 파일이 된다.

**3. 계산기** — `services/damage.py`에 `calc_damage` · `analyze_ko`와, 상대가 없어도
나오는 단일 지표인 `power_index` · `bulk_index`가 있다. 보정은 `modifiers.py`가
4096 정수로 다룬다. 날씨 · 필드 · 랭크 · 상태이상은 예상대로 `BattleContext` 한
덩어리로 묶였고, 참조표는 `Rules`로 받는다. 검증 케이스는 `tests/test_damage.py`에
40개 있다.

**4. agent** — 위가 순수 함수로 완성된 뒤에 만들었다. 도구 13개 중 계산을 하는 것은
없다(§4 참고).

### 다음 순서

**`services/opponent.py`** — 아직 비어 있다. 내 엔트리와 다른 점이 둘이다. 상대
스펙은 대부분 모르므로 **확정값과 추정값을 구분해서** 들고 있어야 하고(최속·최둔
가정 등), 대전마다 새로 만들어지고 버려지므로 파일에 저장할 이유가 없다. 그래서
`team.py`를 복사하지 말고, 공통이 정말 생겼을 때 `services/roster.py` 같은 곳으로
뽑아내는 편이 낫다.

**도구 `reviewed` 채우기** — `items.reviewed`가 0/166이다. 수집 범위를 좁히는
쪽(`get_items.py`의 `ITEM_CATEGORIES` + `EXTRA_ITEMS`)이 먼저 걸러 주고 있어서 지금
아프지는 않지만, 화면에는 166개가 전부 "미확인"으로 뜬다. `annotator.items`를
돌리거나, 이 방식을 접기로 하고 지우거나 — 둘 중 하나로 정해야 한다.

### 작업 규칙

리팩터링과 기능 추가를 같은 커밋에 넣지 않는다. 뭐 때문에 깨졌는지 영원히 못 찾는다.
한 번에 한 종류의 위험만 감수한다 — 이동만 하는 커밋, 로직만 고치는 커밋.

새 코드를 넣기 전에 스스로에게 묻는다.

- 이 SQL이 `db/repositories/` 밖에 있는가? → 옮긴다
- 이 함수가 conn 없이 돌 수 있는데 conn을 받는가? → 인자로 바꾼다
- 이 `print()`가 `services/` 안에 있는가? → 값을 돌려주고 출력은 위에서 한다

---

## 6. 재배치 이력 — 무엇이 어디로 갔나

아래는 `core/` 평면 구조에서 지금 배치로 옮길 때의 대응표다. 옛 경로를 기억하는
사람을 위해 남겨 둔다. 지금 폴더에 `core/` 는 없다.

| 이전 | 현재 | 비고 |
|---|---|---|
| `core/pokemons.py` | `domain/stats.py` + `domain/pokemon.py` | `__str__`은 `interfaces/cli.py`로 |
| `core/stat_calculator.py` | `services/stats.py` + `db/repositories/*` | 조회 4개와 계산 2개를 분리 |
| `core/my_pokemons.py` | `services/team.py` | `show_team()`은 CLI로 |
| `core/damage_calculator.py` | `services/damage.py` | 최상단 `psycopg2.connect()` 제거 |
| `core/enemy_pokemons.py` | `services/opponent.py` | |
| `core/web.py` | `interfaces/api/app.py` | |
| `core/web_static/` | `interfaces/api/static/` + `data/images/` | HTML은 코드, 이미지는 데이터 |
| `core/assets.py` | `assets.py` | 저장 위치가 `data/images/` |
| `core/database/db.py` | `config.py` + `db/connection.py` | 설정과 접속을 분리 |
| `core/database/*.py` | `scripts/etl/*.py` | `main.py` → `build.py` |
| `core/database/{sql,overrides,cache}/` | `data/{sql,overrides,cache}/` | |
| — | `pyproject.toml`, `tests/`, `.env.example` | 신규 |

**ETL 실행 방법이 바뀌었다.** 평평한 `import db`가 전부 패키지 상대 import로 바뀌었기
때문에, 프로젝트 루트에서 `-m`으로 돌린다.

```bash
python -m scripts.etl.build              # 이전: cd database && python main.py
python -m scripts.etl.get_items          # 이전: python get_items.py
python -m scripts.etl.annotator.moves    # 이전: python annotator/moves.py
```

DB 스키마와 데이터는 건드리지 않았다. 재구축 없이 그대로 쓸 수 있다.
