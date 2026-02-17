import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, WebSocket, APIRouter, WebSocketDisconnect
from nicegui import ui
from .auth import get_user_identity, is_authenticated, check_auth
from urllib.parse import urlparse,quote
import logging
from careatlas.app import marutil as mu
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from pathlib import Path
from starlette.routing import Mount
from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.datastructures import Headers
from marimo._utils.paths import marimo_package_path
import uuid
from careatlas.app.util import MarimoManager
import asyncio
import httpx
from fastapi_proxy_lib.core.http import ReverseHttpProxy
from fastapi_proxy_lib.core.websocket import ReverseWebSocketProxy
from fastapi_proxy_lib.fastapi.router import RouterHelper
import websockets



logging.basicConfig(level=logging.INFO)
# silence nicegui internal chatter
logging.getLogger("nicegui").setLevel(logging.WARNING)

logger = logging.getLogger()
# logger.name = 'careatlas'

# 1. Setup the Helper and APIRouter
helper = RouterHelper()
router = APIRouter(prefix="/edit")

AUTH_URL = f"{os.getenv('AUTH_URL')}/auth"
UPSTREAM_HOST = "127.0.0.1"
# Initialize the proxy engines
# Reusing the AsyncClient is critical for performance in Docker
async_client = httpx.AsyncClient()

# mount notebooks dynamically
BASE_DIR = Path(__file__).parent.parent.resolve() 
NOTEBOOKS_DIR = (BASE_DIR / "notebooks").resolve()


# --- Lifespan Logic ---

async def lifespan(app: FastAPI):
    # --- STARTUP ---
    logger.info("Starting Marimo Manager Reaper...")
    # Fire and forget the background task
    reaper_task = asyncio.create_task(manager.cleanup_loop(max_idle_seconds=10))
    #FIRST: Await the factory to get the actual context manager
    proxy_lifespan_factory = helper.get_lifespan()
    
    # SECOND: Create the context manager instance for this app
    proxy_cm = proxy_lifespan_factory(app)
    
    # THIRD: Enter the library's lifecycle
    async with proxy_cm:
        yield  # The app (and NiceGUI) runs here
    
    # --- SHUTDOWN ---
    logger.info("Shutting down: Killing all Marimo sessions...")
    reaper_task.cancel()
    try:
        # Give the reaper a second to stop, then nuke all sessions
        await asyncio.wait_for(reaper_task, timeout=2)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    
    manager.shutdown_all()
    logger.info("Marimo Manager shut down and sessions cleaned up.")


manager = MarimoManager()


app = FastAPI(title="UNDP CareAtlas", lifespan=lifespan)



def undp_vertical_mark():
    return ui.html("""
    <div style="width:56px; display:flex; flex-direction:column;">
      <div style="background:#006db0; padding:8px; display:flex; justify-content:center;">
        <img src="https://upload.wikimedia.org/wikipedia/commons/e/ee/UN_emblem_blue.svg"
             style="width:32px; height:32px; filter:brightness(0) invert(1);" />
      </div>
      <div style="
        background:#006db0;
        color:white;
        font-family:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
        font-size:14px;
        font-weight:600;
        letter-spacing:0.18em;
        text-align:center;
        padding:6px 0;
      ">
        UN<br>DP
      </div>
    </div>
    """)
    
    
# --- 2. UNDP Design System Theme & Assets ---
def apply_undp_theme():
    # Link to official UNDP Design System assets
    ui.add_head_html('''
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@undp/design-system-assets/css/base-minimal.min.css">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@undp/design-system-assets/css/components.min.css">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Saira:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root { --undp-blue: #006db0; }
            body { font-family: 'Saira', sans-serif !important; background-color: #f7f7f7; }
            .undp-card { border-radius: 0 !important; border: 1px solid #e0e0e0; box-shadow: none !important; }
            .undp-card:hover { border-color: var(--undp-blue); }
            .undp-btn { border-radius: 0 !important; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }
            .undp-logo-block { background-color: var(--undp-blue); width: 48px; height: 64px; }
            .animate-spin {
                animation: spin 0.8s linear infinite;
            }
            @keyframes spin {
                from { transform: rotate(0deg); }
                to   { transform: rotate(360deg); }
            }
            
            .force-spin { animation: spin 1s linear infinite !important; }
            @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        </style>
       
    
    ''')




    
