CREATE TABLE stat_stages (
    stage          INT PRIMARY KEY,   -- -6 ~ +6
    battle_mult    REAL NOT NULL,     -- a b c d s 에 적용
    accuracy_mult  REAL NOT NULL      -- 명중률·회피율에 적용
);

INSERT INTO stat_stages
    (stage, battle_mult, accuracy_mult)
VALUES
    ( -6, 0.25, 0.3333),
    ( -5, 0.2857, 0.375),
    ( -4, 0.3333, 0.4286),
    ( -3, 0.4, 0.5),
    ( -2, 0.5, 0.6),
    ( -1, 0.6667, 0.75),
    (0, 1.0, 1.0),
    (1, 1.5, 1.3333),
    (2, 2.0, 1.6667),
    (3, 2.5, 2.0),
    (4, 3.0, 2.3333),
    (5, 3.5, 2.6667),
    (6, 4.0, 3.0);
