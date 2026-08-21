# scripts/etl — 데이터베이스

**그냥 쓰려는 것이라면 아래 한 줄이 전부다.** `data/sql/` 이 저장소에 들어
있으니 그것만 넣으면 된다. API 를 부르지 않고 몇 초면 끝난다.

```bash
python -m scripts.etl.load_sql
```

이 아래는 그 `data/sql/` 을 다시 만들거나 고치는 이야기다.

---

## 1. 세 방향을 헷갈리지 말 것

| | 언제 | 무엇을 |
|---|---|---|
| `load_sql.py` | 설치할 때마다 | `data/sql/` → DB. API 0회, 몇 초 |
| `build.py` | 새 레귤레이션 | PokeAPI → DB. 약 1,900회, 몇 분 |
| `dump_sql.py` | DB 를 고친 뒤 | DB → `data/sql/`, 그리고 커밋 |

`build.py` 는 **빈 DB 가 필요하고 `data/sql/` 을 쓰지 않는다.** 데이터를
"고치려고" 이것을 돌리지 않는다 — 고치는 것은 psql 로 하고 `dump_sql` 로
굳힌다.

`data/sql/` 은 파일 둘이고, 이것이 다시 만들 수 없는 결과물이다.

| | 어디서 | 무엇이 |
|---|---|---|
| `00_schema.sql` | `schema.py` | 모든 `CREATE TYPE` / `CREATE TABLE`, 부모 먼저 |
| `01_content.sql` | 살아 있는 DB | 모든 `INSERT`, 외래키 안전한 순서로 |

DB 내용을 바꾼 뒤에는 `dump_sql` 을 돌려 커밋한다. 안 하면 다음 설치가
당신의 DB 와 달라진다.

---

## 2. 파일 구성

**파일 이름이 값의 출처를 말한다.** 파일을 열지 않고도 그 표가 어디서
오는지, 다시 만들면 얼마가 드는지 알 수 있어야 한다.

```
scripts/etl/
├── schema.py       표를 만드는 SQL 과 넣는 SQL. DDL 의 단일 출처
├── pokeapi.py      PokeAPI 에서 오는 값. 전체 약 1,900회
├── build.py        코드에 적힌 고정값 + 구축 순서. 유일한 진입점
├── sync_usage.py   championsbattledata.com 에서 날마다 쌓이는 것
├── load_sql.py     data/sql/ → DB
└── dump_sql.py     DB → data/sql/
```

`sync_usage.py` 만 성질이 다르다. 채용률은 한 번 만들고 끝이 아니라 날마다
붙으므로 `build.py` 에도 `data/sql/` 에도 들어가지 않는다.

각 파일의 첫머리 docstring 에 "왜 이렇게 갈랐나" 가 적혀 있다. 여기서
되풀이하지 않는다 — 두 벌이 되면 한쪽이 먼저 낡는다.

---

## 3. 구축 순서

`build.py` 가 표를 전부 만든 뒤 단계를 순서대로 돌린다.

| # | 단계 | 표 | 행 | API |
|---|---|---|---|---|
| 1 | `types` | `pokemon_types` + `pokemon_type_names` | 324 + 54 | 0 |
| 2 | `natures` | `pokemon_natures` | 25 | 0 |
| 3 | `pokemons` | `pokemons` | 318 | 636 |
| 4 | `moves` | `moves` + `move_stat_changes` | 498 + 151 | 498 |
| 5 | `abilities` | `abilities` + `pokemon_abilities` | 202 + 652 | 202 |
| 6 | `items` | `items` | 168 | 180 |
| 7 | `pokemon_moves` | `pokemon_moves` | 21,678 | 318 |
| 8 | `mega_evolutions` | `mega_evolutions` | 76 | 0 |

**순서가 있는 이유**는 뒤 단계가 앞 단계의 표를 읽기 때문이다.

- `abilities` 는 포켓몬 응답이 담아 둔 목록에서 대상을 정한다
- `pokemon_moves` 는 `pokemons` 와 `moves` 를 읽어 교집합만 저장한다
- `mega_evolutions` 는 `pokemons` 의 메가폼과 `items` 의 메가스톤을 맞춘다

### 호출이 행 수와 다른 단계

- **포켓몬**: 한 마리당 2회다. `/pokemon/{name}` 으로 종족값·타입·특성을
  받고, 응답 안의 `species.url` 을 한 번 더 타고 들어가 한국어 이름을 얻는다.
  한국어 이름이 species 리소스에만 있다.
- **기술**: 한 번의 호출로 표 둘을 만든다. `stat_changes` 가 같은 응답에 있다.
- **도구**: 카테고리 3회 + 도구 수만큼. 이름을 하나하나 적는 대신 카테고리를
  조회해 합집합으로 목록을 만든다.
- **연결**: 포켓몬 318회. 한 마리의 전체 기술 목록을 받아 `moves` 와
  교집합만 남기므로, 행은 21,678개지만 호출은 318회다.

---

## 4. 실행 규칙

### 매 실행마다 API 를 다시 호출한다

한 단계만 따로 보고 싶으면 `--only` 를 준다. DB 에는 실행하지 않는다.

```bash
python -m scripts.etl.build --only items          # 만들기만 (DB 안 건드림)
python -m scripts.etl.build --only items --exec   # DB 에도 넣기
python -m scripts.etl.build --only items --only moves
```

이름은 단계 이름과 표 이름 둘 다 걸린다. 못 찾는 이름을 주면 고를 수 있는
목록을 보여주고 멈춘다 — 오타를 조용히 건너뛰면 "돌렸는데 아무 일도
안 일어난다" 가 된다.

`--exec` 를 따로 시키는 이유는, 잘못 넣으면 되돌릴 방법이 §6 의 psql
명령뿐이기 때문이다.

