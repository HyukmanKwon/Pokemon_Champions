TYPES_ENUM = "pokemon_types_enum"
NATURES_ENUM = "pokemon_natures_enum"

TYPE_NAMES = [
    "normal", "fire", "water", "electric", "grass", "ice", "fighting",
    "poison", "ground", "flying", "psychic", "bug", "rock", "ghost",
    "dragon", "dark", "steel", "fairy",
]

NATURE_NAMES = [
    "lonely", "brave", "adamant", "naughty",
    "bold", "relaxed", "impish", "lax",
    "timid", "hasty", "jolly", "naive",
    "modest", "mild", "quiet", "rash",
    "calm", "gentle", "sassy", "careful",
    "serious",
    # 무보정 성격. 본가는 다섯인데 오래 성실 하나만 넣어 두었다.
    # 채용률에 이 넷이 41행 잡혀서 뒤늦게 채운다.
    "hardy", "docile", "bashful", "quirky",
]


def _create_enum(name, values):
    items = ", ".join(f"'{v}'" for v in values)
    return (
        f"CREATE TYPE {name} AS ENUM ({items});\n"
    )


# ─────────────────────────────────────────────────────────────
# 파일별 DDL.
#
# DROP 도 IF NOT EXISTS 도 넣지 않는다. 순수한 CREATE 뿐이라
# 이미 테이블이 있는 DB에 실행하면 "already exists" 로 멈춘다.
# 다시 구축하려면 psql 로 먼저 지운다. (README §5)
#
# ALL_TABLES / ALL_ENUMS 는 그 삭제 명령을 만들 때 쓰는 목록이다.
# 새 테이블을 추가하면 여기에도 넣어야 한다.
# ─────────────────────────────────────────────────────────────

TYPES = (
    _create_enum(TYPES_ENUM, TYPE_NAMES)
    + f"""
CREATE TABLE pokemon_types (
    attack_type   {TYPES_ENUM} NOT NULL,    --공격 타입
    defense_type  {TYPES_ENUM} NOT NULL,    --방어 타입
    multiplier    REAL NOT NULL,            --배수
    PRIMARY KEY (attack_type, defense_type)
);
"""
)

# 타입 이름의 언어별 표기. 18타입 × ko·ja·en = 54행.
#
# 배수표(pokemon_types)와 같은 파일에 둔다. 둘 다 타입 이야기고, 둘 다
# API 를 안 부르는 고정값이라 갈라 둘 이유가 없다.
#
# 이 표가 없으면 화면의 타입 배지도, 도우미의 시스템 프롬프트도, 타입
# 아이콘 생성기도 영문으로 떨어진다. 읽는 곳이 다섯인데 만드는 곳이
# 없어서 여기 넣는다.
#
# (language, name) 에 UNIQUE 를 거는 이유는 역방향 조회 때문이다.
# "에스퍼" -> psychic 을 찾는데 두 타입이 같은 표기를 가지면 안 된다.
#
# type_name 이 VARCHAR 인 것은 지금 DB 가 그렇기 때문이다. pokemon_types
# 처럼 enum 이면 오타를 막아 주지만, 그 변경은 여기서 하지 않는다 —
# 배포본과 지금 DB 가 갈리면 "받아서 넣으면 내 것과 같아진다" 가 깨진다.
POKEMON_TYPE_NAMES = """CREATE TABLE pokemon_type_names (
    type_name  VARCHAR(10) NOT NULL,
    language   VARCHAR(10) NOT NULL,   -- ko · ja · en
    name       VARCHAR(20) NOT NULL,
    PRIMARY KEY (type_name, language),
    UNIQUE (language, name)
);
"""

NATURES = (
    _create_enum(NATURES_ENUM, NATURE_NAMES)
    + f"""
CREATE TABLE pokemon_natures (
    en_name  {NATURES_ENUM} PRIMARY KEY,
    ko_name  VARCHAR(50),
    up       CHAR(1),          -- 1.1배가 되는 능력치, 성실은 NULL
    down     CHAR(1)           -- 0.9배가 되는 능력치, 성실은 NULL
);
"""
)

