# scripts/etl — 데이터베이스 구축

PokeAPI에서 데이터를 받아 **SQL 파일을 만들고**, 그 파일을 **실행해서 DB를 구성**한다.
명령 하나면 끝난다. **프로젝트 루트에서** 실행한다.

```bash
python -m scripts.etl.build
```

> 예전에는 `cd database && python main.py` 였다. 지금은 정식 패키지라 `-m` 으로
> 돌린다. 어느 폴더에서 실행하든 같은 경로를 보게 하려는 것이다.

> **실행 전 DB가 비어 있어야 한다.**
> SQL 파일의 `CREATE TYPE` / `CREATE TABLE` 에 `IF NOT EXISTS` 가 없어서, 이미
> 테이블이 있는 DB에 실행하면 `already exists` 로 멈춘다. 다시 구축하려면
> psql 에서 먼저 지운다(§7).

---

## 1. 빠른 시작

```bash
pip install -e ".[dev]"   # 프로젝트 루트에서 한 번만
createdb pokemon          # 없다면
python -m scripts.etl.build
```

접속 정보는 환경변수로 바꾼다. 기본값은 `src/pokemon_champions/config.py` 참고.

| 환경변수 | 기본값 |
|---|---|
| `PGHOST` | localhost |
| `PGPORT` | 5432 |
| `PGDATABASE` | pokemon |
| `PGUSER` | hyukman |
| `PGPASSWORD` | (빈 값) |

```bash
PGDATABASE=pokemon_test python -m scripts.etl.build   # 다른 DB에 구축
```

전체 구축은 PokeAPI를 약 **1,900회** 호출한다. (기술 502 · 포켓몬 626 · 특성 200 ·
도구 296 · 연결 313)

---

## 2. 파일 구성

```
scripts/etl/
├── build.py              진입점. SQL 생성 → 실행을 순서대로 수행
├── paths.py              data/ 하위 경로. config.py 의 값을 그대로 쓴다
├── schema.py             모든 CREATE TABLE / ENUM 정의 (단일 출처)
├── parse_utils.py        PokeAPI 응답 파싱 + SQL 조립 공용 헬퍼
├── translation.py        포켓몬 이름 한↔영 변환, 폼 이름 조립
├── move_flags.py         기술 플래그 (PokeAPI CSV + 이름 규칙)
├── overrides.py          사람이 확정한 값 읽기/쓰기
├── check_moves.py        외부 목록과 기술 대조 (누락 찾기)
│
├── annotator/            브라우저에서 손으로 고치는 도구들
│   ├── _common.py        서버·화면 뼈대 (도구마다 재사용)
│   └── moves.py          기술 플래그
│
│
├── get_types.py          01_types.sql
├── get_natures.py        02_natures.sql
├── get_pokemons.py       03_pokemons.sql
├── get_moves.py          04_moves.sql
├── get_abilities.py      05_abilities.sql
├── get_items.py          06_items.sql
├── get_pokemon_moves.py  07_pokemon_moves.sql
│
├── get_stat_stages.py        08_stat_stages.sql
├── get_status_conditions.py  09_status_conditions.sql
├── get_mega_evolutions.py    10_mega_evolutions.sql
├── get_weathers.py           11_weathers.sql
├── get_terrains.py           12_terrains.sql
```

접속 설정(`connect()`, `DB_CONFIG`)은 여기 없다. `pokemon_champions.db` 와
`pokemon_champions.config` 에 있고 ETL 이 그것을 import 한다 — 앱과 ETL 이 서로 다른
DB를 보는 일을 막기 위해서다.

읽고 쓰는 데이터는 전부 프로젝트 루트의 `data/` 아래에 있다.

```
data/
├── sql/         build.py 가 만든 SQL. 실행할 때마다 덮어쓴다 (git 제외)
├── overrides/   사람이 확정한 값. 재구축해도 살아남는다 (git 커밋 대상)
│   ├── move_flags.json      기술 플래그
│   └── move_ko_names.json   PokeAPI 가 옛 번역을 주는 한국어 이름
└── cache/       내려받은 PokeAPI CSV. 재생성 가능 (git 제외)
    └── move_flag_map.csv
```

