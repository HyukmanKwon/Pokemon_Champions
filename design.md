# 폴더 설계

> **이전 `design.md` 는 폐기됐다. 참고하지 않는다.**
>
> 그 문서는 `setting` · `pokemon` · `backend/{tool,pokemon_dex,pokemon_tier}` 로
> 나누는 스케치였다. 두 가지 이유로 쓰지 않는다.
>
> 1. `setting`(ETL)을 `src/` 안에 두면 배포판에 PokeAPI 파싱 코드가 딸려
>    들어간다. README 규칙 4 와 `pyproject.toml` 의 `where = ["src"]` 가
>    막고 있는 바로 그것이다.
> 2. `backend/` 아래를 기능(도감 · 채용률 · 계산기)으로 자르면 처음 셋까지만
>    쉽고 넷째부터 겹친다. 아래 §4 에 왜 그런지 적어 둔다.
>
> 다만 그 문서가 짚은 두 가지는 옳았고 이 설계가 받아 안았다 —
> 순수 계산기를 한 이름으로 묶는 것(`calc/`), 그리고 배틀 중 상태를
> 포켓몬 쪽에 모으는 것. 뒤엣것은 새 클래스가 아니라 `Pokemon` 을
> 채우는 쪽으로 풀었다 — §5 참고.

---

## 1. 이 문서가 푸는 문제

코드가 늘면서 어디에 무엇이 있는지 알아보기 어려워졌다. 원인을 찾아보니
층이 무너진 것은 아니었다 — `services/damage.py` 는 여전히 `conn` 을 안 받고,
SQL 은 여전히 `db/repositories/` 밖에 없다. 죽은 코드도 없었다.

무너진 것은 **판정 규칙**이다.

`services/` 와 `usecases/` 중 어디에 넣을지 정하는 규칙이 없었다. 그래서
`conn` 을 받는 `team.py` 는 `services/` 에 갔고, 성격이 똑같은 `battle.py` 는
`usecases/` 에 갔다. 누가 틀린 게 아니라 정할 근거가 없었다.

규칙이 없으면 사람도 AI 도 "제일 가까운 파일에 붙이자"를 고른다. 그 결과가
`app.py` 833줄과 `tools.py` 598줄이다.

> **좋은 폴더 구조의 기준은 예뻐 보이는 것이 아니라,
> 새 파일을 어디에 넣을지 1초 안에 정해지는 것이다.**

---

## 2. 구조

```
Pokemon_Champions/
├── main.py                  CLI 진입점. cli.main() 호출뿐
├── web.py                   웹 진입점. uvicorn 설정뿐
├── pyproject.toml
│
├── data/                    ▸ 실행되지 않는 것
│   ├── sql/                     DB 배포본 12개              (git 커밋)
│   ├── overrides/               사람이 확정한 값 4개          (git 커밋)
│   ├── cache/ images/           다시 만들 수 있는 것          (git 제외)
│   └── decks.json               개인 데이터                  (git 제외)
│
├── scripts/                 ▸ 손으로 가끔 돌리는 것. 배포 안 됨
│   ├── check_*.py               계산 결과를 알려진 값과 대조
│   └── etl/                     PokeAPI -> SQL -> DB
│
├── tests/
│
└── src/pokemon_champions/   ▸ 요청마다 도는 것. 이것만 배포됨
    │
    ├── config.py                레귤레이션 상수 · 경로 · 접속 정보
    ├── text.py                  NFC 정규화
    ├── assets.py                스프라이트 캐시
    │
    ├── domain/              ▸ "포켓몬이란 무엇인가"
    │   ├── pokemon.py           Pokemon (배틀 중 상태까지 들고 있다)
    │   └── stats.py             Stats
    │
    ├── db/                  ▸ SQL 이 존재해도 되는 유일한 곳
    │   ├── connection.py        connect()
    │   └── repositories/        pokemon_repo · move_repo · ... (9개)
    │
    ├── calc/                ▸ 순수 계산기. conn 을 안 받는다
    │   ├── stats.py             make_sp · calc_stats
    │   ├── damage.py            calc_damage · analyze_ko · power_index · bulk_index
    │   ├── modifiers.py         특성 · 도구 보정을 4096 정수로
    │   └── residual.py          턴 끝 지속 데미지 · 회복
    │
    ├── usecases/            ▸ 밖(DB · 파일 · 네트워크)을 만지며 조립한다
    │   ├── battle.py            계산기 진입점 셋 — power · bulk · one_hit
    │   ├── team.py              스펙 검증 · 빌드
    │   ├── roster.py            덱 여러 벌 (파일 저장)
    │   ├── naming.py            한↔영 이름 해석
    │   ├── usage.py             채용률을 DB 의 한국어와 잇기
    │   └── usage_source.py      채용률 원본 받아오기 + 캐시
    │
    ├── agent/               ▸ LLM 도우미. 모델은 도구만 고르고 계산은 안 한다
    │   ├── tools.py             도구 15개
    │   ├── schemas.py           도구 스키마
    │   ├── views.py             결과를 모델이 읽을 모양으로
    │   └── runner.py            Ollama 루프
    │
    └── interfaces/          ▸ print · input · HTTP 는 여기서만
        ├── cli.py
        └── api/
            ├── app.py           FastAPI 라우트만
            ├── views.py         DB 행 -> 화면용 JSON
            └── static/          index.html · css · js 7개
```

