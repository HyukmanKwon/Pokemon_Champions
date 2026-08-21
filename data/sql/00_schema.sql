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
    -- 추측이 틀린 것은 DB 에서 직접 고치고 dump_sql 로 굳힌다.
    -- 확인 여부는 큐레이션 작업 상태라 표에 두지 않는다.
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

CREATE TABLE usage_names (
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

CREATE TABLE usage_snapshots (
    id             SERIAL PRIMARY KEY,
    season         VARCHAR(10) NOT NULL,   -- M5
    snapshot_date  DATE NOT NULL,          -- 저쪽 폴더명 DD_MM_YYYY 를 날짜로
    format         VARCHAR(10) NOT NULL,   -- Singles / Doubles
    battle_name    VARCHAR(50) NOT NULL REFERENCES usage_names(source_name)
                       ON UPDATE CASCADE,
    position       INT,                    -- 1 이 1위. 순위를 못 받았으면 NULL
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

CREATE TABLE usage_rows (
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

CREATE VIEW usage AS
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

CREATE VIEW usage_rank AS
SELECT s.snapshot_date, s.season, s.format, s.position,
       pk.ko_name AS pokemon, s.battle_name
FROM usage_snapshots s
JOIN usage_names b    ON b.source_name = s.battle_name
LEFT JOIN pokemons pk ON pk.id = b.pokemon_id
WHERE s.position IS NOT NULL;
