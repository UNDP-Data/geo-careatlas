import git
import marimo as mo
import os
import sys
import shutil


# 1. Configuration
email = os.environ.get("GIT_AUTHOR_EMAIL", None)

DRY_RUN=True
# Extract version once at the module level or inside the function
MARIMO_VERSION = getattr(mo, "__version__", "")

def get_repo():
    try:
        # 1. Initialize the repo
        repo = git.Repo("/server", search_parent_directories=True)
        assert not repo.bare
        
        # 2. Automatically configure identity for this instance
        # Using a context manager ensures the file lock is released immediately
        with repo.config_writer() as cw:
            # Fallback to your UNDP email if env vars are missing
            cw.set_value("user", "name", os.environ.get("GIT_AUTHOR_NAME", "Marimo bot"))
            cw.set_value("user", "email", os.environ.get("GIT_AUTHOR_EMAIL", "bot@marimo"))
        
        return repo
    except Exception as e:
        # Helpful for debugging if /server isn't found
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


def save(src: str = None, push: bool = True):
    try:
        abs_path = os.path.abspath(src)
        name = os.path.basename(abs_path)
        token = os.environ.get('GITHUB_PAT_TOKEN')
        repo = get_repo()
    
        if not repo:
            return mo.status.toast("Repo not found", kind="danger")
        if not DRY_RUN:
            # 1. STAGE & COMMIT (Local first)
            repo.index.add([abs_path], force=True)
            repo.index.commit(f"Auto-notebook: {name}")

        if push:
            origin = repo.remote(name='origin')
            
            # Authenticate URL
            if token and "https://" in origin.url and "@" not in origin.url:
                auth_url = origin.url.replace("https://", f"https://{token}@")
                origin.set_url(auth_url)
            
            try:
                if not DRY_RUN:
                    # 2. THE PULL REBASE (Crucial for multi-user safety)
                    # This brings down others' changes and puts yours on top
                    origin.pull(rebase=True)
                    
                    # 3. PUSH
                    origin.push()
                mo.status.toast(f"Synced: {name}", kind="success")
                
            except Exception as e:
                # If rebase fails (conflict in the SAME notebook), we must abort
                if repo.is_dirty() or "rebase" in str(e).lower():
                    repo.git.rebase("--abort")
                raise e # Pass to the outer exception handler
            finally:
                # Cleanup URL even if it fails
                origin.set_url(origin.url.replace(f"{token}@", ""))
        else:
            mo.status.toast(f"Staged & commited: {name}", kind="success")

    except git.exc.GitCommandError as gce:
        mo.status.toast(f"Git Error: {gce.stderr}", kind="danger")
    except Exception as e:
        mo.status.toast(f"Error: {str(e)}", kind="danger")

def reset_to_remote():
    try:
        if not DRY_RUN:
            repo = get_repo()
            # 1. Fetch the latest from GitHub without merging
            repo.remotes.origin.fetch()
            
            # 2. Hard reset local main to match origin/main
            # WARNING: This deletes uncommitted local work!
            repo.git.reset('--hard', 'origin/main')
            
            # 3. Clean up untracked files/folders
            repo.git.clean('-fd')
        
        mo.status.toast("Environment reset to match GitHub exactly.", kind="info")
    except Exception as e:
        mo.status.toast(f"Reset failed: {str(e)}", kind="danger")


def handle_create(name_ui):
    name = name_ui.value.strip()
    if not name:
        return mo.status.toast("Please enter a notebook name", kind="warn")
    
    filename = name if name.endswith(".py") else f"{name}.py"
    target_path = os.path.join(os.getcwd(), filename)
    
    if os.path.exists(target_path):
        return mo.status.toast(f"File {filename} already exists!", kind="danger")

    if not DRY_RUN:
        # Your boilerplate template
        template = f'import marimo as mo\n\n@app.cell\ndef menu():\n    from careatlas.app.repo import create_sidebar\n    create_sidebar()\n'
        
        with open(target_path, "w") as f:
            f.write(template)
        
        # Auto-save/Sync the new file
        save(src=target_path, push=True)
    return mo.status.toast(f"Created {filename} and synced to Cloud", kind="success")


