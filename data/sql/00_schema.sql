CREATE TYPE pokemon_types_enum AS ENUM ('normal', 'fire', 'water', 'electric', 'grass', 'ice', 'fighting', 'poison', 'ground', 'flying', 'psychic', 'bug', 'rock', 'ghost', 'dragon', 'dark', 'steel', 'fairy');

CREATE TABLE pokemon_types (
    attack_type   pokemon_types_enum NOT NULL,    --공격 타입
    defense_type  pokemon_types_enum NOT NULL,    --방어 타입
    multiplier    REAL NOT NULL,            --배수
    PRIMARY KEY (attack_type, defense_type)
);

CREATE TABLE pokemon_type_names (
    type_name  VARCHAR(10) NOT NULL,
    language   VARCHAR(10) NOT NULL,   -- ko · ja · en
    name       VARCHAR(20) NOT NULL,
    PRIMARY KEY (type_name, language),
    UNIQUE (language, name)
);

CREATE TYPE pokemon_natures_enum AS ENUM ('lonely', 'brave', 'adamant', 'naughty', 'bold', 'relaxed', 'impish', 'lax', 'timid', 'hasty', 'jolly', 'naive', 'modest', 'mild', 'quiet', 'rash', 'calm', 'gentle', 'sassy', 'careful', 'serious', 'hardy', 'docile', 'bashful', 'quirky');

CREATE TABLE pokemon_natures (
    en_name  pokemon_natures_enum PRIMARY KEY,
    ko_name  VARCHAR(50),
    up       CHAR(1),          -- 1.1배가 되는 능력치, 성실은 NULL
    down     CHAR(1)           -- 0.9배가 되는 능력치, 성실은 NULL
);

CREATE TABLE pokemons (
    -- PokeAPI 번호. 폼마다 다르고 폼 변이는 10000번대다.
    -- 자식 표는 전부 이것을 가리킨다.
    id        INT PRIMARY KEY,

    -- 원종 도감 번호. 폼이 달라도 같다 (리자몽·메가리자몽X·Y 전부 6).
    -- 이름이 pokemon_id 였는데, 자식 표의 pokemon_id 가 id 를 가리키게
    -- 되면서 같은 이름이 두 뜻을 갖게 되어 바꿨다.
    dex_no    INT,

    name      VARCHAR(50) UNIQUE NOT NULL,
    ko_name   VARCHAR(50),
    type1     pokemon_types_enum NOT NULL,
    type2     pokemon_types_enum,
    height    REAL,
    weight    REAL,
    h         INT,
    a         INT,
    b         INT,
    c         INT,
    d         INT,
    s         INT
);

