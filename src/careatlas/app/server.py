import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from nicegui import ui, app as ui_app
from .auth import check_auth
from urllib.parse import urlparse,quote
import logging
from careatlas.app import marutil as mu
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from pathlib import Path
from starlette.routing import Mount
import uuid
from careatlas.app.util import MarimoManager
import asyncio
import httpx
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

# This syncs the duality. 
# It tells the app to use the 'X-Forwarded' headers sent by your proxy.





logging.basicConfig(level=logging.INFO)
# silence nicegui internal chatter
logging.getLogger("nicegui").setLevel(logging.WARNING)

logger = logging.getLogger()
# logger.name = 'careatlas'

UNDP_RED = "#E5243B"
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
    # STARTUP: Start the background 'maintenance' task
    # This loop handles the 1800s timeout and the zombie cleanup
    reaper_task = asyncio.create_task(manager.cleanup_loop(max_idle_seconds=1800))
    
    yield  # The NiceGUI app runs here
    
    # SHUTDOWN: Fast break for Docker
    reaper_task.cancel()
    
    manager.shutdown_all()

manager = MarimoManager()


app = FastAPI(title="UNDP CareAtlas", lifespan=lifespan)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

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
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" rel="stylesheet" />
        <style>
            :root { 
                --undp-blue: #006db0; 
                --undp-red: #E5243B; /* Added the official red here */
            }
            
            body { font-family: 'Saira', sans-serif !important; background-color: #f7f7f7; }
            
            .undp-card {
                transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); /* Bouncy feel */
                border: 2px solid transparent;
                z-index: 1; /* Base layer */
            }

            .undp-card:hover {
                /* 1. Scale up 3% in all directions */
                transform: scale(1.01); 
                
                /* 2. Layered shadow for depth */
                box-shadow: 0 15px 30px rgba(0,0,0,0.12), 0 10px 10px rgba(0,0,0,0.06);
                
                /* 3. Ensure it overlaps neighbors */
                z-index: 10; 
                
                /* 4. Keep your hover border */
                border: 2px solid #e0e0e0;
            }
            
            .undp-btn { border-radius: 0 !important; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }
            
            /* Assuming the main logo stays blue, but you can change this to var(--undp-red) too! */
            .undp-logo-block { background-color: var(--undp-blue); width: 48px; height: 64px; } 
            
            /* Consolidated your spin animations */
            .animate-spin, .force-spin {
                animation: spin 0.8s linear infinite !important;
            }
            
            @keyframes spin {
                from { transform: rotate(0deg); }
                to   { transform: rotate(360deg); }
            }
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
                ("OUR APPS", "/"),
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
            # --- RIGHT SIDE: Identity + Actions ---
            with ui.row().classes('items-center gap-2'):

                # 1. Internal Auth Check
                internal_auth_base = "http://auth-proxy:4180/oauth2"
                auth = check_auth(url=f"{internal_auth_base}/auth", request=request)
                is_authenticated = auth.get('is_authenticated', False)
                email = auth.get('email', 'Guest')
                
                # 2. Setup Redirection Logic
                auth_url = os.getenv('AUTH_URL', '/oauth2').rstrip('/')
                target_host = auth_url.replace('auth-proxy', 'localhost') if 'auth-proxy' in auth_url else auth_url
                u = urlparse(str(request.url))
                rd = f'http://localhost:8080{u.path}'
                if u.query: rd += f"?{u.query}"
                
                action = "sign_out" if is_authenticated else "start"
                final_url = f"{target_host}/{action}?rd={quote(rd, safe=':/%?=&')}"

                # --- BUTTON 1: THE IDENTITY BUTTON (Your "Cool" Original) ---
                with ui.element('div'):
                    identity_btn = ui.button(icon='account_circle') \
                        .props(f'flat round dense color={"green" if is_authenticated else "grey"}') \
                        .classes('w-9 h-9 hover:scale-110 transition') \
                        .tooltip(f'Connected as {email}' if is_authenticated else 'Sign In')
                    
                    async def go_auth():
                        identity_btn.props('loading icon=sync')
                        identity_btn.classes(add='animate-spin')
                        await ui.run_javascript('await new Promise(r => requestAnimationFrame(r))')
                        
                        ui.navigate.to(final_url)

                    identity_btn.on('click', go_auth)

                # --- BUTTON 2: THE MANAGEMENT MENU (Second Button) ---
                
                if is_authenticated:
                    # Subtle vertical divider
                    ui.element('div').classes('w-[1px] h-6 bg-gray-300 mx-1')

                    # Session Manager Icon
                    ui.button(icon='dns').props('color="[#E5243B]"') \
                        .props('flat round dense') \
                        .classes('w-9 h-9 hover:scale-110 hover:text-[#E5243B] transition') \
                        .tooltip('Session Manager') \
                        .on('click', lambda: ui.navigate.to('/sessions'))

                    # System Settings Icon
                    ui.button(icon='tune').props('color="[#E5243B]"') \
                        .props('flat round dense') \
                        .classes('w-9 h-9 hover:scale-110 hover:text-[#E5243B] transition') \
                        .tooltip('System Settings') \
                        .on('click', lambda: ui.navigate.to('/settings'))
                
                
        