def handle_duplicate(name_ui):
    name = name_ui.value.strip()
    if not name:
        return mo.status.toast("Enter a name for the copy", kind="warn")
    
    filename = name if name.endswith(".py") else f"{name}.py"
    current_file = os.path.abspath(sys.argv[0])
    target_path = os.path.join(os.path.dirname(current_file), filename)

    try:
        if not DRY_RUN:
            shutil.copy2(current_file, target_path)
            save(src=target_path, push=True)
        mo.status.toast(f"Duplicated to {filename}", kind="success")
    except Exception as e:
        mo.status.toast(f"Copy failed: {e}", kind="danger")

# def handle_create_notebook(_):
#     name = create_input.value.strip()
#     if not name:
#         return mo.status.toast("Please enter a filename", kind="warning")
    
#     # Ensure it ends with .py
#     if not name.endswith(".py"):
#         name += ".py"
        
#     current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
#     new_path = os.path.join(current_dir, name)
    
#     if os.path.exists(new_path):
#         return mo.status.toast(f"Error: {name} already exists!", kind="danger")

#     # Interpolated Template
#     template = (
#         'import marimo\n\n'
#         f'__generated_with = "{MARIMO_VERSION}"\n'
#         'app = marimo.App(width="medium", auto_download=["html"])\n\n\n'
#         '@app.cell\n'
#         'def menu():\n'
#         '    import marimo as mo\n'
#         '    from careatlas.app.repo import create_sidebar\n'
#         '    create_sidebar(marimo_module=mo)\n'
#         '    return (mo,)\n'
#     )

#     try:
    
#         # Git staging
#         if not DRY_RUN:
#             with open(new_path, "w") as f:
#                 f.write(template)
#             repo = get_repo()
#             if repo:
#                 # 2. Get the path relative to the repo root
#                 rel_p = os.path.relpath(new_path, repo.working_tree_dir)
                
#                 # 3. Add and Commit specifically for this file
#                 repo.index.add([rel_p])
#                 repo.index.commit(f"New notebook: {name}")
            
#         return mo.status.toast(f"Created & Staged: {name} (v{MARIMO_VERSION})", kind="success")
#     except Exception as e:
#         return mo.status.toast(f"Error: {str(e)}", kind="danger")

# btn_create_confirm = mo.ui.button(
#     label=f"{mo.icon('fluent:notebook-add-20-regular', size=24)} Create",
#     on_click=handle_create_notebook,
#     full_width=False,
#     tooltip="Create new notebook",
# )


# def commit(message, nb_file):
#     repo = get_repo()
    
#     if not repo:
#         return mo.status.toast("No git repository found.", kind='danger')
#     if not message.strip():
#         return mo.status.toast("Commit message is required.", kind='warning')
#     try:
#         if not DRY_RUN:
#             repo.index.add([nb_file], force=True)
#             new_commit = repo.index.commit(message)
#             return mo.status.toast(f"Local commit was successful", kind='success')
        
#     except Exception as e:
#         return mo.status.toast(f"Commit failed: {str(e)}", kind='danger')

# def push(_):
#     repo = get_repo()
#     if not repo:
#         return mo.status.toast("No git repository found.", kind='danger')
#     try:
#         origin = repo.remote(name='origin')
#         if not DRY_RUN:
#             origin.push()
#             return mo.status.toast("Successfully pushed to origin.", kind='success')
#     except Exception as e:
#         return mo.status.toast(f"Push failed: {str(e)}", kind='danger')

# def revert(_, nb_file):
#     repo = get_repo()
#     if not repo:
#         return mo.status.toast("No git repository found.", kind='danger')
#     try:
#         # Check if the file is tracked/committed in the repository
#         is_tracked = repo.git.ls_files(nb_file)
        
#         if not is_tracked:
#             return mo.status.toast(f"Cannot revert: {nb_file} has no commits yet.", kind='warning')