`data/sql/` 안의 파일은 손으로 고쳐도 다음 실행에서 사라진다.

---

## 3. 구축 순서

`build.py` 는 아래 순서로 **"SQL 생성 → 즉시 실행"** 을 반복한다.

| # | 파일 | 테이블 | 행 수 | API 호출 |
|---|---|---|---|---|
| 01 | `01_types.sql` | `pokemon_types` | 324 | 0 (고정값) |
| 02 | `02_natures.sql` | `pokemon_natures` | 21 | 0 (고정값) |
| 03 | `03_pokemons.sql` | `pokemons` | 313 | 626 |
| 04 | `04_moves.sql` | `moves` + `move_stat_changes` | 502 + α | 502 |
| 05 | `05_abilities.sql` | `abilities` | 200 | 200 |
| 06 | `06_items.sql` | `items` | 284 | 296 |
| 07 | `07_pokemon_moves.sql` | `pokemon_moves` | 21,295 | 313 |
| 08 | `08_stat_stages.sql` | `stat_stages` | 13 | 0 (고정값) |
| 09 | `09_status_conditions.sql` | `status_conditions` | 7 | 0 (고정값) |
| 10 | `10_mega_evolutions.sql` | `mega_evolutions` | 75 | 0 (DB에서 계산) |
| 11 | `11_weathers.sql` | `weathers` | 4 | 0 (고정값) |
| 12 | `12_terrains.sql` | `terrains` | 4 | 0 (고정값) |

**생성과 실행을 번갈아 하는 이유**는 뒤 단계가 앞 단계의 테이블을 읽기 때문이다.

- `05_abilities` 는 `pokemons` 의 `ability1/2/3` 을 훑어 대상 특성 목록을 만든다
- `07_pokemon_moves` 는 `pokemons` 와 `moves` 를 읽어 교집합만 저장한다
- `10_mega_evolutions` 는 `pokemons` 의 메가폼과 `items` 의 메가스톤을 맞춘다

그래서 03·04가 DB에 올라간 뒤에야 05·07을, 03·06 뒤에야 10을 만들 수 있다.
이 순서를 `build.py` 가 알아서 지킨다.

### 호출 횟수가 행 수와 다른 단계

- **03 포켓몬**: 한 마리당 2회다. `/pokemon/{name}` 으로 종족값·타입·특성을 받고,
  응답 안의 `species.url` 을 한 번 더 타고 들어가 한국어 이름을 얻는다.
  한국어 이름이 species 리소스에만 있기 때문이다.
- **04 기술**: 한 번의 호출로 테이블 두 개를 만든다. `move_stat_changes` 에 필요한
  `stat_changes` 가 같은 응답에 들어 있어서, 단계를 나누지 않고 04에 합쳤다.
- **06 도구**: 카테고리 12회 + 도구 284회. 도구는 이름을 하나하나 적는 대신
  카테고리를 조회해 합집합으로 목록을 만든다.
- **07 연결**: 포켓몬 313회. 한 마리의 전체 기술 목록을 받아 `moves` 테이블과
  교집합만 남기므로, 행은 21,295개지만 호출은 313회다.

---

## 4. 실행 규칙

### 매 실행마다 API를 다시 호출한다

`data/sql/` 에 파일이 남아 있어도 재사용하지 않는다. `build.py` 의
`ensure_sql()` 이 조건 없이 `step.build(conn)` 을 부르고 파일을 덮어쓴다.

SQL 파일만 따로 뽑고 싶으면 개별 생성기를 쓴다. DB에는 실행하지 않는다.

```bash
python -m scripts.etl.get_items   # data/sql/06_items.sql 만 생성
```

### 재시도와 요청 간격이 없다

`parse_utils.get_json()` 은 200이 아니면 그냥 `None` 을 돌려주고, 호출부는 그
항목을 건너뛴다. 타임아웃이나 429 하나만 나도 그 항목이 조용히 빠진다는 뜻이다.

각 생성기가 끝날 때 출력하는 줄로 확인한다.

```
수집 502개 / 실패: 0개 - []
```

실패가 0이 아니면 그 SQL 파일을 그대로 쓰지 않는 편이 안전하다.

