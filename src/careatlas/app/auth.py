from fastapi import Request

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

