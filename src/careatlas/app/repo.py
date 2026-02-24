import git
import marimo as mo
import os
import sys
import shutil


# 1. Configuration
email = os.environ.get("GIT_AUTHOR_EMAIL", None)

DRY_RUN=False
# Extract version once at the module level or inside the function
MARIMO_VERSION = getattr(mo, "__version__", "")

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

def stage_commit_push(src:str=None, push:bool=True):
    # Ensure we have the full absolute path inside the container
    abs_path = os.path.abspath(src)
    name = os.path.basename(abs_path)
    
    token = os.environ.get('GITHUB_PAT_TOKEN')
    repo = get_repo()
    
    if not repo:
        return mo.status.toast("Repo not found", kind="danger")

    try:
        # 1. Setup Identity (Required for AKS/Docker)
        with repo.config_writer() as cw:
            cw.set_value("user", "name", os.environ.get("GIT_AUTHOR_NAME", "Marimo Bot"))
            cw.set_value("user", "email", os.environ.get("GIT_AUTHOR_EMAIL", "bot@undp.org"))
        print(f"I am working in: {os.getcwd()}")
        print(f"Git thinks the root is: {repo.working_tree_dir}")
        # 2. STAGE: Passing the absolute path is more reliable in Docker
        repo.index.add([abs_path])
        
        # 3. COMMIT
        repo.index.commit(f"Auto-notebook: {name}")
        if push:
            # 4. AUTHENTICATED PUSH
            origin = repo.remote(name='origin')
            if token and "https://" in origin.url and "@" not in origin.url:
                auth_url = origin.url.replace("https://", f"https://{token}@")
                origin.set_url(auth_url)
                
                # Explicitly push the current branch
                origin.push()
                
                # Cleanup URL
                origin.set_url(origin.url.replace(f"{token}@", ""))
        
            mo.status.toast(f"Pushed: {name}", kind="success")
        else:
            mo.status.toast(f"Staged & commited: {name}", kind="success")
    except Exception as e:
        # This will now capture the specific Git error (e.g., "pathspec matches no files")
        mo.status.toast(f"Git Error: {str(e)}", kind="danger")


# 1. The Input Field (lives inside the popup)
commit_input = mo.ui.text_area(
    placeholder="e.g., Update poverty threshold logic...",
    full_width=True
)

# 1. Input field for the new filename
create_input = mo.ui.text(
    placeholder="new_notebook_name",
    label="Filename",
    full_width=True
)

duplicate_input = mo.ui.text(
    placeholder="new_notebook_name",
    label="Filename",
    full_width=True
)


def duplicate(_):
    
    name = duplicate_input.value.strip()
    if not name:
        return mo.status.toast("Please enter a filename", kind="warning")
    
    # Ensure it ends with .py
    if not name.endswith(".py"):
        name += ".py"
        
    current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    new_path = os.path.join(current_dir, name)
    
    if os.path.exists(new_path):
        return mo.status.toast(f"Error: {name} already exists!", kind="danger")
    
    current_path = os.path.abspath(sys.argv[0])
    
    try:
        if not DRY_RUN:
            shutil.copy2(current_path, new_path)
            #commit(message=f"Created new notebbok {new_path}", nb_file=new_path)
            stage_commit_push(src=new_path)
            return mo.status.toast(f"Duplicated & Staged: {os.path.basename(new_path)}", kind="success")
    except Exception as e:
        return mo.status.toast(f"Duplicate failed: {e}", kind="danger")

# 2. Handlers for buttons
def handle_commit(_):
    nb_file = os.path.abspath(sys.argv[0])
    modified = is_modified(nb_path=nb_file)
    message = commit_input.value
    
    if not modified:
        return mo.status.toast("No changes to commit.", kind="neutral")
    if not message.strip():
        return mo.status.toast("Please enter a commit message!", kind='danger')
    if not DRY_RUN:  
        commit(message, nb_file=nb_file)
        mo.status.toast(f"Commit '{message}' triggered from {nb_file}", kind="success")

