from starlette.types import ASGIApp
import marimo
import ast
import os
import importlib.util
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from fastapi import Request
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware



def get_global_metadata(target):
    """
    Returns only the global (module-level) docstring and the source code.
    """
    path = target
    
    # Resolve FQDN to file path if necessary
    if not os.path.exists(target):
        spec = importlib.util.find_spec(target)
        if spec and spec.origin:
            path = spec.origin
        else:
            return None, "Error: Target not found."

    try:
        with open(path, "r", encoding="utf-8") as f:
            source_code = f.read()
            
        tree = ast.parse(source_code)
        
        # ast.get_docstring specifically retrieves the 
        # docstring of the node passed (the Module root)
        global_doc = ast.get_docstring(tree)
        
        return global_doc
        
    except Exception as e:
        return None, f"Error: {e}"


# def feth_resource(url:str = None)->str:
#     witg 


def get_marimo_runner_old(src: str, internal_path: str = "") -> ASGIApp:
    # internal_path is *within* the mounted Marimo app, so usually ""
    
    version = marimo.__version__
    return (
        marimo.create_asgi_app(
            quiet=False,
            asset_url=f"https://cdn.jsdelivr.net/npm/@marimo-team/frontend@{version}/dist"
            #asset_url=f'/marimo_assets'
        )
        .with_dynamic_directory(path=internal_path, directory=src)
        .build()
    )
    



class MarimoStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Catch any request ending in these specific static files
        if path.endswith(("/manifest.json", "/favicon.ico", "/apple-touch-icon.png")):
            filename = os.path.basename(path)
            
            # Locate Marimo's base _static directory
            static_dir = os.path.join(os.path.dirname(marimo.__file__), "_static")
            file_path = os.path.join(static_dir, filename)
            
            # Serve it directly from disk, bypassing all routing!
            if os.path.exists(file_path):
                return FileResponse(file_path)
                
        return await call_next(request)




def get_marimo_runner(src: str, mount_point: str = None) -> ASGIApp:
    version = marimo.__version__
    # 1. Use the official, native Marimo builder
    marimo_server = (
        marimo.create_asgi_app(
            quiet=False,
            include_code=True,
            skew_protection=True,
            #asset_url=f"https://cdn.jsdelivr.net/npm/@marimo-team/frontend@{version}/dist"
        )
        .with_dynamic_directory(
            path=mount_point,  # Tell Marimo to expect "/apps"
            directory=src
        )
        .build()
    )

    # 2. The simple ASGI wrapper to fix FastAPI's path stripping
    async def prefix_restoring_app(scope, receive, send):
        if scope["type"] in ["http", "websocket"]:
            # FastAPI strips "/apps" from scope["path"] and puts it in scope["root_path"]
            # We put it back so Marimo's dynamic directory matcher sees the full URL
            path = scope.get("path", "")
            
            # Only add the prefix if it's not already there (safety check)
            if not path.startswith(mount_point):
                scope["path"] = f"{mount_point}{path}"
            
            # Clear root_path so Marimo relies entirely on the full path
            scope["root_path"] = ""
            
        await marimo_server(scope, receive, send)

    return prefix_restoring_app

