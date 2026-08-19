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

CREATE TABLE status_conditions (
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

CREATE TABLE weathers (
    name            VARCHAR(20) PRIMARY KEY,
    ko_name         VARCHAR(20),
    boost_type      pokemon_types_enum,   -- 위력이 오르는 기술 타입
    boost_mult      REAL,
    weaken_type     pokemon_types_enum,   -- 위력이 내리는 기술 타입
    weaken_mult     REAL,
    def_boost_type  pokemon_types_enum,   -- 방어 보정을 받는 포켓몬 타입
    def_boost_stat  CHAR(1),        -- b(방어) / d(특수방어)
    def_boost_mult  REAL,
    chip_damage     REAL,           -- 매 턴 최대 HP의 몇 배를 잃는가
    chip_immune     TEXT[],         -- 그 지속 데미지를 안 받는 타입
    note            TEXT,
    sort_order      INT NOT NULL UNIQUE   -- 화면 순서. STATUS_CONDITIONS 위 주석
);

CREATE TABLE terrains (
    name           VARCHAR(20) PRIMARY KEY,
    ko_name        VARCHAR(20),
    boost_type     pokemon_types_enum,   -- 위력 1.3배가 되는 기술 타입
    boost_mult     REAL,
    weaken_type    pokemon_types_enum,   -- 미스트필드의 드래곤 0.5배
    weaken_mult    REAL,
    heal_fraction  REAL,           -- 매 턴 회복량. 그래스필드 1/16
    note           TEXT,
    sort_order     INT NOT NULL UNIQUE   -- 화면 순서. STATUS_CONDITIONS 위 주석
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
    -- 저쪽 표기가 기본키다. 저쪽 자료의 자연키이고, 우리 로스터에 없는
    -- 이름도 기록으로 남아야 하므로 이쪽이 NULL 이 될 수 없는 쪽이다.
    battle_name  VARCHAR(50) PRIMARY KEY,   -- Garchomp, Alolan Raichu
    pokemon_id   INT REFERENCES pokemons(id) ON DELETE SET NULL
);

CREATE TABLE usage_snapshots (
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

CREATE TABLE usage_rows (
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

CREATE TABLE usage_rankings (
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
