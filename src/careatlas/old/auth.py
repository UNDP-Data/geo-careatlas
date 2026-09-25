from fastapi import Request
import httpx
from nicegui import ui
import logging
logger = logging.getLogger(__name__)


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

def check_auth(url: str, request: Request, forward_headers=False):

    with httpx.Client(timeout=3.0) as client:
        try:
            headers = {
                # Use the actual scheme/host the browser used
                "X-Forwarded-Proto": request.headers.get("x-forwarded-proto", request.url.scheme),
                "X-Forwarded-Host": request.headers.get("x-forwarded-host", request.headers.get("host", "")),
                "X-Forwarded-Uri": request.url.path + (("?" + request.url.query) if request.url.query else ""),
            }

            # Also forward original User-Agent (optional but helps some setups)
            ua = request.headers.get("user-agent")
            if ua:
                headers["User-Agent"] = ua

            # Forward cookies exactly
            response = client.get(url, cookies=request.cookies, headers=headers)

            if response.status_code in (200, 202):
                email = response.headers.get("x-auth-request-email", "Guest")
                groups_raw = response.headers.get("x-auth-request-groups", "")
                groups = [g.strip() for g in groups_raw.split(",")] if groups_raw else []
                username = response.headers.get("x-auth-request-user", "")
                
                if forward_headers:
                    # 1. Extract the identity headers from the HTTPX response
                    auth_headers = {
                        "x-auth-request-email": response.headers.get("x-auth-request-email", "Guest"),
                        "x-auth-request-user": response.headers.get("x-auth-request-user", ""),
                        "x-auth-request-groups": response.headers.get("x-auth-request-groups", ""),
                    }
                    current_headers = dict(request.headers)
                    current_headers.update(auth_headers)
                    request.scope["headers"] = [
                        (k.lower().encode("latin-1"), v.encode("latin-1"))
                        for k, v in current_headers.items()
                    ]
                    if hasattr(request, "_headers"):
                       
                        delattr(request, "_headers")
                   
                
                return {"is_authenticated": True, "email": email, "groups": groups, "user": username}
            
        except Exception as e:
            logger.error(f"Auth Service unreachable: {e}")

    return {"is_authenticated": False}
