from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers import auth, me

app = FastAPI(title="ReportForge API")
app.include_router(auth.router)
app.include_router(me.router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    # Proves config, driver, network, authentication and permissions all work
    # together. This endpoint is public, so it must not reveal anything about the
    # database (user name, database name, version) to whoever asks.
    db.execute(text("select 1"))
    return {"status": "ok"}