CREATE TABLE moves (
    id           INT PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,
    ko_name      VARCHAR(50),
    type         pokemon_types_enum NOT NULL,
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

CREATE TABLE abilities (
    id           INT PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,
    ko_name      VARCHAR(50),    
    description  TEXT,
    effect       TEXT
);

CREATE TABLE items (
    id           INT PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,
    ko_name      VARCHAR(50),
    category     VARCHAR(50),
    fling_power  INT,
    description  TEXT,
    effect       TEXT
);

CREATE TABLE pokemon_abilities (
    pokemon_id  INT NOT NULL REFERENCES pokemons(id) ON DELETE CASCADE,
    ability_id  INT NOT NULL REFERENCES abilities(id),
    slot        SMALLINT NOT NULL CHECK (slot BETWEEN 1 AND 3),
    PRIMARY KEY (pokemon_id, slot),
    UNIQUE (pokemon_id, ability_id)
);

CREATE TABLE pokemon_moves (
    pokemon_id  INT NOT NULL REFERENCES pokemons(id) ON DELETE CASCADE,
    move_id     INT NOT NULL REFERENCES moves(id),
    PRIMARY KEY (pokemon_id, move_id)
);

CREATE TABLE move_stat_changes (
    move_id  INT NOT NULL REFERENCES moves(id),
    stat     VARCHAR(3) NOT NULL,   -- a b c d s / acc eva
    change   INT NOT NULL,          -- -6 ~ +6
    PRIMARY KEY (move_id, stat)
);

CREATE TABLE mega_evolutions (
    mega_id  INT PRIMARY KEY REFERENCES pokemons(id),
    base_id  INT NOT NULL REFERENCES pokemons(id),
    item_id  INT REFERENCES items(id)   -- 매칭 실패 시 NULL
);

CREATE TABLE battle_names (
    battle_name  VARCHAR(50) PRIMARY KEY,   -- Garchomp, Alolan Raichu
    pokemon_id   INT REFERENCES pokemons(id) ON DELETE SET NULL
);

CREATE TABLE usage_names (
    category     VARCHAR(20) NOT NULL,   -- move · held_item · ability · stat_alignment
    source_name  VARCHAR(50) NOT NULL,   -- 저쪽 표기 그대로 (Focus Sash)
    move_id      INT REFERENCES moves(id),
    item_id      INT REFERENCES items(id),
    ability_id   INT REFERENCES abilities(id),
    nature       pokemon_natures_enum REFERENCES pokemon_natures(en_name),
    PRIMARY KEY (category, source_name),
    CHECK (num_nonnulls(move_id, item_id, ability_id, nature) <= 1)
);

CREATE TABLE usage_rankings (
    taken_on     DATE NOT NULL,          -- 그 순위가 가리키는 날
    format       VARCHAR(10) NOT NULL,
    season       VARCHAR(10) NOT NULL,
    battle_name  VARCHAR(50) NOT NULL REFERENCES battle_names(battle_name)
                     ON UPDATE CASCADE,
    position     INT NOT NULL,           -- 1 이 1위
    source       VARCHAR(10) NOT NULL,   -- index · csv
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (taken_on, format, battle_name)
);

CREATE UNIQUE INDEX usage_rankings_position_idx
    ON usage_rankings (taken_on, format, position);

CREATE TABLE usage_snapshots (
    id             SERIAL PRIMARY KEY,
    season         VARCHAR(10) NOT NULL,   -- M5
    snapshot_date  DATE NOT NULL,          -- 저쪽 폴더명 DD_MM_YYYY 를 날짜로
    format         VARCHAR(10) NOT NULL,   -- Singles / Doubles
    battle_name    VARCHAR(50) NOT NULL REFERENCES battle_names(battle_name)
                       ON UPDATE CASCADE,
    source         TEXT,                   -- 받아온 CSV 경로
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season, snapshot_date, format, battle_name)
);

-- 한 마리의 추세를 훑는 질의용. UNIQUE 는 (시즌,일자,...) 순이라 못 쓴다.
CREATE INDEX usage_snapshots_battle_idx
    ON usage_snapshots (battle_name, format, snapshot_date);

CREATE TABLE usage_picks (
    snapshot_id  INT NOT NULL REFERENCES usage_snapshots(id) ON DELETE CASCADE,
    category     VARCHAR(20) NOT NULL,
    rank         INT NOT NULL,
    source_name  VARCHAR(50) NOT NULL,   -- 저쪽 표기 그대로
    percent      NUMERIC(4,1),           -- teammate 는 NULL (저쪽이 안 준다)
    PRIMARY KEY (snapshot_id, category, rank)
);

-- "지진을 쓰는 비율이 어떻게 변했나" 는 이름으로 먼저 좁힌다.
CREATE INDEX usage_picks_name_idx ON usage_picks (category, source_name);

CREATE TABLE usage_spreads (
    snapshot_id  INT NOT NULL REFERENCES usage_snapshots(id) ON DELETE CASCADE,
    rank         INT NOT NULL,
    percent      NUMERIC(4,1),
    hp_points       INT,
    attack_points   INT,
    defense_points  INT,
    sp_atk_points   INT,
    sp_def_points   INT,
    speed_points    INT,
    PRIMARY KEY (snapshot_id, rank)
);