#         # If it is tracked, proceed with the revert
#         if not DRY_RUN:
#             repo.git.checkout('HEAD', '--', nb_file)
#             return mo.status.toast(f"Reverted {nb_file} to last commit.", kind='success')
        
#     except Exception as e:
#         return mo.status.toast(f"Revert failed: {str(e)}", kind='danger')

# def stage_commit_push(src:str=None, push:bool=True):
    
#     try:
#         # Ensure we have the full absolute path inside the container
#         abs_path = os.path.abspath(src)
#         name = os.path.basename(abs_path)
        
#         token = os.environ.get('GITHUB_PAT_TOKEN')
#         repo = get_repo()
    
#         if not repo:
#             return mo.status.toast("Repo not found", kind="danger")

#         # 2. STAGE: Passing the absolute path is more reliable in Docker
#         repo.index.add([abs_path], force=True)
        
#         # 3. COMMIT
#         repo.index.commit(f"Auto-notebook: {name}")
#         if push:
#             # 4. AUTHENTICATED PUSH
#             origin = repo.remote(name='origin')
#             if token and "https://" in origin.url and "@" not in origin.url:
#                 auth_url = origin.url.replace("https://", f"https://{token}@")
#                 origin.set_url(auth_url)
                
#                 # Explicitly push the current branch
#                 origin.push()
                
#                 # Cleanup URL
#                 origin.set_url(origin.url.replace(f"{token}@", ""))
        
#                 mo.status.toast(f"Pushed: {name}", kind="success")
#         else:
#             mo.status.toast(f"Staged & commited: {name}", kind="success")
#     except git.exc.GitCommandError as gce:
#         # This captures the ACTUAL terminal error from Git
#         error_msg = f"Git CLI Error: {gce.stderr}"
#         print(error_msg) # Check your Marimo console/terminal
#         return mo.status.toast(error_msg, kind="danger")
#     except Exception as e:
#         # This will now capture the specific Git error (e.g., "pathspec matches no files")
#         mo.status.toast(f"Git Error: {str(e)}", kind="danger")
#         print(e)



# # 1. The Input Field (lives inside the popup)
# commit_input = mo.ui.text_area(
#     placeholder="e.g., Update poverty threshold logic...",
#     full_width=True
# )

# # 1. Input field for the new filename
# create_input = mo.ui.text(
#     placeholder="new_notebook_name",
#     label="Filename",
#     full_width=True
# )

# duplicate_input = mo.ui.text(
#     placeholder="new_notebook_name",
#     label="Filename",
#     full_width=True
# )


# def duplicate(_):
    
#     name = duplicate_input.value.strip()
#     if not name:
#         return mo.status.toast("Please enter a filename", kind="warning")
    
#     # Ensure it ends with .py
#     if not name.endswith(".py"):
#         name += ".py"
        
#     current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
#     new_path = os.path.join(current_dir, name)
    
#     if os.path.exists(new_path):
#         return mo.status.toast(f"Error: {name} already exists!", kind="danger")
    
#     current_path = os.path.abspath(sys.argv[0])
    
#     try:
#         if not DRY_RUN:
#             shutil.copy2(current_path, new_path)
#             #commit(message=f"Created new notebbok {new_path}", nb_file=new_path)
#             stage_commit_push(src=new_path)
#             #return mo.status.toast(f"Duplicated & Staged: {os.path.basename(new_path)}", kind="success")
#     except Exception as e:
#         return mo.status.toast(f"Duplicate failed: {e}", kind="danger")

# # 2. Handlers for buttons
# def handle_commit(_):
#     nb_file = os.path.abspath(sys.argv[0])
#     modified = is_modified(nb_path=nb_file)
#     message = commit_input.value
    
#     if not modified:
#         return mo.status.toast("No changes to commit.", kind="neutral")
#     if not message.strip():
#         return mo.status.toast("Please enter a commit message!", kind='danger')
#     if not DRY_RUN:  
#         commit(message, nb_file=nb_file)
#         mo.status.toast(f"Commit '{message}' triggered from {nb_file}", kind="success")

