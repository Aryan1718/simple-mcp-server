import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse, quote

from fastmcp import FastMCP

# MCP server instance
mcp = FastMCP("overleaf-mcp")

# Overleaf configuration
OVERLEAF_GIT_URL = os.environ.get("OVERLEAF_GIT_URL")
OVERLEAF_EMAIL = os.environ.get("OVERLEAF_EMAIL")  # used only for git commit identity
OVERLEAF_TOKEN = os.environ.get("OVERLEAF_TOKEN")


def run(cmd, cwd=None):
    """
    Run a shell command and capture stderr/stdout so we can see git errors.
    """
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"returncode: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return result


def clone_overleaf_repo() -> Path:
    """
    Clone the Overleaf Git repository using Git authentication token.
    Returns only the repo path without attaching tmpdir to it.
    """
    if not OVERLEAF_GIT_URL or not OVERLEAF_TOKEN:
        raise RuntimeError(
            "Missing Overleaf configuration. Set OVERLEAF_GIT_URL and "
            "OVERLEAF_TOKEN environment variables."
        )

    if not OVERLEAF_GIT_URL.startswith("https://"):
        raise RuntimeError("OVERLEAF_GIT_URL must start with https://")

    # Create temp dir and store it globally to prevent cleanup
    tmpdir = tempfile.TemporaryDirectory()
    repo_dir = Path(tmpdir.name) / "project"

    # Save the tmpdir to a global list to prevent automatic deletion
    # (FastMCP keeps the server alive, so this is safe)
    if "_TMPDIRS" not in globals():
        globals()["_TMPDIRS"] = []
    globals()["_TMPDIRS"].append(tmpdir)

    # Parse base URL
    parsed = urlparse(OVERLEAF_GIT_URL)
    user = "git"
    password = quote(OVERLEAF_TOKEN, safe="")

    # Build netloc: git:TOKEN@git.overleaf.com
    host = parsed.hostname
    netloc = f"{user}:{password}@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"

    auth_url = urlunparse(parsed._replace(netloc=netloc))

    run(["git", "clone", auth_url, str(repo_dir)])

    return repo_dir


@mcp.tool
def read_overleaf_file(path: str = "main.tex") -> str:
    """
    Read a file from the Overleaf project and return its contents as text.
    """
    try:
        repo_dir = clone_overleaf_repo()
    except Exception as e:
        return f"Git clone failed:\n{e}"

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
    Update a file in the Overleaf project and push changes.
    """
    try:
        repo_dir = clone_overleaf_repo()
    except Exception as e:
        return f"Git clone failed:\n{e}"

    file_path = repo_dir / path

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(new_content, encoding="utf-8")

    # Git identity (email is only for metadata; does not affect auth)
    email = OVERLEAF_EMAIL or "overleaf-mcp@example.com"
    run(["git", "config", "user.name", "Overleaf MCP Bot"], cwd=repo_dir)
    run(["git", "config", "user.email", email], cwd=repo_dir)

    # Add + commit
    run(["git", "add", path], cwd=repo_dir)
    try:
        run(["git", "commit", "-m", commit_message], cwd=repo_dir)
    except RuntimeError:
        return "No changes to commit; file is unchanged."

    # Push (try main, then master)
    try:
        run(["git", "push", "origin", "main"], cwd=repo_dir)
    except RuntimeError:
        run(["git", "push", "origin", "master"], cwd=repo_dir)

    return f"Successfully updated '{path}' and pushed to Overleaf."


if __name__ == "__main__":
    mcp.run()