btn_commit = mo.ui.button(
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

btn_push = mo.ui.button(
    label=f"{mo.icon('lucide:git-merge', size=24)}",
    on_click=push, 
    tooltip="Push commits to origin",
    full_width=False
)

def handle_create_notebook(_):
    name = create_input.value.strip()
    if not name:
        return mo.status.toast("Please enter a filename", kind="warning")
    
    # Ensure it ends with .py
    if not name.endswith(".py"):
        name += ".py"
        
    current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    new_path = os.path.join(current_dir, name)
    
    if os.path.exists(new_path):
        return mo.status.toast(f"Error: {name} already exists!", kind="danger")

    # Interpolated Template
    template = (
        'import marimo\n\n'
        f'__generated_with = "{MARIMO_VERSION}"\n'
        'app = marimo.App(width="medium", auto_download=["html"])\n\n\n'
        '@app.cell\n'
        'def menu():\n'
        '    import marimo as mo\n'
        '    from careatlas.app.repo import create_sidebar\n'
        '    create_sidebar(marimo_module=mo)\n'
        '    return (mo,)\n'
    )

    try:
    
        # Git staging
        if not DRY_RUN:
            with open(new_path, "w") as f:
                f.write(template)
            repo = get_repo()
            if repo:
                # 2. Get the path relative to the repo root
                rel_p = os.path.relpath(new_path, repo.working_tree_dir)
                
                # 3. Add and Commit specifically for this file
                repo.index.add([rel_p])
                repo.index.commit(f"New notebook: {name}")
            
        return mo.status.toast(f"Created & Staged: {name} (v{MARIMO_VERSION})", kind="success")
    except Exception as e:
        return mo.status.toast(f"Error: {str(e)}", kind="danger")

btn_create_confirm = mo.ui.button(
    label=f"{mo.icon('fluent:notebook-add-20-regular', size=24)} Create",
    on_click=handle_create_notebook,
    full_width=False,
    tooltip="Create new notebook",
)


btn_duplicate = mo.ui.button(
    label=f"{mo.icon('lucide:copy', size=24)} Duplicate",
    on_click=duplicate,
    tooltip="Duplicate current notebook",
    full_width=False
)

sidebar_content = mo.Html(
    f"""
    <style>
        .git-panel {{ display: flex; flex-direction: column; gap: 8px; padding: 4px; }}
        
        details.tool-expander {{ 
            width: 100%; 
            border-bottom: 3px solid var(--gray-3, #f3f4f6); 
            padding-bottom: 4px; 
        }}
        
        details.tool-expander > summary {{ 
            list-style: none; cursor: pointer; 
            display: flex; justify-content: center;
            padding: 10px; border-radius: 6px;
            transition: background 0.2s ease;
        }}
        
        details.tool-expander > summary::-webkit-details-marker {{ display: none; }}
        details.tool-expander > summary:hover {{ background: var(--gray-2, #f9fafb); }}

        .expander-content {{
            display: flex; flex-direction: column; gap: 10px;
            padding: 12px 6px;
        }}

        .tools-container {{
            display: flex; justify-content: center;
            width: 100%; padding-top: 12px;
        }}
    </style>

    <div class="git-panel">
        
        <details class="tool-expander" id="create-expander">
            <summary title="Create new notebook in current directory">
                {mo.icon('lucide:file-plus', size=24)}
            </summary>
            <div class="expander-content">
                {create_input}
                {btn_create_confirm}
            </div>
        </details>
        
        <details class="tool-expander" id="duplicate-expander">
            <summary title="Duplicate current notebook in current directory">
                {mo.icon('lucide:copy-plus', size=24)}
            </summary>
            <div class="expander-content">
                {duplicate_input}
                {btn_duplicate}
            </div>
        </details>

        <details class="tool-expander" id="commit-expander">
            <summary title="Commit Changes">
                {mo.icon('lucide:folder-git-2', size=24)}
            </summary>
            <div class="expander-content">
                {commit_input}
                <div style="display: flex; gap: 8px;">
                    {btn_commit}
                    {btn_revert}
                </div>
            </div>
        </details>
        
        <div class="tools-container">
            {btn_push}
        </div>
        
    </div>
    
    <script>
        // Closes the expander after an action is taken
        document.querySelectorAll('.expander-content').forEach(panel => {{
            panel.addEventListener('click', (e) => {{
                if(e.target.closest('marimo-ui-element')) {{
                    setTimeout(() => {{
                        panel.parentElement.removeAttribute('open');
                    }}, 300);
                }}
            }});
        }});
    </script>
    """
)

def create_sidebar(marimo_module=None):
    if email:
        return marimo_module.sidebar(sidebar_content)