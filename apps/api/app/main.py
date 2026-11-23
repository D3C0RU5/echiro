from fastapi import FastAPI

app = FastAPI(title="echiro API")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "echiro-api"}