# can_mega / is_mega 를 칸으로 두지 않는다.
#
# 둘 다 mega_evolutions 에서 그대로 나온다 — 그 표에 base_id 로 있으면
# 메가가 가능하고, mega_id 로 있으면 그 자체가 메가폼이다. 칸으로 두면
# 관계표와 갈라질 수 있고, 실제로 갈리지 않게 하려고 "전부 껐다가 다시
# 켜는" 함수를 따로 들고 있어야 했다. 다시 칠해야 하는 값이라면 애초에
# 저장할 값이 아니다.
#
# 읽는 쪽은 repositories 가 EXISTS 로 만들어 준다. 응답 모양은 그대로다.
POKEMONS = f"""CREATE TABLE pokemons (
    -- PokeAPI 번호. 폼마다 다르고 폼 변이는 10000번대다.
    -- 자식 표는 전부 이것을 가리킨다.
    id        INT PRIMARY KEY,

    -- 원종 도감 번호. 폼이 달라도 같다 (리자몽·메가리자몽X·Y 전부 6).
    -- 이름이 pokemon_id 였는데, 자식 표의 pokemon_id 가 id 를 가리키게
    -- 되면서 같은 이름이 두 뜻을 갖게 되어 바꿨다.
    dex_no    INT,

    name      VARCHAR(50) UNIQUE NOT NULL,
    ko_name   VARCHAR(50),
    type1     {TYPES_ENUM} NOT NULL,
    type2     {TYPES_ENUM},
    height    REAL,
    weight    REAL,
    h         INT,
    a         INT,
    b         INT,
    c         INT,
    d         INT,
    s         INT
);
"""

MOVES = f"""CREATE TABLE moves (
    id           INT PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,
    ko_name      VARCHAR(50),
    type         {TYPES_ENUM} NOT NULL,
    power        INT,            -- 변화기/고정 데미지는 NULL
    accuracy     INT,            -- 필중기는 NULL
    pp           INT,
    category     VARCHAR(10),    -- physical / special / status
    priority     INT,            -- 보통 0, 선제공격 +1 등

    -- 여기부터 계산용. PokeAPI /move 의 target 과 meta 에서 온다.
    target          VARCHAR(30),  -- selected-pokemon / all-opponents / user ...
    meta_category   VARCHAR(30),  -- damage-raise(자신) / damage-lower(상대) ...
    ailment         VARCHAR(20),  -- paralysis, burn ... 없으면 NULL
    ailment_chance  INT,          -- 상태이상 확률 %. 0이면 확정 또는 없음
    crit_rate       INT,          -- 급소율 보정 단계. 보통 0
    drain           INT,          -- 준 데미지의 % 회복. 음수면 반동
    healing         INT,          -- 최대 HP의 % 회복
    flinch_chance   INT,          -- 풀죽음 확률 %
    stat_chance     INT,          -- 능력 변화가 일어날 확률 %
    min_hits        INT,          -- 연속기 최소 타수. 단타는 NULL
    max_hits        INT,          -- 연속기 최대 타수. 단타는 NULL

    -- 기술 플래그. PokeAPI에 없어서 이름 규칙으로 추측하고 사람이 확인한다.
    -- 추측이 틀린 것은 DB 에서 직접 고치고 dump_sql 로 굳힌다.
    -- (annotator/moves.py) 확인 여부는 큐레이션 작업 상태라 표에 두지 않는다.
    is_contact  BOOLEAN NOT NULL DEFAULT FALSE,  -- 까칠한피부, 정전기, 철가시
    is_punch    BOOLEAN NOT NULL DEFAULT FALSE,  -- 철주먹 +20%
    is_bite     BOOLEAN NOT NULL DEFAULT FALSE,  -- 옹골찬턱 +50%
    is_sound    BOOLEAN NOT NULL DEFAULT FALSE,  -- 방음이 무효화
    is_powder   BOOLEAN NOT NULL DEFAULT FALSE,  -- 풀 타입에게 무효
    is_bullet   BOOLEAN NOT NULL DEFAULT FALSE,  -- 방탄이 무효화
    is_wind     BOOLEAN NOT NULL DEFAULT FALSE,  -- 바람타기, 풍력발전
    is_slicing  BOOLEAN NOT NULL DEFAULT FALSE,  -- 예리함 위력 1.5배
    is_dance    BOOLEAN NOT NULL DEFAULT FALSE,  -- 무희가 따라서 쓴다
    is_pulse    BOOLEAN NOT NULL DEFAULT FALSE,  -- 메가런처 위력 1.5배
    is_gravity  BOOLEAN NOT NULL DEFAULT FALSE,  -- 중력 상태에서 사용 불가
    is_press    BOOLEAN NOT NULL DEFAULT FALSE,  -- 작아지기 상대에 필중 + 2배

    description  TEXT,           -- 한국어 플레이버 텍스트
    effect       TEXT            -- 영어 효과 설명
);
"""