#--- 3. UI Components (UNS Compliant) ---
def undp_header(request:Request=None):
    font_stack = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    with ui.header().classes('bg-white border-b border-gray-200'):
        with ui.row().classes(
            'w-full max-w-7xl mx-auto items-stretch justify-between h-20'
        ):

            # LEFT: UNDP mark + site identity
            with ui.row().classes('items-center gap-6'):
                undp_vertical_mark()

                with ui.column().classes('gap-0 cursor-pointer').on('click', lambda: ui.navigate.to('/')):
                    ui.label('Gender Team').style(
                        f"""
                        font-family:{font_stack};
                        font-size:12px;
                        font-weight:500;
                        letter-spacing:0.12em;
                        text-transform:uppercase;
                        color:#6b7280;
                        """
                    )
                    ui.label('CareAtlas').style(
                        f"""
                        font-family:{font_stack};
                        font-size:20px;
                        font-weight:600;
                        color:#111827;
                        line-height:1.2;
                        """
                    )
            # CENTER: navigation (optional)
            NAV = [
                ("WHO WE ARE", "/who-we-are"),
                ("WHAT WE DO", "/what-we-do"),
                ("OUR IMPACT", "/our-impact"),
                ("GET INVOLVED", "/get-involved"),
            ]
            with ui.row().classes('items-center gap-8'):
                for label, path in NAV:
                    ui.link(label, path).classes('no-underline').style("""
                        font-family:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                        font-size:13px;
                        font-weight:500;
                        letter-spacing:0.08em;
                        text-transform:uppercase;
                        color:#111827;
                    """)

            
            # --- RIGHT SIDE: User Menu (enterprise-style) ---
            with ui.row().classes('items-center gap-2'):

                # 1. This is your single source of truth from Docker/AKS
                auth_url = os.getenv('AUTH_URL', '/oauth2').rstrip('/')

                # 2. Internal Check: Always use the env var + /auth
                auth = check_auth(url=f"{auth_url}/auth", request=request)
                is_authenticated = auth['is_authenticated']
                email = 'Guest' if not is_authenticated else auth['email']
                color = 'green' if is_authenticated else 'grey'

                # 3. The "Browser" Fix: 
                # If the URL contains 'auth-proxy', the browser needs 'localhost' instead.
                # Otherwise (AKS), use the auth_url exactly as it is.
                target_host = auth_url.replace('auth-proxy', 'localhost') if 'auth-proxy' in auth_url else auth_url
                

                # 4. Build the redirect and final action
                u = urlparse(str(request.url))
                rd = f'{str(request.base_url).rstrip("/")}/{u.path.lstrip("/")}'
                if u.query: rd += f"?{u.query}"

                action = "sign_out" if is_authenticated else "start"
                final_url = f"{target_host}/{action}?rd={quote(rd, safe=':/%?=&')}"
                
                tooltip_text = f'Sign out \n{email} to {final_url}' if is_authenticated else f'Sign in {email}'
                
                #with ui.link(target=final_url).style('display: contents; text-decoration: none !important;'):
                with ui.element('div').style('display:block;text-decoration: none !important;'):
                    btn = ui.button(icon='account_circle') \
                    .props(f'flat round dense color={color}') \
                    .classes('w-9 h-9 hover:scale-110 transition') \
                    .tooltip(tooltip_text)
                    
                    async def go_auth():
                        # --- visual feedback ---
                        btn.props('loading')                # built-in quasar spinner overlay  
                        btn.props('icon=sync')              # change icon
                        btn.classes(add='animate-spin')     # rotation animation

                        await ui.run_javascript('await new Promise(r => requestAnimationFrame(r))')
                        # gives browser one paint frame

                        ui.navigate.to(final_url)

                    btn.on('click', go_auth)
                    
                
                    





def undp_layout(request: Request, title: str):
    """Encapsulates shared page logic to avoid repetition."""
    apply_undp_theme()
    identity = get_user_identity(request)
    # Note: Using identity['user'] consistently for the header
    undp_header(request=request)
    if title:
        with ui.column().classes('w-full max-w-7xl mx-auto px-6 lg:px-8'):
            ui.label(title).classes('text-4xl font-bold text-black uppercase mb-2')
            ui.element('div').classes('w-40 h-1 bg-[#006db0] mb-12')
            # This allows the specific page content to follow below

