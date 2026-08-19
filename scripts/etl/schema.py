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
# 관계표와 갈라질 수 있고, 실제로 갈리지 않게 하려고 migrate_roster 가
# "전부 껐다가 다시 켜는" 함수(sync_can_mega)를 들고 있었다. 다시 칠해야
# 하는 값이라면 애초에 저장할 값이 아니다.
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
    -- 확정값과 확인 여부는 overrides/move_flags.json 에 쌓인다.
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
# ON DELETE CASCADE 는 migrate_roster 때문이다. 로스터에서 빠진 포켓몬을
# DELETE 하는데, 기본값(RESTRICT)이면 기술이 연결된 포켓몬은 안 지워져
# 그 스크립트가 통째로 롤백된다.
POKEMON_MOVES = """CREATE TABLE pokemon_moves (
    pokemon_id  INT NOT NULL REFERENCES pokemons(id) ON DELETE CASCADE,
    move_id     INT NOT NULL REFERENCES moves(id),
    PRIMARY KEY (pokemon_id, move_id)
);
"""

# ─────────────────────────────────────────────────────────────
# 계산용 고정값. API 없이 만든다.
# ─────────────────────────────────────────────────────────────

# 상태이상 상수. 9세대 본가 기준값이므로 포챔스 룰이 다르면 여기만 고친다.
STATUS_CONDITIONS = """CREATE TABLE status_conditions (
    name          VARCHAR(20) PRIMARY KEY,  -- burn, paralysis ... moves.ailment 과 대응
    ko_name       VARCHAR(20),
    attack_mult   REAL,      -- 물리공격 보정. 화상 0.5
    speed_mult    REAL,      -- 스피드 보정. 마비 0.5
    turn_damage   REAL,      -- 매 턴 최대 HP의 몇 배를 잃는가
    immobile      BOOLEAN,   -- 행동 자체가 막히는가 (잠듦·얼음)
    fail_chance   REAL,      -- 행동이 실패할 확률. 마비 0.25
    note          TEXT,
    sort_order    INT NOT NULL UNIQUE   -- 화면에 늘어놓는 순서. 아래 주석 참고
);
"""

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

# 날씨. 기술 위력 보정과 방어 보정이 서로 다른 능력치에 붙는다.
#   모래바람 : 바위 타입의 '특수방어' 1.5배
#   눈       : 얼음 타입의 '방어' 1.5배
# 그래서 어느 능력치인지를 def_boost_stat 에 따로 적는다.
WEATHERS = f"""CREATE TABLE weathers (
    name            VARCHAR(20) PRIMARY KEY,
    ko_name         VARCHAR(20),
    boost_type      {TYPES_ENUM},   -- 위력이 오르는 기술 타입
    boost_mult      REAL,
    weaken_type     {TYPES_ENUM},   -- 위력이 내리는 기술 타입
    weaken_mult     REAL,
    def_boost_type  {TYPES_ENUM},   -- 방어 보정을 받는 포켓몬 타입
    def_boost_stat  CHAR(1),        -- b(방어) / d(특수방어)
    def_boost_mult  REAL,
    chip_damage     REAL,           -- 매 턴 최대 HP의 몇 배를 잃는가
    chip_immune     TEXT[],         -- 그 지속 데미지를 안 받는 타입
    note            TEXT,
    sort_order      INT NOT NULL UNIQUE   -- 화면 순서. STATUS_CONDITIONS 위 주석
);
"""

# 필드. 지면에 닿은 포켓몬에게만 적용된다.
# (비행 타입, 부유 특성, 풍선 소지, 텔레키네시스 대상은 제외)
TERRAINS = f"""CREATE TABLE terrains (
    name           VARCHAR(20) PRIMARY KEY,
    ko_name        VARCHAR(20),
    boost_type     {TYPES_ENUM},   -- 위력 1.3배가 되는 기술 타입
    boost_mult     REAL,
    weaken_type    {TYPES_ENUM},   -- 미스트필드의 드래곤 0.5배
    weaken_mult    REAL,
    heal_fraction  REAL,           -- 매 턴 회복량. 그래스필드 1/16
    note           TEXT,
    sort_order     INT NOT NULL UNIQUE   -- 화면 순서. STATUS_CONDITIONS 위 주석
);
"""

# ─────────────────────────────────────────────────────────────
# 채용률 기록. 다른 표와 달리 PokeAPI 가 아니라
# championsbattledata.com 에서 오고, 한 번 만들고 끝이 아니라
# 하루 한 벌씩 쌓인다. (scripts/etl/sync_usage.py)
#
# ── 왜 DB 에 쌓나 ──
#   저쪽은 일자별 자료를 16일치만 남긴다. 그보다 오래된 날짜는 색인에서
#   사라지고 다시 받을 방법이 없다. 오늘 값을 보는 데는 캐시한 JSON 이면
#   충분하지만, 지난 달과 비교하려면 사라지기 전에 옮겨 두는 수밖에 없다.
#
# ── 왜 두 표인가 ──
#   한 스냅샷이 50줄쯤 된다. 한 표로 두면 시즌·일자·포맷·이름이 그 50줄에
#   전부 따라붙고, "어느 날짜를 이미 받았나" 를 세려면 DISTINCT 를 해야
#   한다. 백필은 3,750번 받는 동안 언제든 끊길 수 있어서, 이어받을 때
#   읽는 그 질문이 한 줄로 끝나야 한다.
#
# ── 왜 영문 이름을 그대로 넣나 ──
#   usecases/usage.py 와 같은 판단이다. 한국어는 조회할 때 lookup_repo 로
#   붙인다. 여기에 굳혀 두면 나중에 ko_name 을 고쳤을 때 지난 스냅샷만
#   옛 표기로 남는다.
# ─────────────────────────────────────────────────────────────