# 기술 하나가 능력 변화를 0~5개 일으킨다. moves 와 같은 04 단계에서 만든다.
#
# 누구에게 걸리는지는 이 테이블이 아니라 moves.meta_category 를 봐야 한다.
#   damage-raise    변화 대상이 시전자   (인파이트의 -1 방어는 자신에게)
#   damage-lower    변화 대상이 상대     (냉동바람의 -1 스피드는 상대에게)
#   net-good-stats  순수 변화기, 자신    (칼춤, 껍질깨기)
MOVE_STAT_CHANGES = """CREATE TABLE move_stat_changes (
    move_id  INT NOT NULL REFERENCES moves(id),
    stat     VARCHAR(3) NOT NULL,   -- a b c d s / acc eva
    change   INT NOT NULL,          -- -6 ~ +6
    PRIMARY KEY (move_id, stat)
);
"""

ABILITIES = """CREATE TABLE abilities (
    id           INT PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,
    ko_name      VARCHAR(50),    
    description  TEXT,
    effect       TEXT
);
"""

# "포챔스에서 지닐 수 있는가" 를 칸으로 두지 않는다.
#
# 전에는 usable BOOLEAN 과 그것을 사람이 확인했는지를 적는 reviewed 가
# 있었다. 그런데 거르는 자리가 이미 앞에 있다 — get_items.py 의
# ITEM_CATEGORIES 3개 + EXTRA_ITEMS 낱개 지정이 애초에 좁게 받아서, 이 표에
# 들어온 168개는 전부 지닐 수 있는 도구다. 뒤쪽 칸은 168개 전부 true 라
# 아무것도 거르지 않으면서 읽는 쪽마다 "이 행을 써도 되나" 를 묻게 만들었다.
#
# 카테고리를 넓힐 일이 생기면 넓히는 그 자리에서 좁힌다. 거르는 자리는
# 하나여야 한다.
ITEMS = """CREATE TABLE items (
    id           INT PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,
    ko_name      VARCHAR(50),
    category     VARCHAR(50),
    fling_power  INT,
    description  TEXT,
    effect       TEXT
);
"""

# 포켓몬이 가질 수 있는 특성. 03 단계에서 pokemons 와 같이 만든다.
#
# 전에는 pokemons 에 ability1 / ability2 / ability3 세 칸으로 있었다. 같은
# 속성이 색인만 달고 반복하는 모양이라(1NF 위반) 읽는 쪽이 매번 가로로
# 펼쳐야 했다 — repositories 다섯 군데가 CROSS JOIN LATERAL (VALUES ...) 나
# 3중 UNION 을 손으로 적고 있었다.
#
# 숨은 특성 여부는 칸으로 두지 않는다. slot = 3 이 곧 그것이다.
#
# slot 2 가 비고 slot 3 만 있는 포켓몬이 86마리다. 특성이 둘인데 하나가
# 숨은 특성인 경우라, 번호에 구멍이 나는 것이 정상이다. 그래서 slot 을
# "몇 번째" 가 아니라 PokeAPI 의 slot 값 그대로 둔다.
#
POKEMON_ABILITIES = """CREATE TABLE pokemon_abilities (
    pokemon_id  INT NOT NULL REFERENCES pokemons(id) ON DELETE CASCADE,
    ability_id  INT NOT NULL REFERENCES abilities(id),
    slot        SMALLINT NOT NULL CHECK (slot BETWEEN 1 AND 3),
    PRIMARY KEY (pokemon_id, slot),
    UNIQUE (pokemon_id, ability_id)
);
"""

