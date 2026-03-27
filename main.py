from sqlite3 import Connection

from fastapi import Depends, FastAPI
from app.setup_database.setup_db import get_connection
from app.routes import admin

app = FastAPI()
app.include_router(admin.router)


@app.get("/health")
def get_health():
    return {"health": "ok"}


@app.get("/check-db")
def check_db(con: Connection = Depends(get_connection)):
    cursor = con.cursor()
    cursor.execute("Select 1")
    result = cursor.fetchall()
    return result
