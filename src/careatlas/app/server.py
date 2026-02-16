import os
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from nicegui import ui, app as nicegui_app
from .auth import get_user_identity, is_authenticated, check_auth
from urllib.parse import urlparse, urlunparse, quote
import logging
from careatlas.app import marutil as mu
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from pathlib import Path
from starlette.routing import Mount
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Scope, Receive, Send
from marimo._utils.paths import marimo_package_path
import marimo
import json

logging.basicConfig(level=logging.INFO)


logger = logging.getLogger()

AUTH_URL = f"{os.getenv('AUTH_URL')}/auth"



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



# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     global marimo_process
#     # Start Marimo to serve the notebooks directory internally
#     marimo_process = subprocess.Popen([
#         "uv", "run", "marimo", "run", "src/careatlas/notebooks",
#         "--port", "8080", "--headless", "--no-token"
#     ])
#     yield
#     if marimo_process:
#         marimo_process.terminate()

app = FastAPI(title="UNDP CareAtlas", lifespan=None)


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
                # auth_url = os.getenv('AUTH_URL', '/oauth2').rstrip('/')
                # auth = check_auth(url=auth_url, request=request)
                # is_authenticated = auth['is_authenticated']
                # email = 'Guest' if not is_authenticated else auth['email']
                # color = 'green' if is_authenticated else 'gray'                
                # target_action = f"{auth_url}/sign_out" if is_authenticated else f"{auth_url}/start"
                
                # # 3. Build the URL dynamically
                # u = urlparse(str(request.url))
                # rd_path = u.path + (("?" + u.query) if u.query else "")

                # # return to the current app host (absolute URL)
                # rd = f'{str(request.base_url).rstrip("/")}/{rd_path.strip("/")}'
                
                # final_url = f"{target_action}?rd={quote(rd, safe=':/%?=&')}"
                # tooltip_text = f'Sign out\n {email} to {final_url}' if is_authenticated else f'Sign in to {final_url}'

                # 1. This is your single source of truth from Docker/AKS
                auth_url = os.getenv('AUTH_URL', '/oauth2').rstrip('/')

                # 2. Internal Check: Always use the env var + /auth
                auth = check_auth(url=f"{auth_url}/auth", request=request)
                is_authenticated = auth['is_authenticated']
                email = 'Guest' if not is_authenticated else auth['email']
                color = 'green' if is_authenticated else 'gray'

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
                
                tooltip_text = f'Sign out \n{email}' if is_authenticated else f'Sign in {email}'
               
                with ui.link(target=final_url).style('display: contents; text-decoration: none !important;'):
                    # ui.button(
                    #     icon='account_circle',
                    #     on_click=lambda: ui.navigate.to(final_url),
                    # ).props(f'flat round dense color={color}') \
                    # .classes('w-9 h-9 hover:scale-110 transition') \
                    # .tooltip(tooltip_text)
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
    #ui.label(str(type(mapp)))
    
    # Identify if user has Edit rights (e.g., is authenticated)
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
            # If parent is '.', we go back to root '/'
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
                # This path is relative to the ROOT, perfect for the URL
                rel_path = item.relative_to(NOTEBOOKS_DIR)
                name,*r = os.path.splitext(item.name)
                item_label = name.replace('_', ' ')
                if item.is_dir():
                    if '__' in item.name:continue
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
                        ui.element('div').classes('w-full h-1 bg-green-500')
                        with ui.column().classes('p-8 w-full'):
                            with ui.row():
                                ui.icon('dashboard', color='[#006db0]').classes('text-3xl')
                                ui.label('Notebook').classes('text-[#006db0] text-1xl font-bold tracking-widest')
                            
                            descr = mu.get_global_metadata(str(item.absolute()))
                            
                            ui.label(descr).classes('text-sm mb-2 text-gray-500 ')
                            
                            with ui.row().classes('w-full gap-2'):
                                # Path for Marimo (no .py extension)
                                marimo_slug = str(rel_path).replace('.py', '').replace(os.sep, '/').strip('/')
                                
                                r = [(str(rel_path).count('/')+1)* '../'][0]
                               
                                
                                # View button (Always available)
                                #ui.label( )
                                ui.button('Launch', on_click=lambda s=marimo_slug, r=r: ui.navigate.to(f'{r}apps/{s}')) \
                                    .classes('undp-btn border border-[#006db0] text-[#006db0] flex-1 max-w-[100px] capitalize')\
                                    .tooltip(f'Launch notebook as app at {r}apps/{marimo_slug}')
                                
                                
                                # Edit button (Conditional)
                                # if can_edit:
                                #     ui.button('Edit', on_click=lambda s=marimo_slug: ui.navigate.to(f'/edit/{s}')) \
                                #         .classes('undp-btn bg-[#006db0] text-white flex-1 ')


@app.middleware("http")
async def normalize_paths(request, call_next):
    path = request.url.path

    # root → explorer
    if path == "/" or path == '/explorer':
        return RedirectResponse("/explorer/", status_code=307)

    # # remove trailing slash (except root)
    # if path != "/" and path.endswith("/"):
    #     new = path.rstrip("/")
    #     if request.url.query:
    #         new += "?" + request.url.query
    #     return RedirectResponse(new, status_code=307)

    return await call_next(request)
 
ui.run_with(
    app, 
    storage_secret=os.getenv("NICEGUI_STORAGE_SECRET"),
    title="UNDP CareAtlas",
    mount_path='/explorer'
)


# mount notebooks dynamically
BASE_DIR = Path(__file__).parent.parent.resolve() 
NOTEBOOKS_DIR = (BASE_DIR / "notebooks").resolve()
marimo_server = mu.get_marimo_runner(src=str(NOTEBOOKS_DIR), internal_path="/apps")

app.mount("/", marimo_server)



