import git
import marimo as mo
import os

# # --- Internal Logic ---

# def get_repo():
#     try:
#         return git.Repo(".", search_parent_directories=True)
#     except:
#         return None

# def git_commit_only(message):
#     repo = get_repo()
#     print(f"DEBUG: git_commit_only triggered with message: {message}")
#     if not repo:
#         return mo.status.error("No git repository found.")
#     if not message.strip():
#         return mo.status.warning("Commit message is required.")
#     try:
#         # Assuming files are already added/staged
#         #commit = repo.index.commit(message)
#         #return mo.status.success(f"Local commit successful: {commit.hexsha[:7]}")
#         return mo.status.success(f"Local commit successful")
#     except Exception as e:
#         return mo.status.error(f"Commit failed: {str(e)}")

# def git_push_origin(_):
#     repo = get_repo()
#     if not repo:
#         return mo.status.error("No git repository found.")
#     try:
#         origin = repo.remote(name='origin')
#         #origin.push()
#         return mo.status.success("Successfully pushed to origin.")
#     except Exception as e:
#         return mo.status.error(f"Push failed: {str(e)}")

# # --- UI Components ---

# email = os.environ.get("GIT_AUTHOR_EMAIL", "developer@careatlas.app")



# commit_button = mo.ui.button(label=" ", full_width=True, on_click=lambda _: print("Save action triggered!"))
# push_button = mo.ui.button(label=" ", full_width=True, on_click=git_push_origin)


# 1. Configuration
email = os.environ.get("GIT_AUTHOR_EMAIL", "NONE")

# Use standard strings (Unicode icons work perfectly)
btn_save = mo.ui.button(
    label="↡",
    on_click=lambda _: mo.status.toast("Commit action triggered in Python!", kind="danger"), 
    tooltip="Commit changes to local repository",
    full_width=False
)

btn_run = mo.ui.button(
    label="↑", 
    on_click=lambda _: mo.status.toast("Push action triggered in Python!", kind="success"), 
    tooltip="Push commits to origin",
    full_width=False
)

sidebar_content = mo.Html(
    f"""
    <style>
        .git-panel {{
            display: flex; flex-direction: column; gap: 12px; padding: 4px;
        }}
        
        /* Apply a smooth, minimal lift and shadow directly to the native Marimo element */
        .git-panel marimo-ui-element {{
            transition: transform 0.2s ease, filter 0.2s ease;
        }}
        .git-panel marimo-ui-element:hover {{
            transform: translateY(-2px);
            filter: drop-shadow(0 4px 4px rgba(0,0,0,0.05)) brightness(1.02);
        }}
        .git-panel marimo-ui-element:active {{
            transform: translateY(0);
        }}

        .user-header {{
            display: flex; align-items: center; width: 100%; overflow: hidden;
            padding-bottom: 12px; border-bottom: 1px solid var(--gray-4, #e5e7eb);
            color: var(--gray-11, #6b7280); font-weight: bold; font-size: 0.9rem;
        }}
    </style>

    <div class="git-panel">
        <div class="user-header">
            <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                {email}
            </span>
        </div>
        {btn_save}
        {btn_run}
    </div>
    """
)

def show_sidebar(mmod=None):
    if email and mmod:
        return mmod.sidebar(sidebar_content)