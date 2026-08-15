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

INSERT INTO weathers
    (name, ko_name, boost_type, boost_mult, weaken_type, weaken_mult, def_boost_type, def_boost_stat, def_boost_mult, chip_damage, chip_immune, note, sort_order)
VALUES
    ('rain', '비', 'water', 1.5, 'fire', 0.5, NULL, NULL, NULL, NULL, NULL, '번개·폭풍이 필중. 아침햇살 회복량 1/4', 1),
    ('sandstorm', '모래바람', NULL, NULL, NULL, NULL, 'rock', 'd', 1.5, 0.0625, ARRAY['rock','ground','steel'], '바위 타입의 특수방어 1.5배', 2),
    ('snow', '눈', NULL, NULL, NULL, NULL, 'ice', 'b', 1.5, NULL, NULL, '얼음 타입의 방어 1.5배. 9세대부터 지속 데미지 없음', 3),
    ('sun', '쾌청', 'fire', 1.5, 'water', 0.5, NULL, NULL, NULL, NULL, NULL, '솔라빔이 즉시 발동. 대타출동·아침햇살 회복량 2/3', 0);