# btn_commit = mo.ui.button(
#     label=f"{mo.icon('lucide:check', size=20)} Commit",
#     on_click=handle_commit,
#     full_width=True,
# )

# btn_revert = mo.ui.button(
#     label=f"{mo.icon('lucide:undo-2', size=20)} Revert",
#     on_click=lambda _: revert(_, nb_file=os.path.abspath(sys.argv[0])),
#     full_width=True,
#     kind="danger"
# )

# btn_push = mo.ui.button(
#     label=f"{mo.icon('lucide:git-merge', size=24)}",
#     on_click=push, 
#     tooltip="Push commits to origin",
#     full_width=False
# )

# def handle_create_notebook(_):
#     name = create_input.value.strip()
#     if not name:
#         return mo.status.toast("Please enter a filename", kind="warning")
    
#     # Ensure it ends with .py
#     if not name.endswith(".py"):
#         name += ".py"
        
#     current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
#     new_path = os.path.join(current_dir, name)
    
#     if os.path.exists(new_path):
#         return mo.status.toast(f"Error: {name} already exists!", kind="danger")

#     # Interpolated Template
#     template = (
#         'import marimo\n\n'
#         f'__generated_with = "{MARIMO_VERSION}"\n'
#         'app = marimo.App(width="medium", auto_download=["html"])\n\n\n'
#         '@app.cell\n'
#         'def menu():\n'
#         '    import marimo as mo\n'
#         '    from careatlas.app.repo import create_sidebar\n'
#         '    create_sidebar(marimo_module=mo)\n'
#         '    return (mo,)\n'
#     )

#     try:
    
#         # Git staging
#         if not DRY_RUN:
#             with open(new_path, "w") as f:
#                 f.write(template)
#             repo = get_repo()
#             if repo:
#                 # 2. Get the path relative to the repo root
#                 rel_p = os.path.relpath(new_path, repo.working_tree_dir)
                
#                 # 3. Add and Commit specifically for this file
#                 repo.index.add([rel_p])
#                 repo.index.commit(f"New notebook: {name}")
            
#         return mo.status.toast(f"Created & Staged: {name} (v{MARIMO_VERSION})", kind="success")
#     except Exception as e:
#         return mo.status.toast(f"Error: {str(e)}", kind="danger")

# btn_create_confirm = mo.ui.button(
#     label=f"{mo.icon('fluent:notebook-add-20-regular', size=24)} Create",
#     on_click=handle_create_notebook,
#     full_width=False,
#     tooltip="Create new notebook",
# )


# btn_duplicate = mo.ui.button(
#     label=f"{mo.icon('lucide:copy', size=24)} Duplicate",
#     on_click=duplicate,
#     tooltip="Duplicate current notebook",
#     full_width=False
# )

# sidebar_content = mo.Html(
#     f"""
#     <style>
#         .git-panel {{ display: flex; flex-direction: column; gap: 8px; padding: 4px; }}
        
#         details.tool-expander {{ 
#             width: 100%; 
#             border-bottom: 3px solid var(--gray-3, #f3f4f6); 
#             padding-bottom: 4px; 
#         }}
        
#         details.tool-expander > summary {{ 
#             list-style: none; cursor: pointer; 
#             display: flex; justify-content: center;
#             padding: 10px; border-radius: 6px;
#             transition: background 0.2s ease;
#         }}
        
#         details.tool-expander > summary::-webkit-details-marker {{ display: none; }}
#         details.tool-expander > summary:hover {{ background: var(--gray-2, #f9fafb); }}

#         .expander-content {{
#             display: flex; flex-direction: column; gap: 10px;
#             padding: 12px 6px;
#         }}

#         .tools-container {{
#             display: flex; justify-content: center;
#             width: 100%; padding-top: 12px;
#         }}
#     </style>

#     <div class="git-panel">
        