### 중간에 실패하면 거기서 멈춘다

한 단계가 깨지면 롤백하고 어느 파일에서 멈췄는지 알린 뒤 종료한다.

```
04_moves.sql 에서 멈췄습니다.
  UndefinedColumn: column "target" of relation "moves" does not exist

앞 단계까지는 DB에 반영돼 있습니다. 이어서 진행할 수 없으니
README §7 로 전부 지운 뒤 다시 실행하세요.
```

이어서 진행하는 기능은 없다. §7 로 지우고 처음부터 다시 돌린다.

---

## 5. 손으로 고친 값 — annotator

PokeAPI가 주지 않는 정보는 이름 규칙으로 추측할 수밖에 없고, 추측은 반드시
틀린다. 그 수정을 psql 로 하면 두 가지가 문제다. 502개 × 12칸을 UPDATE 문으로
치면 오타가 나고, **다음 재구축에서 전부 사라진다.**

```bash
python -m scripts.etl.annotator.moves    # 브라우저가 열린다 (http://localhost:8765)
```

도구가 여러 개가 되므로 `annotator/` 폴더에 모아 둔다. 화면·서버·저장 흐름은
`_common.py` 에 있고, 각 파일은 "무엇을 보여주고 무엇을 체크할지"만 정한다.
특성·도구 효과 편집기를 추가할 때도 `annotator/abilities.py` 처럼 붙이면 된다.

체크박스를 건드리면 **즉시 두 군데에 저장**된다.

```
DB moves 테이블            즉시 반영. 계산기가 바로 쓴다
overrides/move_flags.json  재구축해도 살아남는다. git 에 커밋된다
```

생성기가 매번 이 JSON을 읽어 추측값 위에 덮어씌우므로, 한 번 확정한 값은
재구축을 몇 번 해도 유지된다.

```
추측 (move_flags.py)  ->  overrides 적용  ->  SQL 파일  ->  DB
```

### 무엇을 확인해야 하나

12개 플래그 중 9개는 PokeAPI CSV 에서 온 확정값이라 볼 필요가 거의 없다(§8).
손이 필요한 건 두 갈래다.

1. **바람 · 베기 · 압박** — CSV 에 대응 flag 가 없어 502개 전부 추측이다
2. **`move_id` 826 이후 신기술 등 59개** — CSV 에 없어 12개 전부 추측이다

### 계열 칩으로 찾는다

상단의 계열 칩(접촉·펀치·물기 … 12개)을 누르면 그 계열만 남는다. 이때 두
종류를 같이 띄우는 것이 핵심이다.

| | 뜻 |
|---|---|
| 켜진 것 | 그 플래그가 이미 TRUE 인 기술 |
| **후보** | 아직 FALSE 지만 이름에 관련 단어가 들어 있는 기술 |

후보 칸에는 주황 테두리가 붙는다. **빠뜨린 것은 켜진 것만 봐서는 절대 찾을
수 없다.** 베기 칩을 누르면 `slash`·`cut`·`blade`·`claw`·`axe`·`edge`·`sword`
가 든 기술 26개가 전부 올라오므로, 그중 진짜 베기만 체크하면 끝난다.

`표시: 후보만` 으로 두면 아직 안 켜진 것만 남아서 더 빠르다. 우측에
`베기 켜짐 20 / 후보 6` 처럼 진행 상황이 나온다.

힌트는 넉넉하게 잡아 뒀다. 관계없는 게 섞여도 눈으로 걸러내면 되지만, 좁게
잡아서 놓치면 못 찾는다. 힌트 목록은 `annotator/moves.py` 의 `GROUP_HINTS` 다.
접촉은 물리 기술 대부분이라 이름 힌트가 의미 없어서 비워 뒀다.

추측 규칙이 틀리기 쉬운 지점들이다.

- 이름에 `bomb` 이 있어도 찍찍베기(`population-bomb`)는 총알이 아니라 베기다
- `dance` 가 들어가도 비바라기(`rain-dance`)는 날씨 기술이라 춤이 아니다
- 하드프레스(`hard-press`)는 이름과 달리 압박이 아니다
- 바디프레스(`body-press`)도 압박이 아니다

