CREATE TABLE terrains (
    name           VARCHAR(20) PRIMARY KEY,
    ko_name        VARCHAR(20),
    boost_type     pokemon_types_enum,   -- 위력 1.3배가 되는 기술 타입
    boost_mult     REAL,
    weaken_type    pokemon_types_enum,   -- 미스트필드의 드래곤 0.5배
    weaken_mult    REAL,
    heal_fraction  REAL,           -- 매 턴 회복량. 그래스필드 1/16
    note           TEXT
);

INSERT INTO terrains
    (name, ko_name, boost_type, boost_mult, weaken_type, weaken_mult, heal_fraction, note)
VALUES
    ('electric', '일렉트릭필드', 'electric', 1.3, NULL, NULL, NULL, '접지된 포켓몬은 잠듦 상태가 되지 않는다'),
    ('grassy', '그래스필드', 'grass', 1.3, NULL, NULL, 0.0625, '지진·땅고르기·매그니튜드의 위력 0.5배. 접지된 포켓몬이 매 턴 회복'),
    ('misty', '미스트필드', NULL, NULL, 'dragon', 0.5, NULL, '접지된 포켓몬은 상태이상·혼란에 걸리지 않는다'),
    ('psychic', '사이코필드', 'psychic', 1.3, NULL, NULL, NULL, '접지된 포켓몬에게 우선도 1 이상의 기술이 통하지 않는다');