# 저쪽 표기 -> 우리 이름. 한 벌만 둔다.
#
# 전에는 usage_snapshots 와 usage_rankings 가 각자 우리 이름을 들고
# 있었다. 그런데 battle_name 이 정해지면 pokemon_name 도 정해진다 —
# 4,220행이 236개짜리 대응표를 반복해 보관하던 셈이고, 두 표의 값이
# 갈라지면 어느 쪽이 맞는지 판별할 방법이 없었다. (이행 종속)
#
# 저쪽 표기를 키로 삼는 이유는 그것이 자료의 자연키이기 때문이다.
# 우리 쪽 키는 로스터에 없는 이름이면 NULL 이라 키가 될 수 없고,
# usage_rankings 의 기본키 구성 요소이기도 하다.
#
# ON DELETE SET NULL 은 migrate_roster 때문이다. 로스터에서 빠진 포켓몬을
# DELETE 해도 기록은 지난 일이라 사실로 남아야 한다. battle_name 이
# 남으므로 그 포켓몬이 다시 들어오면 이 표 한 행만 고치면 도로 이어붙는다
# — 전에는 4,220행을 훑어야 했다.
BATTLE_NAMES = """CREATE TABLE battle_names (
    -- 저쪽 표기가 기본키다. 저쪽 자료의 자연키이고, 우리 로스터에 없는
    -- 이름도 기록으로 남아야 하므로 이쪽이 NULL 이 될 수 없는 쪽이다.
    battle_name  VARCHAR(50) PRIMARY KEY,   -- Garchomp, Alolan Raichu
    pokemon_id   INT REFERENCES pokemons(id) ON DELETE SET NULL
);
"""

USAGE_SNAPSHOTS = """CREATE TABLE usage_snapshots (
    id             SERIAL PRIMARY KEY,
    season         VARCHAR(10) NOT NULL,   -- M4
    snapshot_date  DATE NOT NULL,          -- 저쪽 폴더명 DD_MM_YYYY 를 날짜로
    format         VARCHAR(10) NOT NULL,   -- Singles / Doubles
    battle_name    VARCHAR(50) NOT NULL REFERENCES battle_names(battle_name)
                       ON UPDATE CASCADE,   -- 우리 이름은 그쪽에 있다

    source         TEXT,                  -- 받아온 CSV 경로. 어디서 왔는지 되짚을 때

    -- 그날 그 포켓몬의 메타 순위. CSV 의 column_position 이다.
    -- 1 이 가장 많이 쓰인 포켓몬이고, 없으면 NULL(옛 자료).
    --
    -- 이 칸이 없어서 도우미가 헛소리를 했다. "가장 많이 쓰이는 포켓몬" 을
    -- 물으면 답할 자료가 없으니, 기술 채용률(지진 99.3%)을 포켓몬 사용률로
    -- 읽고 줄을 세웠다. 빈칸이 있으면 모델은 채운다.
    usage_rank     INT,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (season, snapshot_date, format, battle_name)
);

-- 한 마리의 추세를 훑는 질의용. UNIQUE 는 (시즌,일자,...) 순이라 이쪽으로 못 쓴다.
CREATE INDEX usage_snapshots_pokemon_idx
    ON usage_snapshots (battle_name, format, snapshot_date);
"""