다 맞으면 "보이는 것 전부 확인 처리" 를 누른다. 확인한 줄은 흐리게 표시되고
"미확인만" 필터로 남은 것만 볼 수 있다.

### JSON 형식

```json
{
  "reviewed": ["fire-punch", "sucker-punch"],
  "values": { "sucker-punch": {"is_punch": false} }
}
```

`values` 에는 **추측과 결론이 다른 항목만** 들어간다. `move_flags.py` 의 규칙을
나중에 개선하면 항목이 저절로 줄어든다. `reviewed` 는 추측이 맞았더라도
사람이 봤다는 표시라서 전부 들어간다.

---

## 6. 목록이 맞는지 확인하기

`moves_M_B` 와 `pokemon_M_B` 는 손으로 채운 목록이라 빠진 것이 생긴다. 포챔스
전용 사이트에서 목록을 복사해 붙이고 대조한다.

```bash
python -m scripts.etl.check_moves 목록.txt      # 한국어 이름 한 줄에 하나
```

참고할 사이트:
[op.gg](https://op.gg/ko/pokemon-champions/moves) ·
[PokéBase](https://pokebase.app/pokemon-champions/moves) ·
[Pokémon Zone](https://www.pokemon-zone.com/champions/moves/) ·
[Game8](https://game8.co/games/Pokemon-Champions/archives/590397)

**개수만 비교하면 안 된다.** 다른 이유가 두 가지이고 대응이 정반대다.

| 종류 | 뜻 | 할 일 |
|---|---|---|
| 번역만 다름 | 같은 기술인데 표기가 다르다 | `ko_name` 만 고친다 |
| DB 에 없음 | 진짜 빠졌다 | `moves_M_B` 에 영문 이름 추가 후 재구축 |

### 실제로 찾은 것 (op.gg 502개 대조)

**진짜 누락 4개** — `moves_M_B` 에 추가했다. 이제 502개다.

| 한국어 | 영문 | 비고 |
|---|---|---|
| 버섯포자 | `spore` | 수면가루만 있고 이게 빠져 있었다 |
| 알낳기 | `soft-boiled` | |
| 우유마시기 | `milk-drink` | |
| 파워시프트 | `power-shift` | 레전드 아르세우스 신기술 |

**번역 차이 2개** — `overrides/move_ko_names.json` 에 넣었다.

```
깨뜨리다 -> 깨트리기   brick-break
독실     -> 독독실     toxic-thread
```

번역 차이는 **PokeAPI 의 한국어 이름이 옛 세대 번역**이라 생긴다. `/move` 의
`names` 배열은 언어당 한 개뿐이고 그 값이 갱신되지 않는다.

```
깨뜨리다 (PokeAPI)  vs  깨트리기 (포챔스)   brick-break
독실     (PokeAPI)  vs  독독실   (포챔스)   toxic-thread
```

구분은 자모 단위 유사도로 한다. 음절로 비교하면 `깨트리기`와 `깨뜨리다`가
2/4 밖에 안 닮은 것으로 나와서 놓친다. 다만 유사도만으로 갈라지지 않는
경우가 있어서, 애매한 구간은 후보 3개를 띄우고 사람이 고른다.

```
깨트리기 vs 깨뜨리다   0.62   같은 기술
알낳기   vs 아픔나누기  0.63   다른 기술
```

점수가 거의 같아서 임계치를 어디에 두든 하나는 틀린다. 그래서 자동 판정하지
않는다.

---

## 7. 지우고 다시 만들기

`build.py` 에는 삭제 기능이 없다. psql 에서 직접 지운다.

```sql
DROP TABLE IF EXISTS pokemon_moves, move_stat_changes, mega_evolutions,
    items, abilities, moves, pokemons, pokemon_types, pokemon_natures,
    stat_stages, status_conditions, weathers, terrains CASCADE;
DROP TYPE IF EXISTS pokemon_types_enum, pokemon_natures_enum CASCADE;
```

확인은 `\dt` 와 `\dT` 로 한다. 둘 다 비어 있으면 `python -m scripts.etl.build` 를 다시 돌린다.

`DROP TABLE` 이 멈춘 채 진행되지 않으면 다른 세션이 락을 쥐고 있는 것이다.
`pg_stat_activity` 에서 `idle in transaction` 인 pid 를 찾아 끊는다.

```sql
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = 'pokemon' AND pid <> pg_backend_pid();
```

---

## 8. 테이블 스키마

정의는 전부 `schema.py` 에 있다. 여기를 고치면 모든 SQL 파일에 반영된다.

### `pokemon_types` — 타입 상성표 (18×18)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| `attack_type` | `pokemon_types_enum` | 공격 타입 |
| `defense_type` | `pokemon_types_enum` | 방어 타입 |
| `multiplier` | REAL | 0.0 / 0.5 / 1.0 / 2.0 |

### `pokemon_natures` — 성격 21종
| 컬럼 | 타입 | 설명 |
|---|---|---|
| `en_name` | `pokemon_natures_enum` | PK |
| `ko_name` | VARCHAR(50) | 고집, 겁쟁이 … |
| `up` | CHAR(1) | 1.1배가 되는 능력치. 성실은 NULL |
| `down` | CHAR(1) | 0.9배가 되는 능력치. 성실은 NULL |

### `pokemons` — 포켓몬
| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | INT | PokeAPI 번호. 폼은 10000번대 |
| `name` | VARCHAR(50) | **PK**. `charizard-mega-x` 형식 |
| `ko_name` | VARCHAR(50) | 메가리자몽X |
| `type1` `type2` | `pokemon_types_enum` | 단일 타입이면 `type2`는 NULL |
| `ability1~3` | VARCHAR(50) | `abilities.name` 과 대응 |
| `height` `weight` | REAL | m, kg |
| `h a b c d s` | INT | 종족값 |
| `can_mega` | BOOLEAN | 이 폼에서 메가진화가 가능한가 |
| `is_mega` | BOOLEAN | 이 폼 자체가 메가폼인가 |

`can_mega` / `is_mega` 는 API 값이 아니라 `pokemon_M_B` 안에서 계산한다.
`gengar-mega` 가 목록에 있으면 `gengar` 의 `can_mega` 가 TRUE 가 된다.
포챔스에서 못 쓰는 메가는 목록에서 빼는 것만으로 반영된다.

### `moves` — 기술
`id`(PK), `name`(UNIQUE), `ko_name`, `type`, `power`, `accuracy`, `pp`,
`category`(physical/special/status), `priority`, `description`(한글), `effect`(영문)

변화기·고정 데미지는 `power`가 NULL, 필중기는 `accuracy`가 NULL.

계산용 컬럼은 PokeAPI `/move` 의 `target` 과 `meta` 에서 가져온다.

| 컬럼 | 설명 |
|---|---|
| `target` | `selected-pokemon`, `all-opponents`, `user` … 더블에서 필요 |
| `meta_category` | 능력 변화가 **누구에게** 걸리는지 판별한다 (아래 참고) |
| `ailment` `ailment_chance` | 상태이상 종류와 확률 %. 없으면 `ailment`가 NULL |
| `crit_rate` | 급소율 보정 단계. 보통 0, 야습 등은 1 |
| `drain` | 준 데미지의 % 회복. **음수면 반동** |
| `healing` | 최대 HP의 % 회복 |
| `flinch_chance` | 풀죽음 확률 % |
| `stat_chance` | 능력 변화가 일어날 확률 % |
| `min_hits` `max_hits` | 연속기 타수. 단타는 둘 다 NULL |

플래그 12개는 `/move` 응답에 없다. `flags` 필드 자체가 없다. 그래서 **PokeAPI 의
CSV 덤프**에서 가져오고, CSV 가 커버하지 않는 것만 이름 규칙으로 추측한다.

분류 기준은 나무위키 [포켓몬스터/기술/성질별](https://namu.wiki/w/포켓몬스터/기술/성질별) 의 13개 성질을 따랐다.

| 컬럼 | 나무위키 | 반응하는 것 | 출처 |
|---|---|---|---|
| `is_contact` | 접촉 | 까칠한피부, 정전기, 불꽃몸, 철가시 | CSV |
| `is_punch` | 펀치 | 철주먹 위력 +20% | CSV |
| `is_bite` | 물기 | 옹골찬턱 위력 +50% | CSV |
| `is_sound` | 소리 | 방음 무효. 대타출동을 뚫는다 | CSV |
| `is_powder` | 가루 | 풀 타입 무효. 방진고글·방진도 막는다 | CSV |
| `is_bullet` | 구슬·폭탄 | 방탄 무효 | CSV |
| `is_dance` | 춤 | 무희가 따라서 쓴다 | CSV |
| `is_pulse` | 파동 | 메가런처 위력 1.5배 | CSV |
| `is_gravity` | 상승 | 중력 상태에서 사용 불가 | CSV |
| `is_wind` | 바람 | 바람타기 무효 + 공격 1랭크↑, 풍력발전 충전 | **추측** |
| `is_slicing` | 베기 | 예리함 위력 1.5배 | **추측** |
| `is_press` | 압박 | 작아지기 상대에게 필중 + 피해 2배 | **추측** |
| `reviewed` | | 사람이 이 기술의 플래그를 확인했는가 | |

나무위키 13개 성질 중 개요를 뺀 12개가 그대로 들어갔다.

한 기술이 여러 플래그를 갖는다. 에어커터는 바람이면서 베기고, 플라잉프레스는
상승이면서 압박이다.

### CSV 가 어디까지 채워 주나

```
https://raw.githubusercontent.com/PokeAPI/pokeapi/master/
    data/v2/csv/move_flags.csv       flag_id -> 이름  (21줄. 코드에 박아 뒀다)
    data/v2/csv/move_flag_map.csv    move_id -> flag_id  (받아서 cache/ 에 둔다)
```

`moves.id` 가 PokeAPI 번호와 같아서 그대로 조인된다. 첫 실행에서 한 번 받고
이후에는 `cache/move_flag_map.csv` 를 재사용한다.

```
CSV 로 채움 : 443개 (88%)  9개 플래그 확정값
추측        :  59개 (12%)  move_id 826 이후 신기술. 12개 전부 추측
바람·베기·압박 : 502개 전부 추측. CSV 에 대응 flag 가 없다
```

`move_id` 826 에서 데이터가 끊기는 탓에 레전드 아르세우스 이후 신기술 55개
(`gigaton-hammer`, `matcha-gotcha`, `psychic-noise`, `jet-punch` …)는 추측이다.

CSV 를 쓰는 효과는 분명하다. 예를 들어 이름 규칙으로는 `super-fang`(분노의앞니)이
`fang` 때문에 물기로 잡히는데, CSV 는 물기가 아니라고 정확히 알려준다.
`sucker-punch`(기습)가 펀치가 아닌 것도 CSV 로 확인된다.

`get_moves.py` 가 끝날 때 어느 쪽이 몇 개였는지 출력한다.

```
플래그: CSV 443개 / 추측 59개
  추측으로 채운 기술: dire-claw, psyshield-bash, stone-axe, ...
  바람·베기·압박은 CSV 에 없어 전부 추측입니다. annotator/moves.py 로 확인하세요.
```

### `move_stat_changes` — 기술의 능력 변화
`move_name`, `stat` (둘이 합쳐 PK), `change`

`stat` 은 `a b c d s` 와 `acc`(명중), `eva`(회피). `change` 는 `-6 ~ +6`.
능력 변화가 없는 기술은 아예 행이 없다.

**누구에게 걸리는지는 이 테이블에 없다.** `moves.meta_category` 를 봐야 한다.

| `meta_category` | 대상 | 예 |
|---|---|---|
| `damage-raise` | 시전자 | 인파이트(자신 방어 -1), 리프스톰 |
| `damage-lower` | 상대 | 냉동바람, 깨트리기 |
| `net-good-stats` | 시전자 | 칼춤, 껍질깨기 |

인파이트가 `damage-raise` 인데 값이 음수라 헷갈리지만, PokeAPI가 "변화 대상이
시전자"라는 뜻으로 쓰는 이름이다. 부호가 아니라 대상을 가리킨다.

### `abilities` — 특성
`id`(PK), `name`(UNIQUE), `ko_name`, `description`(한글), `effect`(영문)

### `items` — 도구
`id`(PK), `name`(UNIQUE), `ko_name`, `category`, `fling_power`,
`description`(한글), `effect`(영문)

### `pokemon_moves` — 포켓몬-기술 연결
`pokemon_name`, `move_name` (둘이 합쳐 PK)

### `stat_stages` — 랭크 변화 배수 (13행, 고정값)
`stage`(PK, -6~+6), `battle_mult`, `accuracy_mult`

공방과 명중·회피는 계산식이 다르다. 같은 +1이라도 공격은 1.5배, 명중은 1.333배다.

```
공방      stage >= 0 : (2 + stage) / 2      stage < 0 : 2 / (2 - stage)
명중회피   stage >= 0 : (3 + stage) / 3      stage < 0 : 3 / (3 - stage)
```

### `status_conditions` — 상태이상 상수 (7행, 고정값)
`name`(PK), `ko_name`, `attack_mult`, `speed_mult`, `turn_damage`,
`immobile`, `fail_chance`, `note`

`name` 은 PokeAPI 의 move-ailment 이름이라 `moves.ailment` 와 바로 조인된다.

```sql
SELECT m.ko_name, s.ko_name, s.attack_mult
FROM moves m JOIN status_conditions s ON m.ailment = s.name;
```

값은 **9세대 본가 기준**이다. 세대마다 바뀐 적이 있으니(화상 1/8→1/16,
마비 스피드 1/4→1/2) 포챔스가 다르면 `get_status_conditions.py` 의
`CONDITIONS` 만 고치면 된다.

### `mega_evolutions` — 메가진화 관계 (75행)
`mega_name`(PK), `base_name`, `variant`(x/y/NULL), `item_name`

베이스는 이름 규칙으로 자른다(`charizard-mega-x` → `charizard` + `x`).
메가스톤은 규칙이 없어서 — `blastoisinite`(blastoise), `heracronite`(heracross),
`alakazite`(alakazam)처럼 철자가 깎인다 — **접두사가 가장 길게 겹치는 스톤**을
고른다. 겹침이 베이스 이름의 60%에 못 미치면 틀린 스톤을 넣는 대신 NULL로
두고 끝에 목록을 출력한다.

성별 폼은 스톤을 공유한다. `meowstic-male`과 `meowstic-female`이 똑같이
`meowsticite`를 쓰므로, 매칭할 때만 `-male` / `-female` 꼬리를 떼어낸다.
이름 규칙에서 아예 벗어나는 것은 `get_mega_evolutions.py` 의 `MANUAL_BASE` 에
적는다. (현재 `pyroar-mega` → `pyroar-male` 하나뿐)

### `weathers` — 날씨 (4행, 고정값)
`name`(PK), `ko_name`, `boost_type` `boost_mult`, `weaken_type` `weaken_mult`,
`def_boost_type` `def_boost_stat` `def_boost_mult`, `chip_damage`, `chip_immune`, `note`

보정이 두 종류다. 하나는 **기술 위력**(비에서 물 1.5배, 불꽃 0.5배), 다른 하나는
**방어 능력치**인데 붙는 능력치가 서로 다르다.

| 날씨 | 위력 | 방어 보정 | 지속 데미지 |
|---|---|---|---|
| `sun` 쾌청 | 불꽃 ×1.5, 물 ×0.5 | — | — |
| `rain` 비 | 물 ×1.5, 불꽃 ×0.5 | — | — |
| `sandstorm` 모래바람 | — | 바위의 **특수방어** ×1.5 | 1/16 (바위·땅·강철 제외) |
| `snow` 눈 | — | 얼음의 **방어** ×1.5 | — |

어느 능력치인지는 `def_boost_stat`(`b` 또는 `d`)에 들어 있다. `name` 은 날씨를
까는 기술과 이어진다 (`sunny-day`→`sun`, `snowscape`→`snow`).

9세대 기준이다. 8세대까지의 싸라기눈은 얼음 타입을 뺀 전원이 1/16을 잃었지만,
9세대 눈은 지속 데미지가 없다.

### `terrains` — 필드 (4행, 고정값)
`name`(PK), `ko_name`, `boost_type` `boost_mult`, `weaken_type` `weaken_mult`,
`heal_fraction`, `note`

| 필드 | 효과 |
|---|---|
| `electric` 일렉트릭필드 | 전기 ×1.3, 잠듦 무효 |
| `grassy` 그래스필드 | 풀 ×1.3, 매 턴 1/16 회복, 지진·땅고르기 ×0.5 |
| `misty` 미스트필드 | 드래곤 ×0.5, 상태이상·혼란 무효 |
| `psychic` 사이코필드 | 에스퍼 ×1.3, 우선도 1 이상 기술 무효 |

**필드는 접지된 포켓몬에게만 걸린다.** 비행 타입·부유·풍선은 영향을 받지 않는다.
위력 1.3배도 기술을 쓰는 쪽이 접지되어 있을 때만 붙는다. 이 판정은 테이블이
아니라 계산 코드에서 해야 한다.

---

## 9. 수집 범위 조절

### 포켓몬 — `get_pokemons.py` 의 `pokemon_M_B`
PokeAPI 이름 형식(소문자, 하이픈)으로 적는다. 예: `charizard-mega-x`

### 기술 — `get_moves.py` 의 `moves_M_B`
같은 형식. `Fire Punch` → `fire-punch`

### 특성 — 목록을 적지 않는다
`pokemons` 테이블의 `ability1/2/3` 에서 자동으로 뽑는다. 포켓몬을 추가하면
특성도 따라온다.

### 도구 — `get_items.py` 의 `ITEM_CATEGORIES`
PokeAPI 카테고리 단위로 수집한다. 포챔스 룰에 따라 넣고 빼면 된다.

```python
ITEM_CATEGORIES = [
    "held-items", "choice", "bad-held-items", "type-enhancement",
    "species-specific", "mega-stones", "stat-boosts", "in-a-pinch",
    "type-protection", "picky-healing", "effort-training", "plates",
]
```

빠져 있는 후보: `z-crystals`, `memories`, `jewels`, `training`, `effort-drop`

---

## 10. 알아둘 것

### 포챔스 신규 데이터는 영어만 들어와 있다
PokeAPI에 한국어가 아직 없는 항목이 있다.

- 특성: `eelevate`, `fire-mane` → `ko_name` NULL
- 도구: 신규 메가스톤 대부분(`clefablite`, `raichunite-x` 등 58개) → `ko_name` NULL

생성기가 끝날 때 `한국어 이름 없음: N개 - [...]` 로 목록을 출력하니, 그 항목만
나중에 채우면 된다.

### SQL 파일에는 `DROP` 이 없다
`schema.py` 의 DDL 은 순수한 `CREATE TYPE` / `CREATE TABLE` 이다. 그래서 SQL 파일을
두 번 실행하면 `already exists` 로 실패한다. 삭제는 §7 의 psql 명령이 유일한 수단이다.

### 외래키는 아직 없다
`pokemons.ability1 → abilities.name`, `pokemon_moves.pokemon_name → pokemons.name`
같은 FK를 걸 수 있지만 지금은 넣지 않았다.

---

## 11. 새 테이블 추가하는 법

1. `schema.py` 에 DDL 상수를 추가한다
2. `get_XX.py` 를 만들고 아래를 노출한다

   ```python
   FILENAME = "08_XXX.sql"
   TABLE    = "XXX"
   COLUMNS  = [...]          # INSERT 컬럼 순서
   DDL      = schema.XXX
   USES_API = True

   def build(conn) -> str:   # SQL 전문을 문자열로 반환
       ...
   ```

3. `build.py` 의 `STEPS` 에 의존 순서에 맞게 끼워 넣는다
4. `schema.py` 의 `ALL_TABLES` 에 테이블 이름을 추가한다

파일에 직접 쓰지 않고 문자열을 반환하는 것이 규칙이다. 파일 배치는 `build.py` 가 한다.
각 `get_*.py` 의 `main()` 은 그 파일을 단독 실행할 때만 쓰는 진입점이고,
`build.py` 는 `build()` 만 호출한다.
