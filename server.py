import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse, quote
import re

from fastmcp import FastMCP

# MCP server instance
mcp = FastMCP("overleaf-mcp")

# Overleaf configuration
OVERLEAF_GIT_URL = os.environ.get("OVERLEAF_GIT_URL")
OVERLEAF_EMAIL = os.environ.get("OVERLEAF_EMAIL")  # only for commit identity
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

    OVERLEAF_GIT_URL should be the plain project URL, e.g.:
        https://git.overleaf.com/68e0....

    OVERLEAF_TOKEN is your Git authentication token from Overleaf.
    """
    if not OVERLEAF_GIT_URL or not OVERLEAF_TOKEN:
        raise RuntimeError(
            "Missing Overleaf configuration. Set OVERLEAF_GIT_URL and "
            "OVERLEAF_TOKEN environment variables."
        )

    if not OVERLEAF_GIT_URL.startswith("https://"):
        raise RuntimeError("OVERLEAF_GIT_URL must start with https://")

    # Create temp dir and keep a global reference so it's not cleaned up early
    tmpdir = tempfile.TemporaryDirectory()
    repo_dir = Path(tmpdir.name) / "project"
    if "_TMPDIRS" not in globals():
        globals()["_TMPDIRS"] = []
    globals()["_TMPDIRS"].append(tmpdir)

    # Parse the base URL (e.g. https://git.overleaf.com/<project-id>)
    parsed = urlparse(OVERLEAF_GIT_URL)
    if not parsed.hostname:
        raise RuntimeError(f"Invalid OVERLEAF_GIT_URL: {OVERLEAF_GIT_URL}")

    # Overleaf expects: username "git", password = token.
    # We embed that as: https://git:<token>@git.overleaf.com/<project-id>
    user = "git"
    password = quote(OVERLEAF_TOKEN, safe="")

    host = parsed.hostname
    netloc = f"{user}:{password}@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"

    auth_url = urlunparse(parsed._replace(netloc=netloc))

    # Perform git clone
    run(["git", "clone", auth_url, str(repo_dir)])

    return repo_dir


def _latex_preview(text: str) -> str:
    """
    Produce a human-friendly preview from LaTeX:
    - Strip preamble and document env markers
    - Render section headings as plain text
    - Render \\item lines as bullets
    - Skip comments and empty lines
    """
    lines = text.splitlines()
    out: list[str] = []

    section_cmds = ["section", "subsection", "subsubsection", "cvsection", "chapter"]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("%"):
            continue
        if stripped.startswith("\\documentclass"):
            continue
        if stripped.startswith("\\usepackage"):
            continue
        if stripped.startswith("\\begin{document}") or stripped.startswith("\\end{document}"):
            continue

        # Section-like commands: \section{Title}, \section*{Title}, etc.
        m = re.match(r"\\([a-zA-Z]+)\*?\{([^}]*)\}", stripped)
        if m and m.group(1) in section_cmds:
            title = m.group(2).strip()
            out.append("")
            out.append(title.upper())
            out.append("-" * len(title))
            continue

        # \item lines -> bullet points
        if stripped.startswith("\\item"):
            content = stripped[len("\\item"):].lstrip()
            out.append(f"- {content}")
            continue

        # Default: include line as-is (this may still contain some LaTeX, but less noise)
        out.append(stripped)

    return "\n".join(out).strip()


@mcp.tool
def read_overleaf_file(
    path: str = "main.tex",
    raw: bool = False,
) -> str:
    """
    Read a file from the Overleaf project.

    Parameters
    ----------
    path : str
        Relative path to the file inside the Overleaf repo.
    raw : bool
        If True, return full LaTeX source.
        If False, return a human-friendly preview (no full preamble/boilerplate).
    """
    try:
        repo_dir = clone_overleaf_repo()
    except Exception as e:
        return f"Git clone failed:\n{e}"

    file_path = repo_dir / path

    if not file_path.exists():
        return f"File '{path}' does not exist in the Overleaf project."

    content = file_path.read_text(encoding="utf-8")

    if raw:
        return content

    return _latex_preview(content)


@mcp.tool
def update_overleaf_file(
    path: str,
    new_content: str,
    commit_message: str = "Update file via Overleaf MCP",
) -> str:
    """
    Update a file in the Overleaf project and push changes.
    This overwrites the entire file.
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


@mcp.tool
def list_overleaf_files() -> list[str]:
    """
    List all files in the Overleaf project (recursively).
    Does NOT include .git directory.
    Returns a list of relative file paths.
    """
    try:
        repo_dir = clone_overleaf_repo()
    except Exception as e:
        return [f"Git clone failed: {e}"]

    file_paths: list[str] = []

    for root, dirs, files in os.walk(repo_dir):
        # Skip .git
        if ".git" in dirs:
            dirs.remove(".git")

        for file in files:
            full_path = Path(root) / file
            rel_path = full_path.relative_to(repo_dir)
            file_paths.append(str(rel_path))

    return file_paths


@mcp.tool
def update_overleaf_section(
    path: str,
    section_title: str,
    new_section_body: str,
    heading_command: str = "section",
    commit_message: str | None = None,
) -> str:
    """
    Replace ONLY the body of a LaTeX section with a given title, and push changes.

    Example:
        path = "ARYAN-PANDIT-RESUME-2/dothis.tex"
        section_title = "Experience"
        heading_command = "section"  (matches \\section{Experience} or \\section*{Experience})
    """
    try:
        repo_dir = clone_overleaf_repo()
    except Exception as e:
        return f"Git clone failed:\n{e}"

    file_path = repo_dir / path
    if not file_path.exists():
        return f"File '{path}' does not exist in the Overleaf project."

    text = file_path.read_text(encoding="utf-8")

    heading_cmd_escaped = re.escape(heading_command)
    title_escaped = re.escape(section_title)

    pattern = (
        rf"(\\{heading_cmd_escaped}\*?\{{{title_escaped}\}}\s*)"  # header
        rf"(.*?)"                                                # body
        rf"(?=("                                                 # stop before next header/end
        rf"\\{heading_cmd_escaped}\b|"
        rf"\\section\b|"
        rf"\\subsection\b|"
        rf"\\chapter\b|"
        rf"\\cvsection\b|"
        rf"\\end\{{document\}}"
        rf"))"
    )
    regex = re.compile(pattern, re.DOTALL)

    def replacer(match: re.Match) -> str:
        header = match.group(1)
        body = new_section_body.strip() + "\n"
        return header + body

    new_text, count = regex.subn(replacer, text, count=1)

    if count == 0:
        return (
            f"Section '{section_title}' with heading '\\{heading_command}' "
            f"not found in '{path}'. No changes made."
        )

    file_path.write_text(new_text, encoding="utf-8")

    email = OVERLEAF_EMAIL or "overleaf-mcp@example.com"
    run(["git", "config", "user.name", "Overleaf MCP Bot"], cwd=repo_dir)
    run(["git", "config", "user.email", email], cwd=repo_dir)

    run(["git", "add", path], cwd=repo_dir)

    if commit_message is None:
        commit_message = f"Update section '{section_title}' in {path}"

    try:
        run(["git", "commit", "-m", commit_message], cwd=repo_dir)
    except RuntimeError:
        return "No changes to commit after section replacement."

    try:
        run(["git", "push", "origin", "main"], cwd=repo_dir)
    except RuntimeError:
        run(["git", "push", "origin", "master"], cwd=repo_dir)

    return (
        f"Successfully updated section '{section_title}' in '{path}' "
        f"and pushed to Overleaf."
    )


if __name__ == "__main__":
    mcp.run()