# 습득 정보(레벨업/기술머신/유전)는 아직 없다. 포챔스가 그 구분을 룰로
# 쓰는지 정한 뒤에 넣는다 — PokeAPI 의 version_group_details 에 값은 있다.
#
# ON DELETE CASCADE 는 로스터 정리 때문이다. 빠진 포켓몬을 DELETE 할 때
# 기본값(RESTRICT)이면 기술이 연결된 포켓몬은 안 지워져 트랜잭션이
# 통째로 롤백된다.
POKEMON_MOVES = """CREATE TABLE pokemon_moves (
    pokemon_id  INT NOT NULL REFERENCES pokemons(id) ON DELETE CASCADE,
    move_id     INT NOT NULL REFERENCES moves(id),
    PRIMARY KEY (pokemon_id, move_id)
);
"""

# ─────────────────────────────────────────────────────────────
# 계산용 고정값. API 없이 만든다.
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# sort_order 가 weathers · terrains · status_conditions 셋에 있는 이유
#
#   이 셋은 화면의 드롭다운을 채운다. 그런데 조회에 ORDER BY 가 없으면
#   순서가 "행이 디스크에 놓인 순서" 가 된다. DB 가 하나뿐일 때는 그게
#   생성기가 적은 순서(쾌청·비·모래바람·눈)와 같아서 문제가 안 보인다.
#
#   dump_sql 은 diff 를 안정시키려고 행을 기본키순으로 정렬한다. 그래서
#   data/sql/ 로 세운 DB 는 알파벳순(rain·sandstorm·snow·sun)이 된다.
#   같은 저장소인데 설치 방법에 따라 화면이 달라진다.
#
#   ORDER BY name 으로 맞추면 둘이 같아지기는 하지만 의미를 잃는다.
#   쾌청이 먼저인 것은 알파벳이 아니라 본가 순서다. 그러니 그 순서를
#   값으로 적어 둔다 — 생성기의 목록 순서에서 그대로 뽑는다.
# ─────────────────────────────────────────────────────────────

# 메가진화 관계. 한 포켓몬이 X/Y 두 개를 가질 수 있어서 mega_id 가 PK다.
# pokemons 와 items 가 DB에 올라간 뒤에 만든다.
#
# variant(x/y)는 칸으로 두지 않는다. 스톤 이름이 그것을 담고 있다 —
# charizardite-x / charizardite-y. 지금 76행 중 x·y 가 붙는 것은 리자몽과
# 라이츄 넷뿐이고, 나머지는 단일 메가라 구분할 것이 없다.
MEGA_EVOLUTIONS = """CREATE TABLE mega_evolutions (
    mega_id  INT PRIMARY KEY REFERENCES pokemons(id),
    base_id  INT NOT NULL REFERENCES pokemons(id),
    item_id  INT REFERENCES items(id)   -- 매칭 실패 시 NULL
);
"""

# ─────────────────────────────────────────────────────────────
# 채용률 (championsbattledata.com)
#
# 저쪽에서 필요한 것은 둘뿐이다.
#   ① 포켓몬별 통계   usage_snapshots + usage_rows
#   ② 전체 순위       usage_snapshots.position
#
# 다른 표와 달리 PokeAPI 가 아니라 저쪽에서 오고, 한 번 만들고 끝이 아니라
# 하루 한 벌씩 쌓인다. 그래서 data/sql/ 에도 build.py 에도 안 들어간다.
# (scripts/etl/sync/usage.py)
#
# ── 왜 DB 에 쌓나 ──
#   저쪽 색인은 지난 날짜를 언젠가 지운다. 얼마나 남기는지는 저쪽 사정이라
#   보장이 없다 — 한때 16일치로 보였는데 지금은 34일치가 있다. 오늘 값을
#   보는 데는 캐시한 JSON 이면 충분하지만, 지난 달과 비교하려면 사라지기
#   전에 옮겨 두는 수밖에 없다.
#
#   폴더의 시즌 이름은 갱신되지 않는다. 2026-08-18 자료도 M4/ 아래 있다.
#   그래서 시즌을 가르는 것은 이름이 아니라 날짜다 (sync.usage.SEASON_START).
# ─────────────────────────────────────────────────────────────