### 재시도와 요청 간격이 없다

`get_json()` 은 200 이 아니면 `None` 을 돌려주고 호출부가 그 항목을
건너뛴다. 타임아웃이나 429 하나만 나도 그 항목이 조용히 빠진다는 뜻이다.
각 단계가 끝날 때 나오는 줄로 확인한다.

```
수집 498개 / 실패: 0개 - []
```

실패가 0 이 아니면 그 결과를 그대로 쓰지 않는 편이 안전하다.

### 중간에 실패하면 거기서 멈춘다

이어서 진행하는 기능은 없다. §6 으로 지우고 처음부터 다시 돌린다.

---

## 5. 목록을 고치는 법

포챔스에서 쓸 수 있는 것이 바뀌면 `pokeapi.py` 의 목록을 고친다.
전부 PokeAPI 이름 형식(소문자, 하이픈)이다.

| 무엇 | 어디 | 예 |
|---|---|---|
| 포켓몬 | `pokemon_M_B` | `charizard-mega-x` |
| 기술 | `moves_M_B` | `Fire Punch` → `fire-punch` |
| 도구 | `ITEM_CATEGORIES` · `EXTRA_ITEMS` | 카테고리 단위 + 낱개 |
| 특성 | 적지 않는다 | 포켓몬을 넣으면 특성도 따라온다 |

목록만 고치면 DB 는 그대로다. 반영하려면 전체 재구축(1,900회)을 하거나,
psql 로 그 몇 줄만 직접 넣는다. 넣은 뒤에는 `dump_sql` 로 굳힌다.

`sync_usage --fill-missing` 이 채운 기술·도구는 위 목록에도 손으로 넣어야
한다. 그 목록이 재구축의 출처라서, 안 넣으면 다시 지어질 때 사라진다.
무엇을 넣어야 하는지는 그 명령이 끝에 출력한다.

---

## 6. 지우고 다시 만들기

`build.py` 에는 삭제 기능이 없다. psql 에서 직접 지운다.

```bash
python -m scripts.etl.load_sql --drop-sql | psql -d pokemon
```

확인은 `\dt` 와 `\dT` 로 한다. 둘 다 비어 있으면 다시 돌린다.

`DROP TABLE` 이 멈춘 채 진행되지 않으면 다른 세션이 락을 쥐고 있는 것이다.
`pg_stat_activity` 에서 `idle in transaction` 인 pid 를 찾아 끊는다.

```sql
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = 'pokemon' AND pid <> pg_backend_pid();
```

---

## 7. 한국어가 없는 것

PokeAPI 에 한국어가 아직 없는 항목이 있다.

- 특성: `eelevate`, `fire-mane`
- 도구: 신규 메가스톤 대부분 (`clefablite`, `raichunite-x` 등 58개)

각 단계가 끝날 때 `한국어 이름 없음: N개 - [...]` 로 목록을 출력한다.
그 항목은 DB 에서 직접 채우고 `dump_sql` 로 굳힌다. 기술 플래그의
바람·베기·압박도 같다 — PokeAPI CSV 에 없어서 항상 추측이고, 사람이
확인한 값이 DB 에 남는다.

> 예전에는 이 교정을 `data/overrides/*.json` 에 따로 쌓고 재구축 때
> 덮어씌웠다. 그 파일이 결국 DB 의 사본이라 두 벌을 맞춰 두는 일만
> 남아서 걷어냈다. 지금은 `data/sql/` 이 그 값의 유일한 보관처다.

---

## 8. 새 표 추가하는 법

1. `schema.py` 에 DDL 상수를 만든다
2. `schema.py` 의 `CREATE_ORDER` 에 `(표 이름, DDL)` 을 넣는다 — 부모가 먼저다
3. 넣을 행이 있으면 `CONTENT_ORDER` 에도 표 이름을 넣는다
4. 값을 만드는 함수를 쓴다 — PokeAPI 에서 오면 `pokeapi.py`, 코드에 적는
   고정값이면 `build.py`
5. `build.py` 의 `STEPS` 에 `Step(...)` 을 의존 순서에 맞게 끼워 넣는다

`build` 함수는 **`INSERT` 문자열만 돌려준다.** 표를 만드는 SQL 은
`CREATE_ORDER` 한 곳에서만 나온다. `main()` 도 `connect()` 도 적지 않는다 —
`STEPS` 에 넣는 순간 `--only` 로 단독 실행이 된다.

한 응답에서 표 둘이 나오면 `Step` 의 `extra` 에 `((표, 칼럼),)` 을 적는다.
`dump_sql` 이 그 표의 칼럼 목록을 거기서 찾는다.

---

## 9. 알아둘 것

**SQL 파일에는 `DROP` 이 없다.** `CREATE TYPE` / `CREATE TABLE` 에
`IF NOT EXISTS` 가 없어서 두 번 실행하면 `already exists` 로 실패한다.
삭제는 §6 이 유일한 수단이다.

**날씨·필드·상태이상은 표가 아니다.** `src/pokemon_champions/calc/rules.py`
의 상수다. 열다섯 줄짜리라 표로 둘 이유가 없었고, `calc/` 는 `db/` 를
import 하지 않는다.

**외래키가 `pokemon_moves` 에는 없다.** 21,678행이라 걸어도 고아가 0건인
것은 확인했지만, 습득 정보(`learn_method` 등)를 넣을지 정한 뒤에 한 번에
손대는 편이 낫다.

**접속 정보는 환경변수로 바꾼다.** 기본값은
`src/pokemon_champions/config.py` 를 본다 — `PGHOST` · `PGPORT` ·
`PGDATABASE` · `PGUSER` · `PGPASSWORD`.

```bash
PGDATABASE=pokemon_test python -m scripts.etl.build
```
