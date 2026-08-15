from fastapi import FastAPI
from app.core.errors import register_errors

app = FastAPI(title="NEXUS CRM")
register_errors(app)


@app.get("/api/v1/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
