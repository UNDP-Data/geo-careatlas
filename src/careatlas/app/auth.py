from fastapi import Request
import httpx
from nicegui import ui



def is_authenticated(identity: dict):
    # Returns True if we have a real email, False if it's the default "Guest User"
    return identity.get("email") and identity["email"] != "Guest User"


def get_user_identity(request: Request):
    """Checks both potential header prefixes (AKS vs Local Docker)."""
    h = request.headers
    
    # Try AKS/Auth-Request style, then Local/Forwarded style
    email = h.get("x-auth-request-email") or h.get("x-forwarded-email")
    user = h.get("x-auth-request-user") or h.get("x-forwarded-user")
    
    # Do the same for groups if you need them
    groups_raw = h.get("x-auth-request-groups") or h.get("x-forwarded-groups") or ""
    groups = [g.strip() for g in groups_raw.split(",") if g.strip()]

    return {
        "email": email or "Guest User",
        "user": user or "Guest",
        "groups": groups
    }


def check_auth(url:str=None, request: Request = None):
    # Pass the browser's cookies to the internal proxy service
    with httpx.Client() as client:
        try:
            resp = client.get(url=url, headers={"Cookie": request.headers.get("cookie", "")})
            if resp.status_code == 200:
                return {
                    "user": resp.headers.get("x-auth-request-user"),
                    "email": resp.headers.get("x-auth-request-email"),
                    "is_authenticated": True
                }
        except Exception as e:
            print(f"Auth Service unreachable: {e}")
            
    return {"is_authenticated": False}