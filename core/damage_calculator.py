"""
damage()    -- 데미지 계산하는 함수
defense()   -- 내구력 계산하는 함수
result()    -- 데미지와 내구력을 바탕으로 결과 예측(난수 2타, 확정 1타 등등)

"""
import psycopg2
from .database import db

DB_CONFIG = db.DB_CONFIG       #db.py에 정의된 DB_CONFIG
MAX_SP = 66                    #SP의 최대 투자가능치 

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

def damage():
    #실능치 * 기술 위력 * 자속 보정 * 특성 보정 * 상성 * 날씨 보정 * 도구 보정

def defense():
    #

def result():
    damage = damage()
    defense = defense()
    #계산