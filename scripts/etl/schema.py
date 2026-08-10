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

POKEMONS = f"""CREATE TABLE pokemons (
    id         INT,   -- PokeAPI 번호. 폼마다 다르고 폼 변이는 10000번대다
    pokemon_id INT,   -- 원종 도감 번호. 폼이 달라도 같다 (메가리자몽 -> 6)
    name      VARCHAR(50) PRIMARY KEY,
    ko_name   VARCHAR(50),
    type1     {TYPES_ENUM} NOT NULL,
    type2     {TYPES_ENUM},
    ability1  VARCHAR(50),
    ability2  VARCHAR(50),
    ability3  VARCHAR(50),
    height    REAL,
    weight    REAL,
    h         INT,
    a         INT,
    b         INT,
    c         INT,
    d         INT,
    s         INT,
    can_mega  BOOLEAN NOT NULL DEFAULT FALSE,  -- 이 폼에서 메가진화가 가능한가
    is_mega   BOOLEAN NOT NULL DEFAULT FALSE   -- 이 폼 자체가 메가폼인가
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
    -- 확정값은 overrides/move_flags.json 에 쌓인다. (annotator/moves.py)
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
    reviewed    BOOLEAN NOT NULL DEFAULT FALSE,  -- 사람이 플래그를 확인했는가

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
    move_name  VARCHAR(50) NOT NULL REFERENCES moves(name),
    stat       VARCHAR(3) NOT NULL,   -- a b c d s / acc eva
    change     INT NOT NULL,          -- -6 ~ +6
    PRIMARY KEY (move_name, stat)
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

ITEMS = """CREATE TABLE items (
    id           INT PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,
    ko_name      VARCHAR(50),
    category     VARCHAR(50),
    fling_power  INT,
    description  TEXT,
    effect       TEXT,

    -- 포챔스에서 지니게 할 수 있는가. PokeAPI 는 이 구분을 주지 않아서
    -- 일단 전부 TRUE 로 두고 사람이 확인한다. (annotator/items.py)
    -- 확정값은 overrides/item_usable.json 에 쌓이고 get_items.py 가 덮어씌운다.
    usable      BOOLEAN NOT NULL DEFAULT TRUE,
    reviewed    BOOLEAN NOT NULL DEFAULT FALSE   -- 사람이 usable 을 확인했는가
);
"""

POKEMON_MOVES = """CREATE TABLE pokemon_moves (
    pokemon_name  VARCHAR(50) NOT NULL,
    move_name     VARCHAR(50) NOT NULL,
    PRIMARY KEY (pokemon_name, move_name)
);
"""

# ─────────────────────────────────────────────────────────────
# 계산용 고정값. API 없이 만든다.
# ─────────────────────────────────────────────────────────────

# 랭크 변화 배수. 공격·방어 계열과 명중·회피는 계산식이 다르다.
#   공방   stage >= 0 : (2 + stage) / 2      stage < 0 : 2 / (2 - stage)
#   명중회피 stage >= 0 : (3 + stage) / 3      stage < 0 : 3 / (3 - stage)
STAT_STAGES = """CREATE TABLE stat_stages (
    stage          INT PRIMARY KEY,   -- -6 ~ +6
    battle_mult    REAL NOT NULL,     -- a b c d s 에 적용
    accuracy_mult  REAL NOT NULL      -- 명중률·회피율에 적용
);
"""

# 상태이상 상수. 9세대 본가 기준값이므로 포챔스 룰이 다르면 여기만 고친다.
STATUS_CONDITIONS = """CREATE TABLE status_conditions (
    name          VARCHAR(20) PRIMARY KEY,  -- burn, paralysis ... moves.ailment 과 대응
    ko_name       VARCHAR(20),
    attack_mult   REAL,      -- 물리공격 보정. 화상 0.5
    speed_mult    REAL,      -- 스피드 보정. 마비 0.5
    turn_damage   REAL,      -- 매 턴 최대 HP의 몇 배를 잃는가
    immobile      BOOLEAN,   -- 행동 자체가 막히는가 (잠듦·얼음)
    fail_chance   REAL,      -- 행동이 실패할 확률. 마비 0.25
    note          TEXT
);
"""

# 메가진화 관계. 한 포켓몬이 X/Y 두 개를 가질 수 있어서 mega_name 이 PK다.
# pokemons 와 items 가 DB에 올라간 뒤에 만든다.
MEGA_EVOLUTIONS = """CREATE TABLE mega_evolutions (
    mega_name  VARCHAR(50) PRIMARY KEY REFERENCES pokemons(name),
    base_name  VARCHAR(50) NOT NULL REFERENCES pokemons(name),
    variant    CHAR(1),      -- x / y, 단일 메가면 NULL
    item_name  VARCHAR(50) REFERENCES items(name)  -- 매칭 실패 시 NULL
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
    note            TEXT
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
    note           TEXT
);
"""

ALL_TABLES = [
    "pokemon_moves", "move_stat_changes", "mega_evolutions",
    "items", "abilities", "moves", "pokemons",
    "pokemon_types", "pokemon_natures",
    "stat_stages", "status_conditions", "weathers", "terrains",
]
ALL_ENUMS = [TYPES_ENUM, NATURES_ENUM, "pokemon_type", "nature_name"]
