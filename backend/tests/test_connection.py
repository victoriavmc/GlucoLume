# 1ER TEST DE CONEXIÓN A LA BASE DE DATOS SQL SERVER

import os

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text

load_dotenv()

url = URL.create(
    "mssql+pyodbc",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", "1435")),
    database=os.getenv("DB_NAME"),
    query={
        "driver": "ODBC Driver 18 for SQL Server",
        "TrustServerCertificate": "yes",
    },
)

try:
    engine = create_engine(url)

    with engine.connect() as connection:
        database = connection.execute(text("SELECT DB_NAME()")).scalar()

        print("✅ Conexión exitosa")
        print(f"✅ Base conectada: {database}")

except Exception as error:
    print("❌ Error al conectar")
    print(error)