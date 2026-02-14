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


def check_auth(url:str=None, request: Request = None):
    # Pass the browser's cookies to the internal proxy service
    with httpx.Client() as client:
        try:
            headers = {
                "X-Forwarded-Proto": "https", # Tell the proxy "pretend this is secure"
                "X-Forwarded-Host": "localhost"
            }
            # Pass the cookies to the proxy
            response = client.get(url, cookies=request.cookies, headers=headers)
            
            # We know 202 is our success code localy!
            is_authenticated = response.status_code in [200, 202]
            
            if is_authenticated:
                # 1. Get the email
                email = response.headers.get('x-auth-request-email', 'Guest')
                
                # 2. Get the groups as a list
                groups_raw = response.headers.get('x-auth-request-groups', '')
                groups = [g.strip() for g in groups_raw.split(',')] if groups_raw else []
                
                # 3. Get the username
                username = response.headers.get('x-auth-request-user', 'iferencik')
                
                return {
                    "is_authenticated": True, 
                    "email": email, 
                    "groups": groups, 
                    "user": username
                }
        except Exception as e:
            logger.error(f"Auth Service unreachable: {e}")
            
    return {"is_authenticated": False}