def undp_layout(request: Request, title: str):
    """Encapsulates shared page logic to avoid repetition."""
    apply_undp_theme()
    
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
    with ui.column().classes('w-full max-w-7xl mx-auto px-6 lg:px-8'):
        ui.label("Detailed information about our team and mission.")
        ui.label(str(request.url))
        ui.label(str(request.base_url))

@ui.page('/what-we-do')
def page_what_we_do(request: Request):
    undp_layout(request, "What We Do")
    with ui.column().classes('w-full max-w-7xl mx-auto px-6 lg:px-8'):
        ui.label("Explaining our core service offerings.")

@ui.page('/our-impact')
def page_our_impact(request: Request):
    undp_layout(request, "Our Impact")
    with ui.column().classes('w-full max-w-7xl mx-auto px-6 lg:px-8'):
        ui.label("Data and stories from the field.")

@ui.page('/get-involved')
def page_get_involved(request: Request):
    undp_layout(request, "Get Involved")
    with ui.column().classes('w-full max-w-7xl mx-auto px-6 lg:px-8'):
        ui.label("NOW OR NEVER")
    


    
@app.get("/edit/open/{notebook_name:path}") # Added :path for subfolders
def edit(notebook_name: str, request: Request):
   
    
    # 0. This is your single source of truth from Docker/AKS
    auth_url = AUTH_URL.rstrip('/')
   
    logger.error(auth_url)
    # 1. Identity & Auth Check
    auth=check_auth(url=AUTH_URL.replace('localhost', 'auth-proxy'), request=request, forward_headers=True)
   
    
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
    # 1. Join existing or Start new session
    existing = next((s for s in manager._sessions.values() if s.notebook_path == str(notebook_path)), None)
    
    if existing:
        # Include PORT in the URL so mitmproxy can route it
        response = RedirectResponse(url=f"/edit/{existing.session_id}/", headers=request.headers)
        response.set_cookie(
            key=f"marimo_port_{existing.session_id}", 
            value=str(existing.port),
            path=f"/",
            max_age=14400,  # 4 hours
            samesite="lax",
            secure=True  # Ensure this is True for AKS/HTTPS
            
        )
        return response

    session_id = uuid.uuid4().hex[:8]
    try:
        session = manager.start_session(
            session_id=session_id, 
            notebook=str(notebook_path),
            # Marimo base_prefix should match the path AFTER the port is stripped
            base_prefix=f"/edit",
            identity=auth
        )
        
        # Include PORT in the URL so mitmproxy can route it
        response = RedirectResponse(url=f"/edit/{session_id}/")
        response.set_cookie(
            key=f"marimo_port_{session.session_id}", 
            value=str(session.port),
            path=f"/",
            max_age=14400,  # 4 hours
            samesite="lax",
            secure=True  # Ensure this is True for AKS/HTTPS
            
        )
        return response
        
        
    except Exception as e:
        logger.error(f"Failed to launch: {e}")
        raise HTTPException(status_code=500, detail="Kernel startup failed")

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
    
    auth_data = check_auth(url=AUTH_URL.replace('localhost', 'auth-proxy'), request=request)
   
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
                                        .tooltip(f'View as interactive app at {r}/apps/{marimo_slug}')

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


@ui.page('/settings')
async def settings(request: Request):
    undp_layout(request, "Settings")
    with ui.column().classes('w-full max-w-7xl mx-auto px-6 lg:px-8'):
        ui.label('Here come settings')
    


