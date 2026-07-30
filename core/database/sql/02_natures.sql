CREATE TYPE pokemon_natures_enum AS ENUM ('lonely', 'brave', 'adamant', 'naughty', 'bold', 'relaxed', 'impish', 'lax', 'timid', 'hasty', 'jolly', 'naive', 'modest', 'mild', 'quiet', 'rash', 'calm', 'gentle', 'sassy', 'careful', 'serious');

CREATE TABLE pokemon_natures (
    en_name  pokemon_natures_enum PRIMARY KEY,
    ko_name  VARCHAR(50),
    up       CHAR(1),          -- 1.1배가 되는 능력치, 성실은 NULL
    down     CHAR(1)           -- 0.9배가 되는 능력치, 성실은 NULL
);

INSERT INTO pokemon_natures
    (en_name, ko_name, up, down)
VALUES
    ('lonely', '외로움', 'a', 'b'),
    ('brave', '용감', 'a', 's'),
    ('adamant', '고집', 'a', 'c'),
    ('naughty', '개구쟁이', 'a', 'd'),
    ('bold', '대담', 'b', 'a'),
    ('relaxed', '무사태평', 'b', 's'),
    ('impish', '장난꾸러기', 'b', 'c'),
    ('lax', '촐랑', 'b', 'd'),
    ('timid', '겁쟁이', 's', 'a'),
    ('hasty', '성급', 's', 'b'),
    ('jolly', '명랑', 's', 'c'),
    ('naive', '천진난만', 's', 'd'),
    ('modest', '조심', 'c', 'a'),
    ('mild', '의젓', 'c', 'b'),
    ('quiet', '차분', 'c', 's'),
    ('rash', '덜렁', 'c', 'd'),
    ('calm', '온순', 'd', 'a'),
    ('gentle', '얌전', 'd', 'b'),
    ('sassy', '건방', 'd', 's'),
    ('careful', '신중', 'd', 'c'),
    ('serious', '성실', NULL, NULL);
