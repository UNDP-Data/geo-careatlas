import git
import marimo as mo
import os

# --- Internal Logic ---

def get_repo():
    try:
        return git.Repo(".", search_parent_directories=True)
    except:
        return None

def git_commit_only(message):
    repo = get_repo()
    if not repo:
        return mo.status.error("No git repository found.")
    if not message.strip():
        return mo.status.warning("Commit message is required.")
    try:
        # Assuming files are already added/staged
        commit = repo.index.commit(message)
        return mo.status.success(f"Local commit successful: {commit.hexsha[:7]}")
    except Exception as e:
        return mo.status.error(f"Commit failed: {str(e)}")

def git_push_origin(_):
    repo = get_repo()
    if not repo:
        return mo.status.error("No git repository found.")
    try:
        origin = repo.remote(name='origin')
        origin.push()
        return mo.status.success("Successfully pushed to origin.")
    except Exception as e:
        return mo.status.error(f"Push failed: {str(e)}")

# --- UI Components ---

email = os.environ.get("GIT_AUTHOR_EMAIL", "developer@careatlas.app")



commit_button = mo.ui.button(label=" ", full_width=True)
push_button = mo.ui.button(label=" ", full_width=True)

# --- The Sidebar Template ---

sidebar_content = mo.Html(
    f"""
    <style>
        .marimo-overlay-wrapper {{
            position: absolute;
            inset: 0;
            z-index: 20;
            opacity: 0;
        }}
        .marimo-overlay-wrapper button {{
            width: 100% !important;
            height: 100% !important;
            cursor: pointer !important;
        }}
        .visual-layer {{
            pointer-events: none; 
            display: flex;
            align-items: center;
            width: 100%;
            height: 100%;
            z-index: 10;
        }}
        .collapsible-btn {{
            min-width: 36px; 
            height: 36px;
            overflow: hidden;
            display: flex;
            align-items: center;
            transition: all 0.2s ease-in-out;
        }}
        .custom-tailwind-wrapper:hover {{
            background-color: var(--sage-3, #e2e8f0);
        }}
        .custom-tailwind-wrapper:active {{
            transform: scale(0.95);
        }}
        .icon-container {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            flex-shrink: 0;
        }}
        .user-header {{
            display: flex;
            align-items: center;
            width: 100%;
            overflow: hidden;
            margin-bottom: 12px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--gray-4, #e5e7eb);
            color: var(--gray-11, #6b7280);
        }}
    </style>

    <div class="flex flex-col gap-2 p-1">
        <div class="user-header">
            <!--
             <div class="icon-container">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="lucide lucide-user"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
            -->
            <span class="text-m font-bold truncate pr-2">{email}</span>
        </div>

        <div class="custom-tailwind-wrapper collapsible-btn relative border border-foreground/10 shadow-xs-solid dark:border-border rounded">
            <div class="visual-layer">
                <div class="icon-container">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-git-commit-vertical"><circle cx="12" cy="12" r="3"/><line x1="12" x2="12" y1="3" y2="9"/><line x1="12" x2="12" y1="15" y2="21"/></svg>
                </div>
                <span class="whitespace-nowrap overflow-hidden pr-3 font-medium text-sm">Commit</span>
            </div>
            <div class="marimo-overlay-wrapper">
                {commit_button}
            </div>
        </div>

        <div class="custom-tailwind-wrapper collapsible-btn relative border border-foreground/10 shadow-xs-solid dark:border-border rounded">
            <div class="visual-layer">
                <div class="icon-container">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-git-push"><path d="M18 12V4"/><path d="m15 7 3-3 3 3"/><circle cx="6" cy="19" r="3"/><path d="M9 19h4a2 2 0 0 0 2-2v-1"/><circle cx="18" cy="16" r="3"/></svg>
                </div>
                <span class="whitespace-nowrap overflow-hidden pr-3 font-medium text-sm">Push</span>
            </div>
            <div class="marimo-overlay-wrapper">
                {push_button}
            </div>
        </div>
    </div>
    """
)