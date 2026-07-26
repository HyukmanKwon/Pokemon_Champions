INSERT INTO pokemon
    (pokemon_id, name, type1, type2, ability1, ability2, ability3,
     height, weight, h, a, b, c, d, s, total)
VALUES
    (678, 'meowstic-mega',        'psychic', NULL, 'trace',        NULL, NULL, 0.3,  8.5,  74,  48,  76, 143, 101, 124, 566),
    (670, 'floette-eternal-mega', 'fairy',   NULL, 'fairy-aura',   NULL, NULL, 0.2,  0.9,  74,  85,  87, 155, 148, 102, 651),
    (964, 'palafin-hero',         'water',   NULL, 'zero-to-hero', NULL, NULL, 1.8, 97.4, 100, 160,  97, 106,  87, 100, 650)
ON CONFLICT (name) DO UPDATE SET
    type1    = EXCLUDED.type1,
    type2    = EXCLUDED.type2,
    ability1 = EXCLUDED.ability1,
    ability2 = EXCLUDED.ability2,
    ability3 = EXCLUDED.ability3,
    height   = EXCLUDED.height,
    weight   = EXCLUDED.weight,
    h = EXCLUDED.h, a = EXCLUDED.a, b = EXCLUDED.b,
    c = EXCLUDED.c, d = EXCLUDED.d, s = EXCLUDED.s,
    total    = EXCLUDED.total;