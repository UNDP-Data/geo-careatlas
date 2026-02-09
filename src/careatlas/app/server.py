import os
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from nicegui import ui, app as nicegui_app

# --- 1. Process Management (Marimo Sidecar) ---
marimo_process = None



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
        </style>
    ''')


@ui.page('/who-we-are')
def who_we_are(request: Request):
    user = request.headers.get("x-forwarded-user", None)
    apply_undp_theme()
    undp_header(user)
    ui.label("WHO WE ARE")


@ui.page('/what-we-do')
def who_we_are(request: Request):
    user = request.headers.get("x-forwarded-user", None)
    apply_undp_theme()
    undp_header(user)
    ui.label("WHAT WE DO")
    
    
@ui.page('/our-impact')
def who_we_are(request: Request):
    user = request.headers.get("x-forwarded-user", None)
    apply_undp_theme()
    undp_header(user)
    ui.label("OUR IMPACT")


    
@ui.page('/get-involved')
def who_we_are(request: Request):
    user = request.headers.get("x-forwarded-user", None)
    apply_undp_theme()
    undp_header(user)
    ui.label("NOW OR NEVER")  
    
    

# --- 3. UI Components (UNS Compliant) ---
def undp_header(user: str):
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

            # RIGHT: utilities
            # with ui.row().classes('items-center gap-4'):
                
            #     ui.icon('account_circle').classes('text-[32px] text-gray-600')
            #     ui.label(user).classes('text-[18px] font-medium text-gray-700')
            with ui.column().classes('items-center gap-1 whitespace-nowrap text-center'):
                ui.icon('account_circle').classes('text-[48px] text-gray-600')
                ui.label(user).classes('text-[14px] text-gray-600').style('font-weight: 400 !important;')



# --- 4. Page Routes ---
@ui.page('/')
async def main_index(request: Request):
    apply_undp_theme()
    user = request.headers.get("x-forwarded-user", None)
    # This header contains the email if configured in OAuth2-Proxy
    email = request.headers.get("x-forwarded-email", None)
    undp_header(email)

    with ui.column().classes('w-full max-w-7xl mx-auto p-8'):
        
        ui.label('Content').classes('text-4xl font-bold text-black uppercase mb-2')
        ui.element('div').classes('w-20 h-1 bg-[#006db0] mb-12')

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
                                ui.button('Explore', on_click=lambda r=region: ui.navigate.to(f'/region/{r}')) \
                                    .classes('undp-btn bg-[#006db0] text-white w-full py-3')

# --- 5. Integrated Execution ---
ui.run_with(
    app, 
    storage_secret=os.getenv("NICEGUI_STORAGE_SECRET"),
    title="UNDP CareAtlas"
)