# 한 스냅샷의 본문. category 마다 채우는 칸이 다르다.
#   move · held_item · ability   name + percent
#   teammate                     name 만 (저쪽이 비율을 안 준다)
#   stat_alignment               name(성격) + percent + stat_up/down
#   stat_points                  percent + SP 여섯 칸 (name 은 NULL)
USAGE_ROWS = """CREATE TABLE usage_rows (
    snapshot_id  INT NOT NULL REFERENCES usage_snapshots(id) ON DELETE CASCADE,
    category     VARCHAR(20) NOT NULL,
    rank         INT NOT NULL,
    name         VARCHAR(50),   -- 영문 표기 그대로. stat_points 는 NULL

    -- 그 이름을 우리 DB 에서 찾은 결과. 못 찾았거나 이름이 없는 줄(stat_points)
    -- 이면 NULL 이다. 어느 표를 가리키는지는 category 가 정한다.
    --
    --     move       -> moves.name          held_item -> items.name
    --     ability    -> abilities.name      teammate  -> pokemons.name
    --
    -- 외래키를 안 거는 이유는 한 칸이 네 표를 가리키기 때문이다. 대신
    -- category 로 조인한다.
    --
    -- ── 왜 저장하나 ──
    --   name 이 "Mimikyu" 로만 있으면 "한카리아스와 같이 쓰는 포켓몬의 타입
    --   분포" 를 SQL 로 못 낸다. 매번 파이썬에서 슬러그를 다시 맞춰야 하고,
    --   그 맞추기가 실패해도 조용히 빈 결과가 된다.
    --
    --   맞추는 규칙 자체는 usecases/usage.py 에 그대로 둔다. 여기 있는 것은
    --   그 결과를 굳혀 둔 것이라, 규칙이 좋아지면 다시 채우면 된다.
    linked_name  VARCHAR(50),

    -- teammate 는 NULL (저쪽이 비율을 안 준다).
    --
    -- REAL 이 아니라 NUMERIC 인 이유: 원본이 "99.4%" 처럼 소수 한 자리로
    -- 떨어지는데 REAL 은 그 값을 정확히 담지 못한다. 다른 표의 REAL 은
    -- 배수(1.5배)라 오차가 묻히지만, 이 표는 존재 이유가 두 날짜를 빼서
    -- 추세를 보는 것이다. 99.4 - 99.3 이 -0.099998474 로 나오면 곤란하다.
    percent      NUMERIC(4,1),
    stat_up      VARCHAR(3),    -- stat_alignment 만. 우리 키(spa)로 접어서 넣는다
    stat_down    VARCHAR(3),

    -- stat_points 만. 이름을 pokemons 의 h/a/b/c/d/s 가 아니라 저쪽 컬럼명
    -- 그대로 두는 것은, 이 표가 남의 자료를 받아 적은 것이기 때문이다.
    hp_points       INT,
    attack_points   INT,
    defense_points  INT,
    sp_atk_points   INT,
    sp_def_points   INT,
    speed_points    INT,

    PRIMARY KEY (snapshot_id, category, rank)
);

-- "지진을 쓰는 비율이 어떻게 변했나" 는 이름으로 먼저 좁힌다.
CREATE INDEX usage_rows_name_idx ON usage_rows (category, name);
"""

# ─────────────────────────────────────────────────────────────
# 전체 순위. 색인(/api) 한 번이면 235마리가 다 온다.
#
# ── 왜 usage_snapshots 와 따로인가 ──
#   저쪽이 주는 모양이 다르다. 스냅샷은 "그날 그 포켓몬의 CSV" 라 하루에
#   235번 받아야 하지만, 이 순위는 색인 한 번에 전부 온다. 요청 수가
#   235배 차이 나는 것을 한 표에 담으면 채우는 시점이 갈려 절반만 찬
#   행이 생긴다.
#
#   그리고 색인 값에는 날짜가 안 붙어 온다. "오늘 순위" 로만 오므로 받은
#   날짜를 우리가 찍는다. usage_snapshots.usage_rank 는 CSV 가 그날치로
#   준 값이라 출처가 다르고, 둘을 따로 두면 서로 대조할 수 있다.
# ─────────────────────────────────────────────────────────────

USAGE_RANKINGS = """CREATE TABLE usage_rankings (
    taken_on      DATE NOT NULL,          -- 받은 날. 저쪽은 날짜를 안 준다
    format        VARCHAR(10) NOT NULL,
    season        VARCHAR(10) NOT NULL,
    position      INT NOT NULL,           -- 1 이 1위
    battle_name   VARCHAR(50) NOT NULL REFERENCES battle_names(battle_name)
                      ON UPDATE CASCADE,   -- 우리 이름은 battle_names 에 있다
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (taken_on, format, battle_name)
);

CREATE UNIQUE INDEX usage_rankings_position_idx
    ON usage_rankings (taken_on, format, position);
"""

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
    ("status_conditions", STATUS_CONDITIONS),
    ("weathers", WEATHERS),
    ("terrains", TERRAINS),
    # 자식
    ("pokemon_abilities", POKEMON_ABILITIES),
    ("pokemon_moves", POKEMON_MOVES),
    ("move_stat_changes", MOVE_STAT_CHANGES),
    ("mega_evolutions", MEGA_EVOLUTIONS),
    # 채용률 — 매일 쌓이는 것이라 01_content.sql 에는 안 들어간다
    ("battle_names", BATTLE_NAMES),
    ("usage_snapshots", USAGE_SNAPSHOTS),
    ("usage_rows", USAGE_ROWS),
    ("usage_rankings", USAGE_RANKINGS),
]

SCHEMA_SQL = "\n".join(ddl for _, ddl in CREATE_ORDER)

# INSERT 순서. 부모가 먼저다 — pokemon_abilities 는 abilities 뒤여야 한다.
CONTENT_ORDER = [
    "pokemon_types", "pokemon_type_names", "pokemon_natures",
    "pokemons", "moves", "abilities", "items",
    "status_conditions", "weathers", "terrains",
    "pokemon_abilities", "pokemon_moves", "move_stat_changes",
    "mega_evolutions",
]

ALL_TABLES = [name for name, _ in CREATE_ORDER]
ALL_ENUMS = [TYPES_ENUM, NATURES_ENUM, "pokemon_type", "nature_name"]