# 저쪽 표기 -> 우리 것. 한 벌만 둔다.
#
# ── 왜 표로 빼나 ──
#   이름 935개가 12,076줄에 흩어져 있다. 성격은 25개가 2,349줄에 —
#   같은 대응을 94번 되풀이해 적는 셈이고, 날이 쌓일수록 그 배수가 는다.
#   오타 하나를 고치려면 그 줄을 다 훑어야 했고(lron Fist -> Iron Fist),
#   안 붙은 이름을 보려면 매번 GROUP BY 를 해야 했다.
#
#   빼 놓으면 고치는 것이 1행 UPDATE 가 되고, 못 붙인 이름은 이 표를
#   그냥 보면 된다.
#
# ── 왜 포켓몬까지 여기인가 ──
#   전에는 battle_names 를 따로 두었는데, 하는 일이 같았다. 갈래끼리
#   이름이 하나도 안 겹쳐서(확인함) source_name 만으로 기본키가 서고,
#   스냅샷과 순위가 거는 외래키도 그대로 선다. 나눌 이유가 없었다.
#
# ── 왜 갈래마다 칸이 다른가 ──
#   가리키는 표가 갈래마다 다르다. 한 칸으로 두면 외래키를 못 건다.
#   935행짜리라 칸을 다섯 두고 CHECK 로 묶는 값이 싸다.
#
# ── 왜 = 1 이 아니라 <= 1 인가 ──
#   못 붙인 이름도 들어가야 한다. 크롤링 자료라 외래키로 INSERT 를 막으면
#   그 줄을 통째로 잃는다. 원문을 남겨 두어야 저쪽 오타를 찾을 수 있다.
USAGE_NAMES = """CREATE TABLE usage_names (
    source_name  VARCHAR(50) PRIMARY KEY,   -- 저쪽 표기 그대로 (Focus Sash)
    category     VARCHAR(20) NOT NULL,      -- pokemon · move · held_item ...
    pokemon_id   INT REFERENCES pokemons(id) ON DELETE SET NULL,
    move_id      INT REFERENCES moves(id),
    item_id      INT REFERENCES items(id),
    ability_id   INT REFERENCES abilities(id),
    nature       pokemon_natures_enum REFERENCES pokemon_natures(en_name),
    CONSTRAINT usage_names_one_ref CHECK (
        num_nonnulls(move_id, item_id, ability_id, nature, pokemon_id) <= 1)
);
"""

# ① 한 관측 = 그날 그 포켓몬. 순위도 여기 있다.
#
# ── 왜 순위가 따로가 아닌가 ──
#   한때 usage_rankings 를 따로 두었다. "색인은 한 번에 235마리가 오고
#   CSV 는 하루 235번이라 채우는 시점이 갈린다" 가 이유였는데, 재보니
#   두 표가 같은 알갱이(날짜 × 포맷 × 이름)에 235행씩이고 한쪽에만 있는
#   줄이 0이었다. 한 표를 둘로 쪼갠 것이었다.
#
#   순위만 받고 본문을 안 받는 길은 남아 있다(--rankings-only). 그때는
#   position 만 찬 줄이 생긴다. "어느 날짜를 이미 받았나" 는 그래서
#   이 표가 아니라 usage_rows 가 있는지로 답한다. (known_keys)
#
# ── 왜 본문과는 따로인가 ──
#   본문이 한 마리에 50줄쯤 된다. 이 머리를 없애면 시즌·날짜·포맷·이름·
#   출처 다섯 칸이 235줄이 아니라 12,076줄에 따라붙고(하루치), 기본키가
#   28바이트에서 94바이트가 된다. 색인이 세 배로 뛴다.
#
# ── percent 와 position 을 헷갈리면 안 된다 ──
#   usage_rows 의 percent 는 전부 그 포켓몬 안에서의 비율이다. 지진 99.3%
#   는 한카리아스가 지진을 채용하는 비율이지 한카리아스가 얼마나 쓰이는지가
#   아니다. 포켓몬끼리 견줄 수 있는 것은 position 뿐이다.
USAGE_SNAPSHOTS = """CREATE TABLE usage_snapshots (
    id             SERIAL PRIMARY KEY,
    season         VARCHAR(10) NOT NULL,   -- M5
    snapshot_date  DATE NOT NULL,          -- 저쪽 폴더명 DD_MM_YYYY 를 날짜로
    format         VARCHAR(10) NOT NULL,   -- Singles / Doubles
    battle_name    VARCHAR(50) NOT NULL REFERENCES usage_names(source_name)
                       ON UPDATE CASCADE,
    position       INT,                    -- 1 이 1위. 순위를 못 받았으면 NULL
    source         VARCHAR(10) NOT NULL,   -- live · index · csv
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season, snapshot_date, format, battle_name)
);

-- 순위는 하루·포맷 안에서 유일하다. 순위 없이 본문만 있는 줄이 있을 수
-- 있어서(상위 밖) 부분 UNIQUE 다.
CREATE UNIQUE INDEX usage_snapshots_position_idx
    ON usage_snapshots (snapshot_date, format, position)
    WHERE position IS NOT NULL;

-- 한 마리의 추세를 훑는 질의용. UNIQUE 는 (시즌,일자,...) 순이라 못 쓴다.
CREATE INDEX usage_snapshots_battle_idx
    ON usage_snapshots (battle_name, format, snapshot_date);
"""