@ui.page('/sessions')
async def sessions(request: Request):
    # 1. Identity & Auth Check
    auth_url_internal = "http://auth-proxy:4180/oauth2"
    auth = check_auth(url=f"{auth_url_internal}/auth", request=request)
    
    if not auth.get('is_authenticated'):
        return RedirectResponse(url='/explorer/')
        
    # 2. Apply your standard header and layout
    undp_layout(request, "Marimo Manager")
    
    # 3. Main Container
    with ui.column().classes('w-full max-w-7xl mx-auto px-6 lg:px-8 gap-6 pb-12'):
        
        # Header Row
        with ui.row().classes('w-full justify-between items-center p-4 mb-8 bg-gray-50  border border-gray-200 shadow-sm'):
            ui.label('Active Marimo Sessions').classes('text-xl font-bold text-gray-800')
            with ui.row().classes('items-center gap-1'):
                ui.button(icon='refresh', on_click=lambda: refresh_list()) \
                    .props('flat round').classes('text-xs font-bold tracking-wider')\
                    .tooltip('Refresh')
                # Solid 'Delete All' Button
                ui.button(icon='delete_forever', on_click=lambda: kil_all_sessions()) \
                    .props(f'flat round color="[#E5243B]"') \
                    .tooltip('Delete All Sessions')

        # The empty container where the cards will be injected
        list_container = ui.column().classes('w-full gap-4')
        
        async def kil_all_sessions():
            sids = list(manager._sessions.keys())
            for sid in sids:
                await kill_session(sid)
        

        # 4. Async logic to handle the termination without losing the UI slot
        async def kill_session(session_id: str):
            session = manager._sessions.get(session_id)
            if session:
                # 1. Clear the cookie FIRST while the UI context is still valid
                cookie_name = f'marimo_port_{session_id}'
                # # Using JavaScript to target the "/" path specifically
                ui.run_javascript(f'document.cookie = "{cookie_name}=; Path=/; Max-Age=-99999999;"')
                
                # 2. Kill the Process (Parent + Child)
                manager.stop_session(session_id=session_id)
                
                # 3. Notify the user
                ui.notify(f"Terminated session {session_id}", type='warning', icon='delete')
                await asyncio.sleep(0.1)
                # 4. Refresh the UI LAST
                refresh_list()
                

        # 5. UI Rendering logic
        def refresh_list():
            list_container.clear()
            
            if not manager._sessions:
                with list_container:
                    ui.label("No active kernels running.").classes('text-gray-400 italic mt-4')
                return

            with list_container:
                for sid, s in manager._sessions.items():
                    is_alive = s.proc and s.proc.poll() is None
                    status_color = 'bg-green-500' if is_alive else 'bg-red-500'
                    nb_rel_path=str(Path(s.notebook_path).relative_to(NOTEBOOKS_DIR))
                    
                    # Sleek horizontal card for each session
                    with ui.card().classes('undp-card w-full p-0 flex flex-row items-center justify-between overflow-hidden bg-white'):
                        
                        # Left side: Color indicator + Info
                        with ui.row().classes('items-center gap-0 w-2/3'):
                            ui.element('div').classes(f'w-2 h-20 {status_color}')
                            
                            with ui.row().classes('items-center gap-4 pl-4 py-2'):
                                ui.icon('terminal', color='[#E5243B]').classes('text-2xl opacity-80')
                                
                                with ui.column().classes('gap-0'):
                                    ui.label(nb_rel_path).classes('font-bold text-lg text-gray-800')
                                    
                                    # Meta info row
                                    with ui.row().classes('gap-3 items-center mt-1'):
                                        ui.label(f"ID: {sid}").classes('text-xs text-gray-500 font-mono bg-gray-100 px-2 py-0.5 rounded')
                                        ui.label(f"Port: {s.port}").classes('text-xs text-[#006db0] font-bold')

                        # Right side: Action Buttons
                        with ui.row().classes('items-center gap-2 pr-6'):
                            # Jump to the notebook
                            ui.button('Join', icon='open_in_new', on_click=lambda sid=sid: ui.navigate.to(f'../edit/open/{str(nb_rel_path).replace(".py", "")}')) \
                                .props('flat color=primary').classes('font-bold tracking-wider')
                            
                            # Kill the specific process
                            ui.button(icon='delete_outline', on_click=lambda sid=sid: kill_session(session_id=sid)) \
                                .props('flat round color=red').tooltip('Kill Kernel')
                                

        # Trigger the first render when the page loads
        refresh_list()
    

 
ui.run_with(
    app, 
    storage_secret=os.getenv("NICEGUI_STORAGE_SECRET"),
    title="UNDP CareAtlas",
    mount_path='/explorer'
)
marimo_server = mu.get_marimo_runner(src=str(NOTEBOOKS_DIR), internal_path="/apps")

app.mount("/", marimo_server)



