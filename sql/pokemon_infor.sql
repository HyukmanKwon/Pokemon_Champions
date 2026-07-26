CREATE TYPE POKEMON_TYPE AS ENUM (
    'normal', 'fire', 'water', 'electric', 'grass', 'ice', 'fighting',
    'poison', 'ground', 'flying', 'psychic', 'bug', 'rock', 'ghost',
    'dragon', 'dark', 'steel', 'fairy'
);

CREATE TABLE IF NOT EXISTS POKEMON
(
    POKEMON_ID INT,
    NAME VARCHAR(50) PRIMARY KEY,
    TYPE1 POKEMON_TYPE NOT NULL,
    TYPE2 POKEMON_TYPE,
    ABILITY1 VARCHAR(50),
    ABILITY2 VARCHAR(50),
    ABILITY3 VARCHAR(50),
    HEIGHT FLOAT,
    WEIGHT FLOAT,
    H INT,
    A INT,
    B INT,
    C INT,
    D INT,
    S INT,
    TOTAL INT
);