# --- 2. Cleaned Routes ---
@ui.page('/who-we-are')
def page_who_we_are(request: Request):
    undp_layout(request, "Who We Are")
    ui.label("Detailed information about our team and mission.")
    ui.label(str(request.url))
    ui.label(str(request.base_url))

@ui.page('/what-we-do')
def page_what_we_do(request: Request):
    undp_layout(request, "What We Do")
    ui.label("Explaining our core service offerings.")

@ui.page('/our-impact')
def page_our_impact(request: Request):
    undp_layout(request, "Our Impact")
    ui.label("Data and stories from the field.")

@ui.page('/get-involved')
def page_get_involved(request: Request):
    undp_layout(request, "Get Involved")
    ui.label("NOW OR NEVER")
    


@app.get("/edit/open/{notebook_name:path}") # Added :path for subfolders
def edit(notebook_name: str, request: Request):
   
    
    # 0. This is your single source of truth from Docker/AKS
    auth_url = AUTH_URL.rstrip('/')
   
    logger.error(auth_url)
    # 1. Identity & Auth Check
    auth=check_auth(url=auth_url, request=request, forward_headers=True)
   
    
    if not auth.get('is_authenticated'):
        # In a real app, maybe redirect to login instead of 403
        raise HTTPException(status_code=403, detail="Authentication required to edit.")
    #raise HTTPException(status_code=403, detail="Authentication required to edit.")
    # 2. Path Safety
    base_dir = Path(NOTEBOOKS_DIR).resolve()
    # Ensure .py extension is present
    full_name = notebook_name if notebook_name.endswith('.py') else f"{notebook_name}.py"
    notebook_path = (base_dir / full_name).resolve()
    
    if not notebook_path.exists() or base_dir not in notebook_path.parents:
        raise HTTPException(status_code=404, detail="Notebook not found or access denied")

    # 3. Idempotency: Join existing session if available
    existing = next((s for s in manager._sessions.values() if s.notebook_path == str(notebook_path)), None)
    if existing:
        return RedirectResponse(url=f"{existing.base_url}/")

    session_id = uuid.uuid4().hex[:8]

    try:
        # Start via manager - base_prefix matches our proxy route
        session = manager.start_session(
            session_id=session_id, 
            notebook=str(notebook_path),
            base_prefix="/edit"
        )
        return RedirectResponse(url=f"{session.base_url}/")
        
    except Exception as e:
        logger.error(f"Failed to launch notebook {notebook_name}: {e}")
        raise HTTPException(status_code=500, detail="Kernel startup failed")
    
@router.api_route("/{session_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def dynamic_marimo_http(request: Request, session_id: str, path: str):
    session = manager._sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404)

    manager.touch(session_id)
   
    # Overwrite the security-sensitive ones
    target_host = f"{UPSTREAM_HOST}:{session.port}"
    # 1. Convert existing headers to a standard mutable dictionary
    # This automatically includes all your X-Auth headers from oauth2-proxy
    custom_headers = dict(request.headers)

    # 2. Perform the DICT UPDATE for the internal proxy requirements
    custom_headers.update({
        "host": target_host,
        "origin": f"http://{target_host}",
        "referer": f"http://{target_host}/",
    })
    
    

    # 3. Repack the dict back into the request's internal ASGI scope
    # This is the "magic" that makes the proxy library see your changes
    request.scope["headers"] = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in custom_headers.items()
    ]
    request._headers = Headers(raw=request.scope["headers"])
   
    
    # 3. VERIFY: If this print doesn't show your email, the proxy won't either
    logger.info(f"Final verify before proxy call: {request.headers.get('x-auth-request-email')}")
    # Use the high-level class directly
    proxy = ReverseHttpProxy(base_url=f"http://{UPSTREAM_HOST}:{session.port}/", client=async_client)
    # FIX: Pass 'request' and 'path' as keyword arguments
    # We lstrip the internal path to avoid double slashes like '...:port//edit/...'
    full_internal_path = f"{session.base_url}/{path}".lstrip("/")
    
    return await proxy.proxy(request=request, path=full_internal_path)
    
    # # Forward the session-prefixed path Marimo expects
    # return await proxy.proxy(request, path=f"{session.base_url}/{path}")

