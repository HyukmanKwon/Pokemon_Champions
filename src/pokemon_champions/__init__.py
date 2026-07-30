"""포켓몬 챔피언스 (레귤레이션 M-B) 코어 패키지.

계층은 아래 한 방향으로만 흐른다. 역방향 import 는 없다.

    interfaces  ->  services  ->  db.repositories  ->  db.connection
                       |
                    domain (아무것도 import 하지 않는다)

ETL(scripts/etl) 은 이 패키지를 import 해도 되지만, 이 패키지는
scripts 를 절대 import 하지 않는다.
"""

__all__ = []
