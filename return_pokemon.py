import psycopg2

import db
from translation import ko_to_en

DB_CONFIG = db.DB_CONFIG       #db.py에 정의된 DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

def main():
    print("알고 싶은 포켓몬의 이름을 입력하세요")
    korean_name=input("포켓몬의 이름: ")
    english_name=ko_to_en(korean_name)
    cur.execute(
        """
        SELECT * 
        FROM POKEMON 
        JOIN POKEMON_NAME ON POKEMON.NAME=POKEMON_NAME.EN_NAME 
        WHERE POKEMON.NAME = %s
        """,
        (english_name,),
    )
    rows = cur.fetchall()         
    for row in rows:
        print(row)              
    conn.close()

if __name__ == "__main__":
    main()