import git
import marimo as mo
import os
import sys

# --- Internal Logic ---

DRY_RUN=False


def get_repo():
    try:
        return git.Repo(".", search_parent_directories=True)
    except:
        return None

# Accept the notebook path as an argument
def is_modified(nb_path):
    repo = get_repo()
    if not repo or not nb_path:
        return False
    try:
        return repo.is_dirty(path=nb_path)
    except Exception as e:
        print(f"Git status error: {e}")
        return False

def commit(message, nb_file):
    repo = get_repo()
    
    if not repo:
        return mo.status.toast("No git repository found.", kind='danger')
    if not message.strip():
        return mo.status.toast("Commit message is required.", kind='warning')
    try:
        if not DRY_RUN:
            repo.index.add([nb_file])
            new_commit = repo.index.commit(message)
        return mo.status.toast(f"Local commit was successful", kind='success')
        
    except Exception as e:
        return mo.status.toast(f"Commit failed: {str(e)}", kind='danger')

def push(_):
    repo = get_repo()
    if not repo:
        return mo.status.toast("No git repository found.", kind='danger')
    try:
        origin = repo.remote(name='origin')
        if not DRY_RUN:
            origin.push()
        return mo.status.toast("Successfully pushed to origin.", kind='success')
    except Exception as e:
        return mo.status.toast(f"Push failed: {str(e)}", kind='danger')

def revert(_, nb_file):
    repo = get_repo()
    if not repo:
        return mo.status.toast("No git repository found.", kind='danger')
    try:
        # Check if the file is tracked/committed in the repository
        is_tracked = repo.git.ls_files(nb_file)
        
        if not is_tracked:
            return mo.status.toast(f"Cannot revert: {nb_file} has no commits yet.", kind='warning')

        # If it is tracked, proceed with the revert
        if not DRY_RUN:
            repo.git.checkout('HEAD', '--', nb_file)
        return mo.status.toast(f"Reverted {nb_file} to last commit.", kind='success')
        
    except Exception as e:
        return mo.status.toast(f"Revert failed: {str(e)}", kind='danger')


# 1. Configuration
email = os.environ.get("GIT_AUTHOR_EMAIL", None)

# 1. The Input Field (lives inside the popup)
commit_input = mo.ui.text_area(
    placeholder="e.g., Update poverty threshold logic...",
    full_width=True
)

# 2. Handlers for buttons
def handle_commit(_):
    nb_file = os.path.abspath(sys.argv[0])
    modified = is_modified(nb_path=nb_file)
    message = commit_input.value
    
    if not modified:
        return mo.status.toast("No changes to commit.", kind="neutral")
    if not message.strip():
        return mo.status.toast("Please enter a commit message!", kind='danger')
        
    commit(message, nb_file=nb_file)
    mo.status.toast(f"Commit '{message}' triggered from {nb_file}", kind="success")

btn_confirm = mo.ui.button(
    label=f"{mo.icon('lucide:check', size=20)} Commit",
    on_click=handle_commit,
    full_width=True,
)

btn_revert = mo.ui.button(
    label=f"{mo.icon('lucide:undo-2', size=20)} Revert",
    on_click=lambda _: revert(_, nb_file=os.path.abspath(sys.argv[0])),
    full_width=True,
    kind="danger"
)

btn_run = mo.ui.button(
    label=f"{mo.icon('lucide:git-merge', size=24)}",
    on_click=push, 
    tooltip="Push commits to origin",
    full_width=False
)

sidebar_content = mo.Html(
    f"""
    <style>
        .git-panel {{ display: flex; flex-direction: column; gap: 12px; padding: 4px; }}
        
        /* Native HTML Expandable Styling */
        details.commit-expander {{ width: 100%; }}
        details.commit-expander > summary {{ 
            list-style: none; cursor: pointer; 
            display: flex; justify-content: center;
            padding: 6px; border-radius: 6px;
            transition: background 0.2s ease;
        }}
        
        /* Hide the default HTML triangle arrow */
        details.commit-expander > summary::-webkit-details-marker {{ display: none; }}
        
        /* Hover effect for the icon */
        details.commit-expander > summary:hover {{ background: var(--gray-3, #f3f4f6); }}

        .commit-box {{
            display: flex; flex-direction: column; gap: 8px;
            padding-top: 12px;
            border-top: 1px solid var(--gray-3, #f3f4f6);
            margin-top: 8px;
        }}

        /* Container to place commit and revert buttons side by side */
        .action-buttons {{
            display: flex;
            gap: 8px;
            width: 100%;
        }}
        
        /* Ensure both buttons take up equal space */
        .action-buttons > * {{
            flex: 1;
        }}

        .push-container {{
            display: flex;
            justify-content: center;
            width: 100%;
        }}
    </style>

    <div class="git-panel">
        
        <details class="commit-expander" id="commit-expander">
            <summary title="Toggle Commit Input">
                {mo.icon('lucide:folder-git-2', size=24)}
            </summary>
            
            <div class="commit-box" id="commit-box-content">
                {commit_input}
                <div class="action-buttons">
                    {btn_confirm}
                    {btn_revert}
                </div>
            </div>
        </details>
        
        <div class="push-container">
            {btn_run}
        </div>
        
    </div>
    
    <script>
        document.getElementById('commit-box-content').addEventListener('click', (e) => {{
            if(e.target.closest('marimo-ui-element')) {{
                setTimeout(() => document.getElementById('commit-expander').removeAttribute('open'), 300);
            }}
        }});
    </script>
    """
)

def create_sidebar(mmo=None):
    if email:
        return mmo.sidebar(sidebar_content)