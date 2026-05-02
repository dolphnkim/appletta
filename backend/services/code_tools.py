"""Code agent tools — file system, search, and shell access for Kevin.

All file operations are sandboxed to WORKSPACE_ROOT. Paths outside the
workspace are rejected with an error. Shell commands run inside a macOS
seatbelt (sandbox-exec) that blocks writes outside the workspace and
prevents malware from installing persistence mechanisms.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Workspace root — the Persist repo directory
# ---------------------------------------------------------------------------

# backend/services/code_tools.py  →  .parent.parent.parent  →  repo root
WORKSPACE_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# macOS sandbox (seatbelt)
# ---------------------------------------------------------------------------

_SANDBOX_PROFILE_PATH: Optional[Path] = None


def _build_sandbox_profile() -> str:
    """Generate a macOS seatbelt profile for Kevin's shell.

    Strategy:
      - Allow everything by default (process execution, reads, network)
      - Deny all file writes
      - Re-allow writes only to: workspace, /tmp, SSH, package caches
      - Hard-deny persistence locations (LaunchAgents/Daemons) last
        so they can't be opened even by an earlier allow

    The "most specific / last matching rule wins" behaviour of SBPL
    means the final (deny ...) blocks for LaunchAgents override the
    broader (allow ...) for ~/.config etc.
    """
    ws   = str(WORKSPACE_ROOT)
    home = str(Path.home())
    return f"""\
(version 1)

; ── Base ────────────────────────────────────────────────────────────────────
(allow default)          ; allow process execution, reads, network by default

; ── Write restrictions ──────────────────────────────────────────────────────
(deny file-write*)       ; block all writes …

; workspace: full read/write
(allow file-write* (subpath "{ws}"))

; standard temp locations
(allow file-write*
    (subpath "/private/tmp")
    (subpath "/private/var/folders")
    (subpath "/tmp"))

; character devices every shell needs
(allow file-write*
    (literal "/dev/null")
    (literal "/dev/stdout")
    (literal "/dev/stderr")
    (literal "/dev/tty"))

; git needs to update known_hosts on first connect
(allow file-write* (subpath "{home}/.ssh"))

; package manager caches (pip, npm, brew, etc.)
(allow file-write*
    (subpath "{home}/.npm")
    (subpath "{home}/.cache")
    (subpath "{home}/.config")
    (subpath "{home}/Library/Caches")
    (subpath "{home}/Library/Preferences")
    (subpath "/opt/homebrew/var"))

; ── Hard-deny persistence — overrides everything above ──────────────────────
(deny file-write*
    (subpath "{home}/Library/LaunchAgents")
    (subpath "{home}/Library/LaunchDaemons")
    (subpath "/Library/LaunchAgents")
    (subpath "/Library/LaunchDaemons")
    (subpath "/System/Library/LaunchAgents")
    (subpath "/System/Library/LaunchDaemons"))