지금 구조에서 바뀌는 것은 넷뿐이다.

| 지금 | 다음 |
|---|---|
| `services/{damage,modifiers,residual,stats}.py` | `calc/` |
| `services/{team,usage}.py` | `usecases/` |
| `battledata.py` | `usecases/usage_source.py` (ETL 전용 절반은 `scripts/etl/` 로) |
| — | `interfaces/api/views.py` · `agent/views.py` 신설 |

`services/` 는 사라진다.

---

## 3. 판정 절차

위에서부터 묻고, **처음 "예" 에서 멈춘다.**

| | 질문 | 여기로 |
|---|---|---|
| 1 | 손으로 가끔 돌리는가? | `scripts/` |
| 2 | `print` · `input` · HTTP 응답을 만지는가? | `interfaces/` |
| 3 | LLM 이 부르는 도구인가? | `agent/` |
| 4 | SQL 문자열이 들어있는가? | `db/repositories/` |
| 5 | conn · 파일 · 네트워크를 만지는가? | `usecases/` |
| 6 | 같은 입력이면 항상 같은 출력인가? | `calc/` |
| 7 | 그냥 데이터의 모양인가? | `domain/` |

핵심은 **판정이 파일을 열지 않고 함수 시그니처만 보면 끝난다**는 것이다.

```python
def calc_damage(attacker, defender, move, ctx=None, rules=None)   # conn 없음 -> calc/
def one_hit(conn, rules, attacker, defender, move, ...)           # conn 있음 -> usecases/
```

취향이 아니라 사실로 결정된다.

---

## 4. 왜 이렇게 하는가

### 폴더 이름이 테스트 방법과 일치한다

`calc/` 에 있으면 DB 없이 테스트된다. `usecases/` 에 있으면 DB 가 필요하다.
그래서 폴더를 보는 순간 "이걸 어떻게 테스트하지?" 의 답이 이미 나와 있다.

지금은 `services/` 를 열면 `damage.py`(DB 불필요)와 `team.py`(DB 필요)가 나란히
있어서 매번 파일을 열어봐야 안다. 테스트 103개 중 93개가 DB 없이 도는데
그 사실이 폴더에 안 보인다.

### AI 와 일할 때는 규칙이 폴더에 있어야 한다

AI 는 매번 맥락을 새로 읽는다. README 에 "계산은 순수 함수로 쓴다" 고 적어둬도
작업할 때 그 문단까지 읽는다는 보장이 없다. 지난 몇 달간 규칙이 조용히
새어나간 경로가 이것이다.

폴더 이름은 다르다. `calc/damage.py` 를 열어서 `conn` 을 인자로 추가하려면
폴더 이름과 정면으로 충돌한다. **문서에 있는 규칙은 안 지켜지고, 이름에 있는
규칙은 지켜진다.**

### 기능별로 자르면 처음엔 쉽고 나중에 지옥이다

기능 폴더는 세 개까지만 쉽다. 넷째부터 겹친다. "메가진화" 는 어디로 가는가?

- `mega_repo` 가 폼과 메가스톤을 조회한다 -> 도감
- `team.resolve_mega` 가 엔트리를 조립한다 -> 엔트리
- `damage` 가 메가 종족값으로 계산한다 -> 계산기
- 채용률에도 메가 폼이 따로 집계된다 -> 채용률

전부다. 그래서 기능 폴더끼리 서로 import 하기 시작하고, 결국 어느 폴더를
열어도 다른 다섯 개를 부르고 있다.

|  | 자르는 기준 | 개수 |
|---|---|---|
| 층 | "무엇에 의존하는가" | 5~6개에서 멈춤 |
| 기능 | "무엇에 관한 것인가" | 무한히 늘어남 |

층은 아래로만 부르니 화살표가 안 엉킨다. 기능은 서로를 불러서 결국 엉킨다.
이 프로젝트는 이미 그 증거를 갖고 있다 — 도감 · 엔트리 · 계산기 · 채용률 ·
에이전트 다섯 기능이 전부 같은 `pokemon_repo` 와 `naming` 을 쓴다.

### 이름이 정직해진다

좋은 폴더 이름은 **그 이름으로 안 되는 것이 있어야** 한다.

| 이름 | 못 들어오는 것 |
|---|---|
| `calc/` | conn 받는 것 |
| `db/repositories/` | SQL 없는 것 |
| `interfaces/` | 계산하는 것 |
| `backend/` | 없음 — 그래서 안 쓴다 |

---

## 5. 솔직한 지점 둘

