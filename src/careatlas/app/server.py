import os
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, APIRouter
from nicegui import ui, app as nicegui_app
from .auth import get_user_identity, is_authenticated, check_auth
from urllib.parse import urlparse, urlunparse, quote
import logging
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


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



@asynccontextmanager
async def lifespan(app: FastAPI):
    global marimo_process
    # Start Marimo to serve the notebooks directory internally
    marimo_process = subprocess.Popen([
        "uv", "run", "marimo", "run", "src/careatlas/notebooks",
        "--port", "8080", "--headless", "--no-token"
    ])
    yield
    if marimo_process:
        marimo_process.terminate()

app = FastAPI(title="UNDP CareAtlas", lifespan=lifespan)

# --- 2. UNDP Design System Theme & Assets ---
def apply_undp_theme():
    # Link to official UNDP Design System assets
    ui.add_head_html('''
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@undp/design-system-assets/css/base-minimal.min.css">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@undp/design-system-assets/css/components.min.css">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Saira:wght@700&display=swap" rel="stylesheet">
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
                auth_url = os.getenv('AUTH_URL', '/oauth2').rstrip('/')
                auth = check_auth(url=auth_url, request=request)
                is_authenticated = auth['is_authenticated']
                email = 'Guest' if not is_authenticated else auth['email']
                color = 'green' if is_authenticated else 'gray'
                
                target_action = f"{auth_url}/sign_out" if is_authenticated else f"{auth_url}/start"
                
                # 3. Build the URL dynamically
                u = urlparse(str(request.url))
                rd_path = u.path + (("?" + u.query) if u.query else "")

                # return to the current app host (absolute URL)
                rd = f'{str(request.base_url).rstrip("/")}/{rd_path.strip("/")}'
                
                final_url = f"{target_action}?rd={quote(rd, safe=':/%?=&')}"
                tooltip_text = f'Sign out\n {email} to {final_url}' if is_authenticated else f'Sign in to {final_url}'

                
                
                
                
               
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

# --- 4. Page Routes ---
@ui.page('/')
async def main_index(request: Request):
    undp_layout(request, "" ) 
    apply_undp_theme()
    undp_header(request=request)
    #ui.label(request.scope)
    #ui.label(str(request.app))
    ui.label(str(request.url))
    ui.label(str(request.base_url))
    with ui.column().classes('w-full max-w-7xl mx-auto px-6 lg:px-8'):
        
        with ui.element('div').classes('w-full min-w-0 break-words'):
            
            with ui.grid(columns='1fr 1fr 1fr').classes('w-full gap-8'):
                notebook_root = "src/careatlas/notebooks"
                if os.path.exists(notebook_root):
                    folders = [d for d in os.listdir(notebook_root) if os.path.isdir(os.path.join(notebook_root, d))]
                    
                    for folder in folders:
                        # Check for lock files
                        is_locked = os.path.exists(os.path.join(notebook_root, folder, ".lock"))
                        
                        with ui.card().classes('undp-card p-0 overflow-hidden bg-white'):
                            # UNDP Accent bar
                            ui.element('div').classes(f"w-full h-1 {'bg-red-600' if is_locked else 'bg-[#006db0]'}")
                            
                            with ui.column().classes('p-8 w-full'):
                                ui.label('Group').classes('text-[#006db0] text-[10px] font-bold tracking-widest')
                                ui.label(folder).classes('text-2xl font-bold uppercase mb-4 text-black')
                                
                                if is_locked:
                                    ui.label('Currently being updated by an editor.').classes('text-red-600 text-xs mb-6 italic')
                                    ui.button('LOCKED', color='grey').classes('undp-btn w-full py-3').props('disabled')
                                else:
                                    ui.label('Access regional poverty and economic indicators.').classes('text-gray-500 text-sm mb-6')
                                    ui.button('Explore', on_click=lambda r=folder: ui.navigate.to(f'/notebooks/{r}')) \
                                        .classes('undp-btn bg-[#006db0] text-white w-full py-3')




# --- 5. Integrated Execution ---
ui.run_with(
    app, 
    storage_secret=os.getenv("NICEGUI_STORAGE_SECRET"),
    title="UNDP CareAtlas"
)