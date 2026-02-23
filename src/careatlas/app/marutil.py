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
    



def get_marimo_runner(src: str, internal_path: str = "") -> ASGIApp:
    # 1. Build the Marimo app normally
    marimo_server = (
        marimo.create_asgi_app(
            quiet=False, 
            asset_url=internal_path # HTML will request /apps/assets/...
        )
        .with_dynamic_directory(path=internal_path, directory=src)
        .build()
    )

    # 2. Locate Marimo's physical static assets folder
    marimo_static_dir = os.path.join(os.path.dirname(marimo.__file__), "_static", "assets")

    # 3. Extract Marimo's base Starlette app from inside the middleware
    base_starlette_app = marimo_server.app 

    # 4. Monkey patch the router! 
    # Insert at index 0 so it intercepts the asset requests before the catch-all routes
    base_starlette_app.routes.insert(
        0, 
        Mount("/assets", app=StaticFiles(directory=marimo_static_dir), name="patched_assets")
    )

    return marimo_server


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