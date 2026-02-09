from fastapi import FastAPI, Header
from typing import Annotated, Optional
import os

app = FastAPI(title="UNDP CareAtlas API")

@app.get("/")
@app.get("")
async def root(
    # # These headers are injected by the OAuth2 Proxy upon successful GH login
    # # Try both standard proxy header names
    # user: Annotated[Optional[str], Header(alias="x-forwarded-user")] = None,
    # email: Annotated[Optional[str], Header(alias="x-forwarded-email")] = None,
    # # Backup: The ones you already had
    # auth_user: Annotated[Optional[str], Header(alias="x-auth-request-user")] = None,
    # auth_email: Annotated[Optional[str], Header(alias="x-auth-request-email")] = None,
    user: Annotated[Optional[str], Header(alias="x-forwarded-user")] = None,
    email: Annotated[Optional[str], Header(alias="x-forwarded-email")] = None,
    # The groups header name can vary, this is the most common for GH teams
    groups: Annotated[Optional[str], Header(alias="x-forwarded-groups")] = None,
    
):
    return {
        "app": "UNDP CareAtlas",
        "auth": {
            "user": user,
            "email": email,
            "teams": groups.split(",") if groups else []
            
        },
        "version": "2026.02.09",
        "env": os.getenv("APP_ENV", "dev"),
        "container_path": os.getcwd()
    }

@app.get("/health")
async def health():
    return {"status": "up"}