#         <details class="tool-expander" id="create-expander">
#             <summary title="Create new notebook in current directory">
#                 {mo.icon('lucide:file-plus', size=24)}
#             </summary>
#             <div class="expander-content">
#                 {create_input}
#                 {btn_create_confirm}
#             </div>
#         </details>
        
#         <details class="tool-expander" id="duplicate-expander">
#             <summary title="Duplicate current notebook in current directory">
#                 {mo.icon('lucide:copy-plus', size=24)}
#             </summary>
#             <div class="expander-content">
#                 {duplicate_input}
#                 {btn_duplicate}
#             </div>
#         </details>

#         <details class="tool-expander" id="commit-expander">
#             <summary title="Commit Changes">
#                 {mo.icon('lucide:folder-git-2', size=24)}
#             </summary>
#             <div class="expander-content">
#                 {commit_input}
#                 <div style="display: flex; gap: 8px;">
#                     {btn_commit}
#                     {btn_revert}
#                 </div>
#             </div>
#         </details>
        
#         <div class="tools-container">
#             {btn_push}
#         </div>
        
#     </div>
    
#     <script>
#         // Closes the expander after an action is taken
#         document.querySelectorAll('.expander-content').forEach(panel => {{
#             panel.addEventListener('click', (e) => {{
#                 if(e.target.closest('marimo-ui-element')) {{
#                     setTimeout(() => {{
#                         panel.parentElement.removeAttribute('open');
#                     }}, 300);
#                 }}
#             }});
#         }});
#     </script>
#     """
# )



def hr(border_top_pixels='1'):
    # Native HTML horizontal rule with a bit of styling for better spacing
    return mo.Html(f'<hr style="border: 0; border-top: {border_top_pixels}px solid #e2e8f0; margin: 1rem 0;">')


# 1. Instantiate UI Elements Globally (Outside the function)
name_input = mo.ui.text(label="Name:")
commit_msg = mo.ui.text_area(label="Commit Message", placeholder="Summarize your changes...")

btn_create = mo.ui.button(
    label=f"{mo.icon('fluent:notebook-add-20-regular')} Create", 
    on_click=lambda _: handle_create(name_input), 
    kind="neutral"
)

btn_duplicate = mo.ui.button(
    label=f"{mo.icon('lucide:copy', size=24)} Duplicate", 
    on_click=lambda _: handle_duplicate(name_input),
    kind='neutral'
)

btn_sync = mo.ui.button(
    label=f"{mo.icon('lucide:git-compare-arrows', size=24)} Save & Sync",
    on_click=lambda _: save(src="notebooks/", push=True), 
    full_width=False
)

btn_reset = mo.ui.button(
    label=f"{mo.icon('lucide:git-branch-minus', size=24)} Discard changes - reset",
    on_click=lambda _: reset_to_remote(),
    kind="danger", 
    full_width=False,
)


# 2. Arrange elements in the function
def create_ui():
    # --- TAB 1: FILE OPERATIONS ---
    file_ops = mo.vstack([

        mo.md("--- Notebook Management"),
        name_input,
        hr(2),
        mo.hstack([
            btn_create,
            btn_duplicate
        ], justify="start")
    ])

    # --- TAB 2: GIT SYNC ---
    git_ops = mo.vstack([
        mo.md("### 🌿 Cloud Sync"),
        mo.md("This will pull changes from others and save your work to GitHub."),
        commit_msg,
        btn_sync,
        hr(),
        mo.md("#### Advanced"),
        btn_reset
    ])

    file_ops_label = f"{mo.icon('lucide:file-plus', size=24)}"
    git_ops_label = f"{mo.icon('lucide:folder-git-2', size=24)}"
    
    return mo.ui.tabs({
        file_ops_label: file_ops,
        git_ops_label: git_ops
    })

def create_sidebar():
    email = os.environ.get("GIT_AUTHOR_EMAIL", None)
    if email:
        tabs = create_ui()
        return mo.sidebar([
            mo.md(f"**User:** {email}"),
            hr(),
            tabs
        ])