# ① 본문. 한 스냅샷의 50줄.
#
# 갈래가 여섯이고 그중 stat_points 만 모양이 다르다 — 이름이 없고 SP 여섯
# 칸이 한 벌로 온다. 한때 표를 갈랐는데, Postgres 는 NULL 을 널 비트맵으로
# 처리해서 빈 칸이 자리를 거의 안 먹는다. 표를 하나 더 두는 값이 그보다
# 비쌌다. 대신 source_name 의 NOT NULL 을 잃었다.
#
# 우리 것으로 옮기는 일은 여기서 안 한다. usage_names 를 조인한다.
USAGE_ROWS = """CREATE TABLE usage_rows (
    snapshot_id  INT NOT NULL REFERENCES usage_snapshots(id) ON DELETE CASCADE,
    category     VARCHAR(20) NOT NULL,
    rank         INT NOT NULL,
    source_name  VARCHAR(50),            -- 저쪽 표기. stat_points 는 NULL
    percent      NUMERIC(4,1),           -- teammate 는 NULL (저쪽이 안 준다)

    -- stat_points 만. 칸 이름을 우리 키(h·a·b·c·d·s)가 아니라 저쪽 표기로
    -- 두는 것은, 이 표가 남의 자료를 받아 적은 것이기 때문이다.
    hp_points       INT,
    attack_points   INT,
    defense_points  INT,
    sp_atk_points   INT,
    sp_def_points   INT,
    speed_points    INT,

    PRIMARY KEY (snapshot_id, category, rank)
);

-- "지진을 쓰는 비율이 어떻게 변했나" 는 이름으로 먼저 좁힌다.
CREATE INDEX usage_rows_name_idx ON usage_rows (category, source_name);
"""

# ─────────────────────────────────────────────────────────────
# 사람이 보는 창
#
# 정규화한 표는 기계가 읽기 좋지 사람이 읽기 좋지 않다. "한카리아스가 뭘
# 들고 다니나" 하나에 표 넷을 조인해야 하고, 갈래마다 조인 상대가 달라
# 한 번 쓴 질의를 다시 쓰지도 못한다.
#
# 그 조인을 여기서 한 번만 치른다. 앱은 usage_repo 가 대신 해 주므로
# 안 아팠고, 아픈 것은 psql 로 직접 들여다볼 때뿐이었다.
#
# 뷰라서 저장 공간을 안 쓰고 원본과 어긋날 일도 없다.
# ─────────────────────────────────────────────────────────────

