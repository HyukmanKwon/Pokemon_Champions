CREATE TABLE status_conditions (
    name          VARCHAR(20) PRIMARY KEY,  -- burn, paralysis ... moves.ailment 과 대응
    ko_name       VARCHAR(20),
    attack_mult   REAL,      -- 물리공격 보정. 화상 0.5
    speed_mult    REAL,      -- 스피드 보정. 마비 0.5
    turn_damage   REAL,      -- 매 턴 최대 HP의 몇 배를 잃는가
    immobile      BOOLEAN,   -- 행동 자체가 막히는가 (잠듦·얼음)
    fail_chance   REAL,      -- 행동이 실패할 확률. 마비 0.25
    note          TEXT
);

INSERT INTO status_conditions
    (name, ko_name, attack_mult, speed_mult, turn_damage, immobile, fail_chance, note)
VALUES
    ('burn', '화상', 0.5, NULL, 0.0625, false, NULL, '물리공격 0.5배. 불꽃 타입은 걸리지 않는다'),
    ('paralysis', '마비', NULL, 0.5, NULL, false, 0.25, '행동 실패 25%. 전기 타입은 걸리지 않는다'),
    ('poison', '독', NULL, NULL, 0.125, false, NULL, '독·강철 타입은 걸리지 않는다'),
    ('toxic', '맹독', NULL, NULL, NULL, false, NULL, '턴마다 1/16씩 누적. n턴째 n/16'),
    ('sleep', '잠듦', NULL, NULL, NULL, true, NULL, '1~3턴. 잠꼬대·코골기만 사용 가능'),
    ('freeze', '얼음', NULL, NULL, NULL, true, NULL, '매 턴 20% 확률로 해동. 얼음 타입은 걸리지 않는다'),
    ('confusion', '혼란', NULL, NULL, NULL, false, 0.33, '부가 상태. 33% 확률로 자신을 공격');