class MarimoWSProxy(ReverseWebSocketProxy):
    """
    A specialized proxy that spoofs headers to bypass Marimo's security.
    """

    
    async def get_target_request_headers(self, websocket, **kwargs):
        # Get the original headers from the library
        headers = await super().get_target_request_headers(websocket, **kwargs)
        
        # SPOSTING: Make Marimo think the request is coming from itself
        # This kills the 403 Forbidden/Silent Disconnect
        target_host = f"{UPSTREAM_HOST}:{websocket.path_params.get('port', '8000')}" #TODO fix the port 
        headers["host"] = target_host
        headers["origin"] = f"http://{target_host}"
        # 2. THE 1002 FIX: Kill WebSocket compression extensions
        # This prevents the "Reserved bit set unexpectedly" error
        if "sec-websocket-extensions" in headers:
            del headers["sec-websocket-extensions"]
        
        return headers

@app.websocket("/edit/{session_id}/{path:path}")
async def dynamic_marimo_ws(websocket: WebSocket, session_id: str, path: str):
    session = manager._sessions.get(session_id)
    if not session:
        return # Session not found, close immediately

    manager.touch(session_id)
    
    # 1. Reconstruct the internal target (Translating: proxy_pass)
    query = f"?{websocket.query_params}" if websocket.query_params else ""
    # We use ws:// for the internal loopback connection
    target_url = f"ws://{UPSTREAM_HOST}:{session.port}{session.base_url}/{path}{query}"
    
    ws_headers = dict(websocket.headers)

    # 2. Translate Nginx headers: Host, Origin, and Forwarded-For
    # We make Marimo think the request is coming from its own local interface
    ws_headers = {
        "Host": f"{UPSTREAM_HOST}:{session.port}",
        "Origin": f"http://{UPSTREAM_HOST}:{session.port}",
        "X-Real-IP": websocket.client.host if websocket.client else UPSTREAM_HOST,
        "X-Forwarded-For": websocket.client.host if websocket.client else {UPSTREAM_HOST},
        "X-Forwarded-Proto": "ws",
        "Cookie": websocket.headers.get("cookie", "")
    }

    # 3. Extract Subprotocols (Important for Marimo's internal messaging)
    requested_protocols = websocket.headers.get("sec-websocket-protocol", "").split(",")
    requested_protocols = [p.strip() for p in requested_protocols if p.strip()]

    try:
        # 4. Connect to the internal Marimo instance
        # We disable compression here to ensure no 'Reserved Bit' 1002 errors
        async with websockets.connect(
            target_url, 
            additional_headers=ws_headers, 
            subprotocols=requested_protocols,
            compression=None 
        ) as target_ws:
            
            # 5. Accept the browser connection with the negotiated subprotocol
            await websocket.accept(subprotocol=target_ws.subprotocol)

            # 6. The "Raw Pipe" - Bidirectional data flow
            async def browser_to_marimo():
                try:
                    while True:
                        # Receive from browser, send to Marimo
                        msg = await websocket.receive()
                        if "text" in msg:
                            await target_ws.send(msg["text"])
                        elif "bytes" in msg:
                            await target_ws.send(msg["bytes"])
                except Exception:
                    pass # Handle disconnect silently

            async def marimo_to_browser():
                try:
                    async for message in target_ws:
                        # Receive from Marimo, send to browser
                        if isinstance(message, str):
                            await websocket.send_text(message)
                        else:
                            await websocket.send_bytes(message)
                except Exception:
                    pass # Handle disconnect silently

            # Run both tasks concurrently
            await asyncio.gather(browser_to_marimo(), marimo_to_browser())

    except Exception as e:
        logger.error(f"Marimo WS Tunnel failed: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass


@app.get("/heartbeat")
async def heartbeat():
    notebooks_exist = os.path.exists(str(NOTEBOOKS_DIR))
    files = os.listdir(str(NOTEBOOKS_DIR)) if notebooks_exist else []
    
    # Extract the routing table
    routes_snapshot = []
    for route in app.routes:
        route_info = {
            "path": getattr(route, "path", "unknown"),
            "name": getattr(route, "name", "unnamed"),
            "type": type(route).__name__
        }
        # If it's a Mount, we want to know what's inside
        if isinstance(route, Mount):
            route_info["is_mount"] = True
            # This confirms if it's Marimo or NiceGUI
            route_info["app_type"] = type(route.app).__name__
        
        routes_snapshot.append(route_info)

    return JSONResponse(content={
        "status": "alive",
        "notebooks_dir": str(NOTEBOOKS_DIR),
        "files_found": files,
        "fastapi_routes": routes_snapshot
    })
    
    
@ui.page('/')
@ui.page('/notebooks/{subpath:path}')
async def notebook_explorer(request: Request, subpath: str = ""):
    # 1. Setup UNDP Layout & Identity
    undp_layout(request, "Notebook Explorer")
    
    auth_data = check_auth(url=AUTH_URL, request=request)
    # Identify if user has Edit rights (authenticated users)
    can_edit = auth_data.get('is_authenticated', False)

    # 2. Resolve the directory to scan
    current_dir = (NOTEBOOKS_DIR / subpath).resolve()

    # Security: Prevent escaping the root directory
    if not str(current_dir).startswith(str(NOTEBOOKS_DIR)) or not current_dir.exists():
        ui.notify("Directory not found", type='negative')
        return ui.navigate.to('/')

    with ui.column().classes('w-full max-w-7xl mx-auto px-6 lg:px-8'):
        
        # 3. Breadcrumbs / "Back" Navigation
        if subpath:
            parent_path = Path(subpath).parent
            # Navigate back: if parent is '.', go to root '/'
            back_url = '/' if str(parent_path) == '.' else f'/notebooks/{parent_path}'
            
            with ui.row().classes('items-center mb-6 cursor-pointer group').on('click', lambda: ui.navigate.to(back_url)):
                ui.icon('arrow_back', color='[#006db0]').classes('group-hover:-translate-x-1 transition-transform')
                ui.label(f"Back to {parent_path if str(parent_path) != '.' else 'Root'}").classes('text-[#006db0] font-bold text-xs tracking-widest uppercase')

        # 4. The Grid
        with ui.grid(columns='1fr 1fr 1fr').classes('w-full gap-8'):
            # Filter: No hidden files, no __init__.py
            items = [
                item for item in current_dir.iterdir() 
                if not item.name.startswith('.') and item.name != "__init__.py"
            ]
            # Sort: Folders first, then files
            items.sort(key=lambda x: (not x.is_dir(), x.name))
            
            for item in items:
                
                rel_path = item.relative_to(NOTEBOOKS_DIR)
                name, _ = os.path.splitext(item.name)
                item_label = name.replace('_', ' ')
                
                if item.is_dir():
                    if '__' in item.name: continue
                    # --- FOLDER CARD ---
                    with ui.card().classes('undp-card p-0 overflow-hidden bg-white cursor-pointer hover:shadow-lg transition-shadow') \
                        .on('click', lambda p=rel_path: ui.navigate.to(f'/notebooks/{p}')):
                        ui.element('div').classes('w-full h-1 bg-[#006db0]')
                        with ui.column().classes('p-8 w-full'):
                            ui.icon('folder_shared', color='[#006db0]').classes('text-4xl mb-2')
                            ui.label(item_label).classes('text-xl font-bold text-gray-700 capitalize')
                            ui.label('Folder').classes('text-gray-400 text-[10px] tracking-widest uppercase font-bold')

                elif item.suffix == '.py':
                    # --- NOTEBOOK CARD ---
                    with ui.card().classes('undp-card p-0 overflow-hidden bg-white'):
                        # Green accent for notebooks
                        ui.element('div').classes('w-full h-1 bg-green-500')
                        with ui.column().classes('p-8 w-full'):
                            with ui.row().classes('items-center gap-2 mb-2'):
                                ui.icon('dashboard', color='[#006db0]').classes('text-2xl')
                                ui.label('Notebook').classes('text-[#006db0] text-sm font-bold tracking-widest uppercase')
                            
                            # Fetch metadata (description) from the file
                            descr = mu.get_global_metadata(str(item.absolute()))
                            ui.label(descr or "No description available.").classes('text-sm mb-6 text-gray-500 line-clamp-2 h-10')
                            # Standard slug: 'folder/name'
                            marimo_slug = str(rel_path).replace('.py', '').replace(os.sep, '/').strip('/')
                            
                            # Calculate relative path jump to root (../../ etc)
                            # This ensures links work regardless of folder depth
                            depth = str(rel_path).count('/')
                            r = "../" * (depth + 1)
                            
                            with ui.row().classes('w-full justify-center mt-auto'):
                                # This wrapper defines the “middle” area and width budget for buttons
                                with ui.row().classes('w-full max-w-[360px] gap-2 flex-nowrap'):
                                    if can_edit:
                                        # 2 buttons, equal widths
                                        ui.button(
                                            'Launch',
                                            on_click=lambda s=marimo_slug, r=r: ui.navigate.to(f'{r}apps/{s}')
                                        ).classes('undp-btn primary text-white flex-1 w-1/2 capitalize') \
                                        .tooltip(f'View as interactive app at {r}apps/{marimo_slug}')

                                        ui.button(
                                            'Edit',
                                            on_click=lambda s=marimo_slug, r=r: ui.navigate.to(f'{r}edit/open/{s}')
                                        ).classes('undp-btn bg-[#006db0] text-white flex-1 w-1/2 capitalize') \
                                        .tooltip(f'Open in Editor mode (Spawns kernel) to {r}edit/open/{marimo_slug}')

                                    else:
                                        # 1 button, centered in the same max width wrapper
                                        ui.button(
                                            'Launch',
                                            on_click=lambda s=marimo_slug, r=r: ui.navigate.to(f'{r}apps/{s}')
                                        ).classes('undp-btn primary text-white justify w-[180px] capitalize') \
                                        .tooltip(f'View as interactive app at {r}apps/{marimo_slug}')
                                                        
                            
                            
                            # with ui.row().classes('w-full gap-2 mt-auto'):
                            #     # Standard slug: 'folder/name'
                            #     marimo_slug = str(rel_path).replace('.py', '').replace(os.sep, '/').strip('/')
                                
                            #     # Calculate relative path jump to root (../../ etc)
                            #     # This ensures links work regardless of folder depth
                            #     depth = str(rel_path).count('/')
                            #     r = "../" * (depth + 1)
                               
                            #     # 1. Launch Button (Read-only App mode)
                            #     ui.button('Launch', on_click=lambda s=marimo_slug, r=r: ui.navigate.to(f'{r}apps/{s}')) \
                            #         .classes('undp-btn primary text-white flex-1 capitalize max-w-[100px] ') \
                            #         .tooltip(f'View as interactive app at {r}apps/{marimo_slug}')
                                
                            #     # 2. Edit Button (Full interactive Editor)
                            #     if can_edit:
                            #         # Routes to the FastAPI 'open' endpoint which spawns the kernel
                            #         ui.button('Edit', on_click=lambda s=marimo_slug, r=r: ui.navigate.to(f'{r}edit/open/{s}')) \
                            #             .classes('undp-btn bg-[#006db0] text-white flex-1 capitalize') \
                            #             .tooltip(f'Open in Editor mode (Spawns kernel) to {r}edit/open/{marimo_slug}')
                            #     # else:
                            #     #     # Locked state for unauthenticated users
                            #     #     ui.button('Edit', icon='lock') \
                            #     #         .classes('undp-btn bg-gray-100 text-gray-400 flex-1 capitalize') \
                            #     #         .props('disable') \
                            #     #         .tooltip('Sign in to access the editor')



@app.middleware("http")
async def redirect_slash(request: Request, call_next):
    path = request.url.path

    # canonicalize /explorer -> /explorer/
    if path == "/explorer":
        return RedirectResponse(url="/explorer/", status_code=308)

    # canonicalize / -> /explorer/
    if path == "/":
        return RedirectResponse(url="/explorer/", status_code=308)

    return await call_next(request)


 
ui.run_with(
    app, 
    storage_secret=os.getenv("NICEGUI_STORAGE_SECRET"),
    title="UNDP CareAtlas",
    mount_path='/explorer'
)
marimo_server = mu.get_marimo_runner(src=str(NOTEBOOKS_DIR), internal_path="/apps")
app.include_router(router)
app.mount("/", marimo_server)