"""


def _ensure_sandbox_profile() -> Optional[Path]:
    """Write the sandbox profile to disk once; return its path (or None if unavailable)."""
    global _SANDBOX_PROFILE_PATH

    if not shutil.which("sandbox-exec"):
        return None

    if _SANDBOX_PROFILE_PATH is not None and _SANDBOX_PROFILE_PATH.exists():
        return _SANDBOX_PROFILE_PATH

    profile_path = WORKSPACE_ROOT / ".kevin_sandbox.sb"
    profile_path.write_text(_build_sandbox_profile())
    _SANDBOX_PROFILE_PATH = profile_path
    return profile_path


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def _resolve_path(path: str) -> Optional[Path]:
    """Resolve *path* relative to WORKSPACE_ROOT and confirm it stays inside.

    Returns the resolved absolute Path, or None if the path escapes the workspace.
    """
    p = Path(path)
    if p.is_absolute():
        full = p.resolve()
    else:
        full = (WORKSPACE_ROOT / p).resolve()

    try:
        full.relative_to(WORKSPACE_ROOT.resolve())
        return full
    except ValueError:
        return None  # Path traversal attempt


# ---------------------------------------------------------------------------
# Shell safety
# ---------------------------------------------------------------------------

_BLOCKED = [
    r"\brm\s+-[a-z]*f[a-z]*\s",   # rm -rf / rm -f
    r"\bsudo\b",
    r"\bsu\b",
    r"\bdd\b",
    r"\bmkfs\b",
    r"\bshred\b",
    r"\bfdisk\b",
    r"\bparted\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r":\(\)\s*\{",               # fork bomb opener
    r"\|\s*(sh|bash|zsh|fish)\b", # pipe to shell
    r">\s*/etc/",
    r">\s*/usr/",
    r">\s*/bin/",
    r">\s*/sbin/",
    r">\s*/dev/",
    r">\s*/sys/",
]

_BLOCKED_RE = re.compile("|".join(_BLOCKED), re.IGNORECASE)


def _is_safe_command(command: str) -> bool:
    return not bool(_BLOCKED_RE.search(command))


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def read_file(path: str, offset: int = 0, limit: Optional[int] = None) -> Dict[str, Any]:
    """Read a file from the workspace."""
    full = _resolve_path(path)
    if full is None:
        return {"error": f"Path '{path}' is outside the workspace ({WORKSPACE_ROOT})"}
    if not full.exists():
        return {"error": f"File not found: {path}"}
    if not full.is_file():
        return {"error": f"Not a file: {path}"}

    # Reject obvious binaries
    try:
        raw = full.read_bytes()
        if b"\x00" in raw[:8192]:
            return {"error": f"Binary file — use a text file path: {path}"}
        content = raw.decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Could not read file: {e}"}

    lines = content.splitlines(keepends=True)
    if offset:
        lines = lines[offset:]
    if limit is not None:
        lines = lines[:limit]
    content = "".join(lines)

    MAX = 50_000
    truncated = len(content) > MAX
    if truncated:
        content = content[:MAX]

    return {
        "path": str(full.relative_to(WORKSPACE_ROOT)),
        "content": content,
        "lines": len(lines),
        "truncated": truncated,
    }


def write_file(path: str, content: str) -> Dict[str, Any]:
    """Create or overwrite a file in the workspace."""
    full = _resolve_path(path)
    if full is None:
        return {"error": f"Path '{path}' is outside the workspace ({WORKSPACE_ROOT})"}

    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "path": str(full.relative_to(WORKSPACE_ROOT)),
            "bytes_written": len(content.encode()),
        }
    except Exception as e:
        return {"error": f"Write failed: {e}"}


def list_directory(path: str = ".") -> Dict[str, Any]:
    """List entries in a workspace directory."""
    full = _resolve_path(path)
    if full is None:
        return {"error": f"Path '{path}' is outside the workspace"}
    if not full.exists():
        return {"error": f"Directory not found: {path}"}
    if not full.is_dir():
        return {"error": f"Not a directory: {path}"}

    try:
        entries = []
        for entry in sorted(full.iterdir()):
            # Skip hidden and cache dirs to keep output clean
            if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules", ".venv"):
                continue
            entries.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            })
        return {
            "path": str(full.relative_to(WORKSPACE_ROOT)),
            "entries": entries,
            "count": len(entries),
        }
    except Exception as e:
        return {"error": str(e)}


def search_files(pattern: str, directory: str = ".") -> Dict[str, Any]:
    """Glob for files matching *pattern* inside *directory*."""
    full_dir = _resolve_path(directory)
    if full_dir is None:
        return {"error": f"Directory '{directory}' is outside the workspace"}
    if not full_dir.is_dir():
        return {"error": f"Not a directory: {directory}"}

    try:
        matches = [
            str(p.relative_to(WORKSPACE_ROOT))
            for p in full_dir.rglob(pattern)
            if p.is_file()
            and "__pycache__" not in p.parts
            and ".venv" not in p.parts
            and "node_modules" not in p.parts
        ]
        matches.sort()
        return {"pattern": pattern, "matches": matches[:200], "count": len(matches)}
    except Exception as e:
        return {"error": str(e)}


def search_content(query: str, path: str = ".", file_pattern: str = "*") -> Dict[str, Any]:
    """Search file contents for *query* (case-insensitive) using grep."""
    full = _resolve_path(path)
    if full is None:
        return {"error": f"Path '{path}' is outside the workspace"}
    if not full.exists():
        return {"error": f"Path not found: {path}"}

    search_root = full if full.is_dir() else full.parent

    try:
        cmd = [
            "grep", "-r", "-n", "-i",
            "--include", file_pattern,
            "--exclude-dir", "__pycache__",
            "--exclude-dir", ".venv",
            "--exclude-dir", "node_modules",
            "--exclude-dir", ".git",
            query,
            str(search_root),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        raw_lines = result.stdout.splitlines()[:100]  # cap results

        hits = []
        for line in raw_lines:
            # grep output: /abs/path/file.py:42:  matched line
            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path, lineno, text = parts[0], parts[1], parts[2]
                try:
                    rel = str(Path(file_path).relative_to(WORKSPACE_ROOT))
                except ValueError:
                    rel = file_path
                hits.append({"file": rel, "line": int(lineno), "text": text.strip()})
            else:
                hits.append({"raw": line})

        return {"query": query, "results": hits, "count": len(hits)}
    except subprocess.TimeoutExpired:
        return {"error": "Search timed out (>15s)"}
    except Exception as e:
        return {"error": str(e)}


def run_shell(command: str, timeout: int = 30) -> Dict[str, Any]:
    """Run a shell command in the workspace root, inside the macOS seatbelt.

    The sandbox (sandbox-exec) restricts file writes to the workspace, /tmp,
    SSH, and package-manager caches. Persistence locations (LaunchAgents/
    LaunchDaemons) are hard-blocked so malware can't install itself.

    The keyword blocklist still runs first as a fast pre-check.
    Working directory is always the workspace root.
    """
    if not _is_safe_command(command):
        return {"error": f"Command blocked by safety filter: {command!r}"}

    sandbox = _ensure_sandbox_profile()

    if sandbox:
        # Run inside macOS seatbelt
        cmd = ["sandbox-exec", "-f", str(sandbox), "sh", "-c", command]
        use_shell = False
    else:
        # sandbox-exec unavailable — fall back to unsandboxed (dev only)
        print("[code_tools] WARNING: sandbox-exec not found, running unsandboxed")
        cmd = command
        use_shell = True

    try:
        result = subprocess.run(
            cmd,
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_ROOT),
        )
        stdout = result.stdout[:10_000]
        stderr = result.stderr[:2_000]
        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0,
            "sandboxed": sandbox is not None,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

CODE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file in the Persist workspace. "
                "Paths are relative to the repo root (e.g. 'backend/services/tools.py'). "
                "Returns the file content as a string. Large files are truncated at 50,000 chars. "
                "Use offset/limit to read specific line ranges."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root, e.g. 'backend/services/tools.py'"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (0-indexed, default: 0)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of lines to return (omit for full file)"
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a file in the Persist workspace. "
                "Creates parent directories automatically. "
                "All changes are tracked by git so nothing is permanent — you can always revert. "
                "Use this to implement features, fix bugs, or create new files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root"
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content to write to the file"
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": (
                "List files and subdirectories at a path in the workspace. "
                "Use '.' for the repo root. Skips hidden files, __pycache__, .venv, node_modules."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to repo root (default: '.' = repo root)"
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "Find files by name pattern using glob syntax. "
                "Examples: '**/*.py' finds all Python files, '*.tsx' finds TypeScript files in a dir. "
                "Returns a list of matching file paths relative to the repo root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '**/*.py', 'frontend/src/**/*.tsx'"
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to search in (default: '.' = repo root)"
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_content",
            "description": (
                "Search file contents for a string or pattern (case-insensitive grep). "
                "Returns matching lines with file paths and line numbers. "
                "Use file_pattern to narrow to specific file types, e.g. '*.py' or '*.ts'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to search for"
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search in (default: '.' = whole repo)"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Limit search to files matching this pattern, e.g. '*.py' (default: '*')"
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Run a shell command in the Persist repo root. "
                "Use this for git operations, running tests, installing packages, building the frontend, etc. "
                "Examples: 'git status', 'git diff', 'git add -p', 'git commit -m \"msg\"', "
                "'python -m pytest backend/', 'npm run build'. "
                "Destructive commands (rm -rf, sudo, dd, etc.) are blocked. "
                "Output is capped at 10,000 chars."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds to wait (default: 30)"
                    },
                },
                "required": ["command"],
            },
        },
    },
]
