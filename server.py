import os
import subprocess
import tempfile
from pathlib import Path

from fastmcp import FastMCP

# MCP server instance (FastMCP Cloud entrypoint: server.py:mcp)
mcp = FastMCP("overleaf-mcp")

# Overleaf configuration from environment
OVERLEAF_GIT_URL = os.environ.get("OVERLEAF_GIT_URL")
OVERLEAF_EMAIL = os.environ.get("OVERLEAF_EMAIL")
OVERLEAF_TOKEN = os.environ.get("OVERLEAF_TOKEN")


def run(cmd, cwd=None):
    """Run a shell command and raise if it fails."""
    subprocess.check_call(cmd, cwd=cwd)


def clone_overleaf_repo() -> Path:
    """
    Clone the Overleaf Git repo into a temp dir and return the repo path.
    Uses HTTPS with email + personal access token.
    """
    if not OVERLEAF_GIT_URL or not OVERLEAF_EMAIL or not OVERLEAF_TOKEN:
        raise RuntimeError(
            "Missing Overleaf configuration. "
            "Set OVERLEAF_GIT_URL, OVERLEAF_EMAIL, and OVERLEAF_TOKEN env vars."
        )

    # Create temp dir for this operation
    tmpdir = tempfile.TemporaryDirectory()
    repo_dir = Path(tmpdir.name) / "project"

    # Auth URL: https://email:token@git.overleaf.com/<project-id>
    auth_url = OVERLEAF_GIT_URL.replace(
        "https://",
        f"https://{OVERLEAF_EMAIL}:{OVERLEAF_TOKEN}"
    )

    run(["git", "clone", auth_url, str(repo_dir)])

    # Keep the TemporaryDirectory alive by attaching it
    repo_dir._tmpdir = tmpdir  # type: ignore[attr-defined]
    return repo_dir


@mcp.tool
def read_overleaf_file(path: str = "main.tex") -> str:
    """
    Read a file from the Overleaf project and return its content as text.

    Parameters
    ----------
    path : str
        Relative path to the file inside the Overleaf repo (default: 'main.tex').

    Returns
    -------
    str
        File content, or an error message if the file does not exist.
    """
    repo_dir = clone_overleaf_repo()
    file_path = repo_dir / path

    if not file_path.exists():
        return f"File '{path}' does not exist in the Overleaf project."

    return file_path.read_text(encoding="utf-8")


@mcp.tool
def update_overleaf_file(
    path: str,
    new_content: str,
    commit_message: str = "Update file via Overleaf MCP",
) -> str:
    """
    Overwrite a file in the Overleaf project with new content and push changes.

    Parameters
    ----------
    path : str
        Relative path to the file inside the Overleaf repo (e.g., 'main.tex').
    new_content : str
        New content to write into the file.
    commit_message : str
        Git commit message.

    Returns
    -------
    str
        Status message.
    """
    repo_dir = clone_overleaf_repo()
    file_path = repo_dir / path

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(new_content, encoding="utf-8")

    # Set git identity
    run(["git", "config", "user.name", "Overleaf MCP Bot"], cwd=repo_dir)
    run(["git", "config", "user.email", OVERLEAF_EMAIL], cwd=repo_dir)

    run(["git", "add", path], cwd=repo_dir)

    # Commit (if there are changes)
    try:
        run(["git", "commit", "-m", commit_message], cwd=repo_dir)
    except subprocess.CalledProcessError:
        return "No changes to commit; file content is unchanged."

    # Push to 'main', fall back to 'master' if needed
    try:
        run(["git", "push", "origin", "main"], cwd=repo_dir)
    except subprocess.CalledProcessError:
        run(["git", "push", "origin", "master"], cwd=repo_dir)

    return f"Successfully updated '{path}' and pushed to Overleaf."


if __name__ == "__main__":
    mcp.run()