**`usecases/` 는 여전히 이름이 약하다.** {battle, team, roster, naming, usage,
usage_source} 는 성격이 조금씩 다르다. 그럼에도 이 이름을 쓰는 이유는 판정
규칙("밖을 만지는가")이 이름보다 강하기 때문이다. 그리고 `usecases/__init__.py`
가 이미 이 층이 왜 필요한지를 33줄로 정확히 적어두고 있다 — 이름을 바꾸면
그 문서가 가리키는 대상이 흔들린다.

**`views.py` 둘은 아직 합치지 않는다.** 웹용과 모델용이 필요한 칸이 실제로
다르다(웹은 `types` · `rank`, 모델은 `ko_name` 짝). 각각 뽑아내면 둘이 나란히
보이게 되고, **그때 합칠지 판단한다.** 지금 미리 합치면 필요 없는 추상화가
하나 생긴다.

---

## 6. 하지 않는 것

| | 이유 |
|---|---|
| `setting` 을 `src/` 안으로 | 규칙 4. 배포판에 ETL 이 딸려 들어간다 |
| `backend/` 신설 | `interfaces` 빼면 전부 backend 다. 정보량 0 |
| `domain` -> `pokemon` 등 rename | import 전부 건드리고 얻는 것이 없다 |
| `pokemon_dex` 폴더 | 도감은 조회와 필터뿐이라 인자만 옮겨 적는 파일이 된다 (README §5) |
| `migrations/` | `schema.py` 가 DDL 단일 출처고 전체 재구축이 가능하다 |

---

## 7. 문서 세 벌 — 역할이 겹치지 않게

같은 내용을 두 곳에 쓰면 하나만 고치게 되고, 그러면 둘 다 못 믿게 된다.
그래서 역할을 가른다.

| 파일 | 언어 | 담당 | 길이 |
|---|---|---|---|
| 루트 `README.md` | 한글 | 전체 지도 · 빠른 시작 · 설계 이유 | 지금 그대로 |
| 각 `__init__.py` docstring | 한글 | **왜** 이 폴더가 있는가 | 이미 있음, 유지 |
| 각 `CLAUDE.md` | 영어 | **무엇을 하지 마라** — 규칙만 | 5~15줄 |

`__init__.py` docstring 이 폴더별 `README.md` 보다 낫다 — 코드와 같은 파일에
있어서 덜 어긋나고, `import` 하면 따라오고, 파일을 옮기면 같이 옮겨진다.

`CLAUDE.md` 는 규칙이 실제로 있는 곳에만 둔다. Claude Code 가 편집하는 파일
근처의 것을 자동으로 읽으므로, 루트 README 를 읽어주길 기대하는 것보다 확실하다.

```
CLAUDE.md                          루트. 판정 표 + 커밋 규칙
src/pokemon_champions/
├── calc/CLAUDE.md                 conn 금지
├── db/repositories/CLAUDE.md      SQL 은 여기서만
├── usecases/CLAUDE.md             뷰를 만들지 마라
├── interfaces/CLAUDE.md           계산하지 마라
└── agent/CLAUDE.md                모델은 계산 안 한다
scripts/CLAUDE.md                  src/ 는 여기를 import 하지 않는다
```

---

## 8. 이행 순서

리팩터링과 기능 추가를 같은 커밋에 넣지 않는다. 한 번에 한 종류의 위험만
감수한다.

| | 단계 | 종류 | 검증 | 상태 |
|---|---|---|---|---|
| 0 | 잡동사니 · `.gitignore` | 삭제 | — | 완료 |
| 0b | DB 배포 전환 (`load_sql`) | 신규 | 빈 DB 재현 | 완료 |
| 1 | 쌓인 1,165줄 커밋 정리 | 이력 | pytest | 완료 |
| 1b | `sort_order` · 에러 문구 통일 | 로직 | 빈 DB 재현 | |
| 2 | `calc/` 분리 · `usecases/` 합류 | **이동만** | pytest 103개 | |
| 2b | `CLAUDE.md` 7개 | 신규 | — | |
| 3 | `interfaces/api/views.py` (833 -> 300줄대) | **이동만** | `golden/api.json` | |
| 4 | `agent/views.py` (598 -> 350줄대) | **이동만** | `golden/tools.json` | |
| 5 | 배틀 중 상태를 `Pokemon` 으로 | 로직 | golden 불변 | 완료 |

2~4 단계가 전부 "이동만" 인 것이 핵심이다. 골든 파일 둘이 응답을 통째로
박아두고 있어서, 옮기다 칸 이름 하나를 잘못 적으면 그 자리에서 실패한다.
이런 안전망이 있는 상태의 이동은 리팩터링 중 위험이 가장 낮은 종류다.

---

## 9. 새 코드를 넣기 전에 묻는 것

- 이 SQL 이 `db/repositories/` 밖에 있는가? -> 옮긴다
- 이 함수가 conn 없이 돌 수 있는데 conn 을 받는가? -> 인자로 바꾼다
- 이 `print()` 가 `calc/` 나 `usecases/` 안에 있는가? -> 값을 돌려주고 출력은 위에서
- 이 dict 리터럴이 라우트 안에 있는가? -> `views.py` 로