# 채용 내역 한 줄 = 그 포켓몬이 그날 무엇을 얼마나 썼나.
# 갈래(기술·도구·특성·성격·팀원)를 가리지 않고 한국어 이름까지 붙는다.
USAGE_VIEW = """CREATE VIEW usage AS
SELECT s.snapshot_date, s.season, s.format,
       pk.ko_name AS pokemon,
       s.battle_name,
       r.category, r.rank,
       COALESCE(m.ko_name, i.ko_name, ab.ko_name,
                nt.ko_name, tpk.ko_name) AS ko_name,
       r.source_name,
       r.percent,
       r.hp_points, r.attack_points, r.defense_points,
       r.sp_atk_points, r.sp_def_points, r.speed_points
FROM usage_rows r
JOIN usage_snapshots s       ON s.id = r.snapshot_id
JOIN usage_names b           ON b.source_name = s.battle_name
LEFT JOIN pokemons pk        ON pk.id = b.pokemon_id
LEFT JOIN usage_names n      ON n.source_name = r.source_name
LEFT JOIN moves m            ON m.id = n.move_id
LEFT JOIN items i            ON i.id = n.item_id
LEFT JOIN abilities ab       ON ab.id = n.ability_id
LEFT JOIN pokemon_natures nt ON nt.en_name = n.nature
LEFT JOIN pokemons tpk       ON tpk.id = n.pokemon_id
                             AND r.category = 'teammate';
"""

# 전체 순위. 조인이 하나뿐이라 창이 얇다.
USAGE_RANK_VIEW = """CREATE VIEW usage_rank AS
SELECT s.snapshot_date, s.season, s.format, s.position,
       pk.ko_name AS pokemon, s.battle_name, s.source
FROM usage_snapshots s
JOIN usage_names b    ON b.source_name = s.battle_name
LEFT JOIN pokemons pk ON pk.id = b.pokemon_id
WHERE s.position IS NOT NULL;
"""

VIEWS = [("usage", USAGE_VIEW), ("usage_rank", USAGE_RANK_VIEW)]

# ─────────────────────────────────────────────────────────────
# 순서
#
# CREATE_ORDER   00_schema.sql 에 적히는 순서. 부모가 먼저다.
# CONTENT_ORDER  01_content.sql 의 INSERT 순서. 외래키가 걸리지 않는 순서다.
#
# 둘이 다른 이유는 생성 순서와 적재 순서가 같지 않아서가 아니라, 빈 표
# (usage_*)는 만들기만 하고 넣을 것이 없기 때문이다.
#
# ALL_TABLES 는 전부 지우는 명령을 만들 때 쓴다. 지우는 것은 CASCADE 라
# 순서를 안 탄다.
# ─────────────────────────────────────────────────────────────

CREATE_ORDER = [
    # 부모 — 다른 표를 가리키지 않는다
    ("pokemon_types", TYPES),
    ("pokemon_type_names", POKEMON_TYPE_NAMES),
    ("pokemon_natures", NATURES),
    ("pokemons", POKEMONS),
    ("moves", MOVES),
    ("abilities", ABILITIES),
    ("items", ITEMS),
    # 자식
    ("pokemon_abilities", POKEMON_ABILITIES),
    ("pokemon_moves", POKEMON_MOVES),
    ("move_stat_changes", MOVE_STAT_CHANGES),
    ("mega_evolutions", MEGA_EVOLUTIONS),
    # 채용률 — 매일 쌓이는 것이라 01_content.sql 에는 안 들어간다
    ("usage_names", USAGE_NAMES),
    ("usage_snapshots", USAGE_SNAPSHOTS),
    ("usage_rows", USAGE_ROWS),
]

SCHEMA_SQL = "\n".join(ddl for _, ddl in CREATE_ORDER + VIEWS)

# INSERT 순서. 부모가 먼저다 — pokemon_abilities 는 abilities 뒤여야 한다.
CONTENT_ORDER = [
    "pokemon_types", "pokemon_type_names", "pokemon_natures",
    "pokemons", "moves", "abilities", "items",
    "pokemon_abilities", "pokemon_moves", "move_stat_changes",
    "mega_evolutions",
]

ALL_TABLES = [name for name, _ in CREATE_ORDER]
ALL_ENUMS = [TYPES_ENUM, NATURES_ENUM, "pokemon_type", "nature_name"]
