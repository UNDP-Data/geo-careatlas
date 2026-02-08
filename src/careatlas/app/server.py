from fastapi import FastAPI
import os

app = FastAPI(title="Geo-CareAtlas API")

@app.get("/")
async def root():
    return {
        "app": "UNDP CareAtlas",
        "version": "2026.02.08",
        "hosted": "AKS1",
        "repo": "https://github.com/UNDP-Data/geo-careatlas",
        "container_path": os.getcwd()
    }

@app.get("/health")
async def health():
    return {"status": "up", "environment": "production"}