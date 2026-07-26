import os #OS 연동

DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE", "pokemon"),
    "user": os.getenv("PGUSER", "hyukman"),
    "password": os.getenv("PGPASSWORD", ""),
}