import os
import subprocess
import tempfile
from pathlib import Path

from fastmcp import FastMCP

# MCP server instance
mcp = FastMCP("overleaf-mcp")

# Overleaf configuration
OVERLEAF_GIT_URL = os.environ.get("OVERLEAF_GIT_URL")
OVERLEAF_EMAIL = os.environ.get("OVERLEAF_EMAIL")
OVERLEAF_TOKEN = os.environ.get("OVERLEAF_TOKEN")


def run(cmd, cwd=None):
    """
    Run a shell command and capture stderr/stdout so we can see git errors.
    """
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True
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
    Clone the Overleaf Git repository using email + Overleaf Git authentication token.
    """
    if not OVERLEAF_GIT_URL or not OVERLEAF_EMAIL or not OVERLEAF_TOKEN:
        raise RuntimeError(
            "Missing Overleaf configuration. Set OVERLEAF_GIT_URL, "
            "OVERLEAF_EMAIL, and OVERLEAF_TOKEN environment variables."
        )

    # Temporary directory
    tmpdir = tempfile.TemporaryDirectory()
    repo_dir = Path(tmpdir.name) / "project"

    # Construct authenticated URL
    # Example final URL:
    #   https://email:token@git.overleaf.com/project-id
    if not OVERLEAF_GIT_URL.startswith("https://"):
        raise RuntimeError("OVERLEAF_GIT_URL must start with https://")

    auth_url = OVERLEAF_GIT_URL.replace(
        "https://",
        f"https://{OVERLEAF_EMAIL}:{OVERLEAF_TOKEN}@"
    )

    # Perform git clone
    run(["git", "clone", auth_url, str(repo_dir)])

    # Keep temp directory alive
    repo_dir._tmpdir = tmpdir
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

    # Git identity
    run(["git", "config", "user.name", "Overleaf MCP Bot"], cwd=repo_dir)
    run(["git", "config", "user.email", OVERLEAF_EMAIL], cwd=repo_dir)

    # Add + commit
    run(["git", "add", path], cwd=repo_dir)
    try:
        run(["git", "commit", "-m", commit_message], cwd=repo_dir)
    except RuntimeError:
        return "No changes to commit; file is unchanged."

    # Push
    try:
        run(["git", "push", "origin", "main"], cwd=repo_dir)
    except RuntimeError:
        run(["git", "push", "origin", "master"], cwd=repo_dir)

    return f"Successfully updated '{path}' and pushed to Overleaf."


if __name__ == "__main__":
    mcp.run()
