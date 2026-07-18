"""
Tool registry and implementations.

Each tool is a plain Python function decorated with @tool.
The registry exposes OpenAI-style function-calling schemas so the
assistant can decide which tool to invoke.

Categories
----------
system      – OS info, settings, services, reboot, env vars, drivers
files       – create/edit/delete/move/copy/rename/search/encrypt/compress
network     – connectivity, Wi-Fi, DNS, ports, VPN, SSL, traffic
security    – permissions, malware scan, firewall, auth logs
processes   – launch/stop/monitor/schedule
programming – generate/explain/refactor/debug/run/test code
databases   – query/export/optimize/backup
cloud       – cloud CLI discovery
containers  – build/run/logs/compose
virt        – virtual machine discovery
web         – search/scrape/summarize/monitor
productivity– calendar/tasks/notes/goals/checklists
email       – draft and categorize messages
documents   – PDF/convert/summarize/OCR
ai_data     – analyze/clean/visualize data, forecasts
multimedia  – image/audio/video utilities
mobile      – Android device discovery
smarthome   – Home Assistant state and service control
finance     – expenses/budget/subscriptions
research    – gather refs/summarize papers
pkm         – store/retrieve memories, knowledge graphs
monitoring  – system/app/site health
automation  – workflows, triggers, watchers
"""

from __future__ import annotations

import ast
import csv
import fnmatch
import glob as _glob
import hashlib
import importlib
import inspect
import io
import json
import logging
import mimetypes
import os
import platform
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import traceback
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── Registry ────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, dict] = {}  # name → {fn, schema}


def tool(
    name: Optional[str] = None,
    description: str = "",
    parameters: Optional[dict] = None,
    category: str = "",
    requires_approval: bool = False,
):
    """Decorator that registers a function as a callable tool."""
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        doc = description or (inspect.getdoc(fn) or "")
        schema: dict = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": doc,
                "parameters": parameters or {"type": "object", "properties": {}, "required": []},
            },
        }
        _REGISTRY[tool_name] = {
            "fn": fn,
            "schema": schema,
            "category": category,
            "requires_approval": requires_approval,
        }
        return fn
    return decorator


def get_schemas(categories: Optional[list[str]] = None) -> list[dict]:
    """Return OpenAI tool schemas, optionally filtered by category."""
    result = []
    for entry in _REGISTRY.values():
        if categories is None or entry["category"] in categories:
            result.append(entry["schema"])
    return result


def call_tool(name: str, arguments: dict) -> Any:
    """Dispatch a tool call by name."""
    if name not in _REGISTRY:
        raise ValueError(f"Unknown tool: {name}")
    fn = _REGISTRY[name]["fn"]
    return fn(**arguments)


def list_tools() -> list[dict]:
    return [
        {
            "name": n,
            "category": v["category"],
            "description": v["schema"]["function"]["description"],
            "requires_approval": v["requires_approval"],
        }
        for n, v in _REGISTRY.items()
    ]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd: list[str] | str, timeout: int = 30, shell: bool = False) -> dict:
    """Run a subprocess and return {stdout, stderr, returncode}."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=shell
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Timed out", "returncode": -1}
    except FileNotFoundError as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


def _ok(data: Any) -> dict:
    return {"status": "ok", "result": data}


def _err(msg: str) -> dict:
    return {"status": "error", "error": msg}


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="system_info",
    description="Return OS, hardware, and uptime information.",
    parameters={"type": "object", "properties": {}, "required": []},
    category="system_read",
)
def system_info() -> dict:
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": socket.gethostname(),
        "python": sys.version,
    }
    try:
        import psutil
        info["cpu_count"] = psutil.cpu_count()
        info["cpu_percent"] = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        info["memory_total_gb"] = round(mem.total / 1e9, 2)
        info["memory_available_gb"] = round(mem.available / 1e9, 2)
        info["memory_percent"] = mem.percent
        info["uptime_seconds"] = int(time.time() - psutil.boot_time())
    except ImportError:
        pass
    return _ok(info)


@tool(
    name="get_env_vars",
    description="Return current environment variables, optionally filtered by a prefix.",
    parameters={
        "type": "object",
        "properties": {
            "prefix": {"type": "string", "description": "Optional prefix filter (case-insensitive)"},
        },
        "required": [],
    },
    category="system_read",
)
def get_env_vars(prefix: str = "") -> dict:
    env = {k: v for k, v in os.environ.items()
           if not prefix or k.upper().startswith(prefix.upper())}
    return _ok(env)


@tool(
    name="set_env_var",
    description="Set an environment variable for the current process.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["name", "value"],
    },
    category="system",
    requires_approval=True,
)
def set_env_var(name: str, value: str) -> dict:
    os.environ[name] = value
    return _ok(f"Set {name}={value}")


@tool(
    name="list_services",
    description="List system services and their status (systemd or launchctl).",
    parameters={"type": "object", "properties": {}, "required": []},
    category="system_read",
)
def list_services() -> dict:
    sys_name = platform.system()
    if sys_name == "Linux":
        r = _run(["systemctl", "list-units", "--type=service", "--no-pager", "--no-legend"])
    elif sys_name == "Darwin":
        r = _run(["launchctl", "list"])
    else:
        return _err("Unsupported OS for service listing")
    return _ok(r["stdout"])


@tool(
    name="manage_service",
    description="Start, stop, restart, or get status of a named system service.",
    parameters={
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Service name"},
            "action": {"type": "string", "enum": ["start", "stop", "restart", "status"]},
        },
        "required": ["service", "action"],
    },
    category="system",
    requires_approval=True,
)
def manage_service(service: str, action: str) -> dict:
    sys_name = platform.system()
    if sys_name == "Linux":
        r = _run(["systemctl", action, service])
    elif sys_name == "Darwin":
        if action == "status":
            r = _run(["launchctl", "list", service])
        else:
            cmd = "load" if action == "start" else "unload"
            r = _run(["launchctl", cmd, service])
    else:
        return _err("Unsupported OS")
    return _ok(r)


@tool(
    name="install_package",
    description="Install a system or Python package.",
    parameters={
        "type": "object",
        "properties": {
            "package": {"type": "string"},
            "manager": {"type": "string", "enum": ["pip", "apt", "brew", "npm"],
                        "description": "Package manager to use"},
        },
        "required": ["package", "manager"],
    },
    category="system",
    requires_approval=True,
)
def install_package(package: str, manager: str) -> dict:
    cmds = {
        "pip": [sys.executable, "-m", "pip", "install", package],
        "apt": ["apt-get", "install", "-y", package],
        "brew": ["brew", "install", package],
        "npm": ["npm", "install", "-g", package],
    }
    if manager not in cmds:
        return _err(f"Unknown manager: {manager}")
    return _ok(_run(cmds[manager], timeout=120))


@tool(
    name="reboot_system",
    description="Reboot, shutdown, suspend, or hibernate the system.",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["reboot", "shutdown", "suspend", "hibernate"]},
        },
        "required": ["action"],
    },
    category="system",
    requires_approval=True,
)
def reboot_system(action: str) -> dict:
    sys_name = platform.system()
    cmds: dict[str, dict[str, list[str]]] = {
        "Linux": {
            "reboot": ["systemctl", "reboot"],
            "shutdown": ["systemctl", "poweroff"],
            "suspend": ["systemctl", "suspend"],
            "hibernate": ["systemctl", "hibernate"],
        },
        "Darwin": {
            "reboot": ["shutdown", "-r", "now"],
            "shutdown": ["shutdown", "-h", "now"],
            "suspend": ["pmset", "sleepnow"],
            "hibernate": ["pmset", "sleepnow"],
        },
    }
    os_cmds = cmds.get(sys_name, {})
    if action not in os_cmds:
        return _err(f"Action '{action}' not supported on {sys_name}")
    return _ok(_run(os_cmds[action]))


# ═══════════════════════════════════════════════════════════════════════════
# FILES
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="read_file",
    description="Read the contents of a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "encoding": {"type": "string", "default": "utf-8"},
            "max_bytes": {"type": "integer", "description": "Max bytes to read", "default": 1048576},
        },
        "required": ["path"],
    },
    category="file_read",
)
def read_file(path: str, encoding: str = "utf-8", max_bytes: int = 1_048_576) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return _err(f"File not found: {p}")
    try:
        with open(p, encoding=encoding, errors="replace") as f:
            content = f.read(max_bytes)
        return _ok({"path": str(p), "size": p.stat().st_size, "content": content})
    except Exception as e:
        return _err(str(e))


@tool(
    name="write_file",
    description="Write text content to a file (creates or overwrites).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "append": {"type": "boolean", "default": False},
        },
        "required": ["path", "content"],
    },
    category="files",
    requires_approval=True,
)
def write_file(path: str, content: str, append: bool = False) -> dict:
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    try:
        with open(p, mode, encoding="utf-8") as f:
            f.write(content)
        return _ok({"path": str(p), "bytes_written": len(content.encode())})
    except Exception as e:
        return _err(str(e))


@tool(
    name="delete_file",
    description="Delete a file or empty directory.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    category="files",
    requires_approval=True,
)
def delete_file(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if p == Path(p.anchor) or p == Path.home():
        return _err("Refusing to delete a filesystem root or home directory")
    if not p.exists():
        return _err(f"Not found: {p}")
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return _ok(f"Deleted {p}")
    except Exception as e:
        return _err(str(e))


@tool(
    name="copy_path",
    description="Copy a file or directory to a destination.",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "destination": {"type": "string"},
        },
        "required": ["source", "destination"],
    },
    category="files",
    requires_approval=True,
)
def copy_path(source: str, destination: str) -> dict:
    src = Path(source).expanduser().resolve()
    dst = Path(destination).expanduser().resolve()
    try:
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return _ok(f"Copied {src} → {dst}")
    except Exception as e:
        return _err(str(e))


@tool(
    name="move_path",
    description="Move or rename a file or directory.",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "destination": {"type": "string"},
        },
        "required": ["source", "destination"],
    },
    category="files",
    requires_approval=True,
)
def move_path(source: str, destination: str) -> dict:
    src = Path(source).expanduser().resolve()
    dst = Path(destination).expanduser().resolve()
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return _ok(f"Moved {src} → {dst}")
    except Exception as e:
        return _err(str(e))


@tool(
    name="search_files",
    description="Search for files matching a glob pattern or containing a text string.",
    parameters={
        "type": "object",
        "properties": {
            "directory": {"type": "string"},
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '*.py'"},
            "contains": {"type": "string", "description": "Optional text to search inside files"},
            "max_results": {"type": "integer", "default": 50},
        },
        "required": ["directory"],
    },
    category="file_read",
)
def search_files(
    directory: str,
    pattern: str = "*",
    contains: str = "",
    max_results: int = 50,
) -> dict:
    base = Path(directory).expanduser().resolve()
    if not base.exists():
        return _err(f"Directory not found: {base}")
    matches: list[str] = []
    for path in base.rglob(pattern):
        if len(matches) >= max_results:
            break
        if path.is_file():
            if contains:
                try:
                    text = path.read_text(errors="replace")
                    if contains.lower() not in text.lower():
                        continue
                except Exception:
                    continue
            matches.append(str(path))
    return _ok({"matches": matches, "count": len(matches)})


@tool(
    name="list_directory",
    description="List contents of a directory.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "show_hidden": {"type": "boolean", "default": False},
        },
        "required": ["path"],
    },
    category="file_read",
)
def list_directory(path: str, show_hidden: bool = False) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return _err(f"Not found: {p}")
    entries = []
    for item in sorted(p.iterdir()):
        if not show_hidden and item.name.startswith("."):
            continue
        stat = item.stat()
        entries.append({
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return _ok(entries)


@tool(
    name="compress_files",
    description="Create a zip archive from a list of files or directories.",
    parameters={
        "type": "object",
        "properties": {
            "sources": {"type": "array", "items": {"type": "string"}},
            "output": {"type": "string", "description": "Output .zip path"},
        },
        "required": ["sources", "output"],
    },
    category="files",
    requires_approval=True,
)
def compress_files(sources: list[str], output: str) -> dict:
    out = Path(output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for src in sources:
                p = Path(src).expanduser().resolve()
                if p.is_dir():
                    for f in p.rglob("*"):
                        if f.is_file():
                            zf.write(f, f.relative_to(p.parent))
                else:
                    zf.write(p, p.name)
        return _ok({"archive": str(out), "size": out.stat().st_size})
    except Exception as e:
        return _err(str(e))


@tool(
    name="extract_archive",
    description="Extract a zip archive to a destination directory.",
    parameters={
        "type": "object",
        "properties": {
            "archive": {"type": "string"},
            "destination": {"type": "string"},
        },
        "required": ["archive", "destination"],
    },
    category="files",
    requires_approval=True,
)
def extract_archive(archive: str, destination: str) -> dict:
    arc = Path(archive).expanduser().resolve()
    dst = Path(destination).expanduser().resolve()
    try:
        with zipfile.ZipFile(arc) as zf:
            zf.extractall(dst)
        return _ok(f"Extracted to {dst}")
    except Exception as e:
        return _err(str(e))


@tool(
    name="checksum_file",
    description="Compute SHA-256 checksum of a file.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    category="file_read",
)
def checksum_file(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return _err(f"Not found: {p}")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return _ok({"path": str(p), "sha256": h.hexdigest()})


@tool(
    name="disk_usage",
    description="Show disk usage for a path.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "default": "/"}},
        "required": [],
    },
    category="file_read",
)
def disk_usage(path: str = "/") -> dict:
    p = Path(path).expanduser().resolve()
    try:
        total, used, free = shutil.disk_usage(p)
        return _ok({
            "path": str(p),
            "total_gb": round(total / 1e9, 2),
            "used_gb": round(used / 1e9, 2),
            "free_gb": round(free / 1e9, 2),
            "used_pct": round(used / total * 100, 1),
        })
    except Exception as e:
        return _err(str(e))


# ═══════════════════════════════════════════════════════════════════════════
# NETWORK
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="check_connectivity",
    description="Check internet connectivity by attempting to reach a host.",
    parameters={
        "type": "object",
        "properties": {
            "host": {"type": "string", "default": "8.8.8.8"},
            "port": {"type": "integer", "default": 53},
            "timeout": {"type": "number", "default": 3.0},
        },
        "required": [],
    },
    category="network_read",
)
def check_connectivity(host: str = "8.8.8.8", port: int = 53, timeout: float = 3.0) -> dict:
    try:
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
        return _ok({"connected": True, "host": host, "port": port})
    except OSError:
        return _ok({"connected": False, "host": host, "port": port})


@tool(
    name="dns_lookup",
    description="Resolve a hostname to IP addresses.",
    parameters={
        "type": "object",
        "properties": {"hostname": {"type": "string"}},
        "required": ["hostname"],
    },
    category="network_read",
)
def dns_lookup(hostname: str) -> dict:
    try:
        results = socket.getaddrinfo(hostname, None)
        addresses = list({r[4][0] for r in results})
        return _ok({"hostname": hostname, "addresses": addresses})
    except socket.gaierror as e:
        return _err(str(e))


@tool(
    name="ping_host",
    description="Ping a host and return latency statistics.",
    parameters={
        "type": "object",
        "properties": {
            "host": {"type": "string"},
            "count": {"type": "integer", "default": 4},
        },
        "required": ["host"],
    },
    category="network_read",
)
def ping_host(host: str, count: int = 4) -> dict:
    sys_name = platform.system()
    flag = "-n" if sys_name == "Windows" else "-c"
    r = _run(["ping", flag, str(count), host], timeout=15)
    return _ok({"host": host, "output": r["stdout"] or r["stderr"]})


@tool(
    name="check_open_ports",
    description="Check which of a list of TCP ports are open on a host.",
    parameters={
        "type": "object",
        "properties": {
            "host": {"type": "string"},
            "ports": {"type": "array", "items": {"type": "integer"}},
            "timeout": {"type": "number", "default": 1.0},
        },
        "required": ["host", "ports"],
    },
    category="network_read",
)
def check_open_ports(host: str, ports: list[int], timeout: float = 1.0) -> dict:
    results = {}
    for port in ports:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                results[port] = "open"
        except (socket.timeout, ConnectionRefusedError, OSError):
            results[port] = "closed"
    return _ok({"host": host, "ports": results})


@tool(
    name="get_public_ip",
    description="Return the public IP address of this machine.",
    parameters={"type": "object", "properties": {}, "required": []},
    category="network_read",
)
def get_public_ip() -> dict:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as r:
            return _ok({"public_ip": r.read().decode().strip()})
    except Exception as e:
        return _err(str(e))


@tool(
    name="http_request",
    description="Perform an HTTP GET or POST request and return the response.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "default": "GET"},
            "headers": {"type": "object", "description": "Optional HTTP headers"},
            "body": {"type": "string", "description": "Optional request body"},
            "timeout": {"type": "integer", "default": 15},
        },
        "required": ["url"],
    },
    category="network_read",
)
def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict] = None,
    body: Optional[str] = None,
    timeout: int = 15,
) -> dict:
    try:
        req = urllib.request.Request(
            url,
            data=body.encode() if body else None,
            headers=headers or {},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read(1_048_576).decode("utf-8", errors="replace")
            return _ok({
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": content,
            })
    except Exception as e:
        return _err(str(e))


# ═══════════════════════════════════════════════════════════════════════════
# SECURITY
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="list_open_files",
    description="List open files/sockets for a process (lsof).",
    parameters={
        "type": "object",
        "properties": {
            "pid": {"type": "integer", "description": "Optional PID; omit for all"},
        },
        "required": [],
    },
    category="security",
)
def list_open_files(pid: Optional[int] = None) -> dict:
    cmd = ["lsof", "-n", "-P"]
    if pid:
        cmd += ["-p", str(pid)]
    r = _run(cmd, timeout=15)
    return _ok(r["stdout"])


@tool(
    name="list_listening_ports",
    description="List all TCP/UDP ports currently listening on the system.",
    parameters={"type": "object", "properties": {}, "required": []},
    category="security",
)
def list_listening_ports() -> dict:
    sys_name = platform.system()
    if sys_name == "Linux":
        r = _run(["ss", "-tlnpu"])
    elif sys_name == "Darwin":
        r = _run(["netstat", "-an", "-p", "tcp"])
    else:
        r = _run(["netstat", "-an"], shell=False)
    return _ok(r["stdout"])


@tool(
    name="check_file_permissions",
    description="Return the permissions and ownership of a file or directory.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    category="security",
)
def check_file_permissions(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return _err(f"Not found: {p}")
    stat = p.stat()
    return _ok({
        "path": str(p),
        "mode": oct(stat.st_mode),
        "uid": stat.st_uid,
        "gid": stat.st_gid,
        "size": stat.st_size,
    })


@tool(
    name="generate_password",
    description="Generate a secure random password.",
    parameters={
        "type": "object",
        "properties": {
            "length": {"type": "integer", "default": 20},
            "include_symbols": {"type": "boolean", "default": True},
        },
        "required": [],
    },
    category="security",
)
def generate_password(length: int = 20, include_symbols: bool = True) -> dict:
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    if include_symbols:
        alphabet += "!@#$%^&*()-_=+[]{}|;:,.<>?"
    password = "".join(secrets.choice(alphabet) for _ in range(length))
    return _ok({"password": password, "length": length})


@tool(
    name="hash_text",
    description="Hash a string using a specified algorithm (md5, sha1, sha256, sha512).",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "algorithm": {"type": "string", "enum": ["md5", "sha1", "sha256", "sha512"],
                          "default": "sha256"},
        },
        "required": ["text"],
    },
    category="security",
)
def hash_text(text: str, algorithm: str = "sha256") -> dict:
    h = hashlib.new(algorithm, text.encode()).hexdigest()
    return _ok({"algorithm": algorithm, "hash": h})


# ═══════════════════════════════════════════════════════════════════════════
# PROCESSES
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="list_processes",
    description="List running processes with CPU and memory usage.",
    parameters={
        "type": "object",
        "properties": {
            "filter_name": {"type": "string", "description": "Optional process name filter"},
            "limit": {"type": "integer", "default": 20},
        },
        "required": [],
    },
    category="process_read",
)
def list_processes(filter_name: str = "", limit: int = 20) -> dict:
    try:
        import psutil
        procs = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = proc.info
                if filter_name and filter_name.lower() not in info["name"].lower():
                    continue
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda p: p.get("cpu_percent") or 0, reverse=True)
        return _ok(procs[:limit])
    except ImportError:
        r = _run(["ps", "aux"])
        lines = r["stdout"].splitlines()
        if filter_name:
            lines = [l for l in lines if filter_name.lower() in l.lower()]
        return _ok("\n".join(lines[:limit + 1]))


@tool(
    name="kill_process",
    description="Kill a process by PID.",
    parameters={
        "type": "object",
        "properties": {
            "pid": {"type": "integer"},
            "signal_name": {"type": "string", "enum": ["TERM", "KILL", "INT"], "default": "TERM"},
        },
        "required": ["pid"],
    },
    category="processes",
    requires_approval=True,
)
def kill_process(pid: int, signal_name: str = "TERM") -> dict:
    sig = {"TERM": signal.SIGTERM, "KILL": signal.SIGKILL, "INT": signal.SIGINT}[signal_name]
    try:
        os.kill(pid, sig)
        return _ok(f"Sent {signal_name} to PID {pid}")
    except ProcessLookupError:
        return _err(f"Process {pid} not found")
    except PermissionError:
        return _err(f"Permission denied for PID {pid}")


@tool(
    name="run_command",
    description="Run a shell command and return stdout/stderr.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "default": 30},
            "working_dir": {"type": "string"},
        },
        "required": ["command"],
    },
    category="processes",
    requires_approval=True,
)
def run_command(command: str, timeout: int = 30, working_dir: Optional[str] = None) -> dict:
    cwd = str(Path(working_dir).expanduser().resolve()) if working_dir else None
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return _ok({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return _err("Command timed out")
    except Exception as e:
        return _err(str(e))


# ═══════════════════════════════════════════════════════════════════════════
# PROGRAMMING
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="run_python",
    description="Execute a Python code snippet and return its output.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["code"],
    },
    category="programming",
    requires_approval=True,
)
def run_python(code: str, timeout: int = 30) -> dict:
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    result: dict[str, Any] = {}

    import contextlib
    try:
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
            compiled = compile(code, "<assistant>", "exec")
            local_ns: dict = {}
            exec(compiled, local_ns)  # noqa: S102
        result["stdout"] = stdout_capture.getvalue()
        result["stderr"] = stderr_capture.getvalue()
        result["status"] = "ok"
    except Exception:
        result["stdout"] = stdout_capture.getvalue()
        result["stderr"] = traceback.format_exc()
        result["status"] = "error"
    return _ok(result)


@tool(
    name="lint_python",
    description="Lint a Python file or code snippet using pyflakes.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source code"},
        },
        "required": ["code"],
    },
    category="programming",
)
def lint_python(code: str) -> dict:
    try:
        import pyflakes.api as pf  # type: ignore
        import pyflakes.reporter as pfr  # type: ignore
        warnings_buf = io.StringIO()
        reporter = pfr.Reporter(warnings_buf, warnings_buf)
        result_count = pf.check(code, "<input>", reporter)
        return _ok({"issues": result_count, "output": warnings_buf.getvalue()})
    except ImportError:
        # Fallback: try ast parse
        try:
            ast.parse(code)
            return _ok({"issues": 0, "output": "Syntax OK (pyflakes not installed)"})
        except SyntaxError as e:
            return _ok({"issues": 1, "output": str(e)})


@tool(
    name="format_python",
    description="Format Python code using black (must be installed).",
    parameters={
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    },
    category="programming",
)
def format_python(code: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tf:
        tf.write(code)
        tmp = tf.name
    try:
        r = _run(["black", "--quiet", tmp])
        if r["returncode"] == 0:
            formatted = Path(tmp).read_text()
            return _ok({"formatted": formatted})
        return _err(r["stderr"])
    finally:
        Path(tmp).unlink(missing_ok=True)


@tool(
    name="create_project_scaffold",
    description="Create a minimal Python project scaffold (pyproject.toml + src layout).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Project name"},
            "directory": {"type": "string", "description": "Parent directory"},
            "description": {"type": "string", "default": ""},
        },
        "required": ["name", "directory"],
    },
    category="programming",
    requires_approval=True,
)
def create_project_scaffold(name: str, directory: str, description: str = "") -> dict:
    base = Path(directory).expanduser().resolve() / name
    pkg = name.replace("-", "_").lower()
    (base / "src" / pkg).mkdir(parents=True, exist_ok=True)
    (base / "tests").mkdir(exist_ok=True)

    (base / "src" / pkg / "__init__.py").write_text(f'"""{description}"""\n')
    (base / "tests" / "__init__.py").write_text("")
    (base / "pyproject.toml").write_text(
        f"""[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
description = "{description}"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""
    )
    (base / "README.md").write_text(f"# {name}\n\n{description}\n")
    return _ok({"project_path": str(base), "package": pkg})


# ═══════════════════════════════════════════════════════════════════════════
# DATABASES
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="sqlite_query",
    description="Run a SQL query against a SQLite database file.",
    parameters={
        "type": "object",
        "properties": {
            "db_path": {"type": "string"},
            "query": {"type": "string"},
            "params": {"type": "array", "items": {}, "description": "Optional bind parameters"},
        },
        "required": ["db_path", "query"],
    },
    category="databases",
    requires_approval=True,
)
def sqlite_query(db_path: str, query: str, params: Optional[list] = None) -> dict:
    p = Path(db_path).expanduser().resolve()
    try:
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, params or [])
        if query.strip().upper().startswith("SELECT"):
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return _ok({"rows": rows, "count": len(rows)})
        conn.commit()
        affected = cur.rowcount
        conn.close()
        return _ok({"affected_rows": affected})
    except Exception as e:
        return _err(str(e))


@tool(
    name="sqlite_export_csv",
    description="Export a SQLite table to a CSV file.",
    parameters={
        "type": "object",
        "properties": {
            "db_path": {"type": "string"},
            "table": {"type": "string"},
            "output_path": {"type": "string"},
        },
        "required": ["db_path", "table", "output_path"],
    },
    category="databases",
    requires_approval=True,
)
def sqlite_export_csv(db_path: str, table: str, output_path: str) -> dict:
    # Validate table name to prevent SQL injection (allow only safe identifiers)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        return _err(f"Invalid table name: {table!r}")
    conn = sqlite3.connect(db_path)
    cur = conn.execute(f"SELECT * FROM {table}")  # noqa: S608 — table name validated above
    rows = cur.fetchall()
    headers = [d[0] for d in cur.description]
    conn.close()
    out = Path(output_path).expanduser().resolve()
    with open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return _ok({"rows_exported": len(rows), "path": str(out)})


# ═══════════════════════════════════════════════════════════════════════════
# CONTAINERS
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="docker_command",
    description="Run a Docker CLI command and return output.",
    parameters={
        "type": "object",
        "properties": {
            "args": {"type": "array", "items": {"type": "string"},
                     "description": "Docker arguments, e.g. ['ps', '-a']"},
        },
        "required": ["args"],
    },
    category="containers",
    requires_approval=True,
)
def docker_command(args: list[str]) -> dict:
    r = _run(["docker"] + args, timeout=60)
    return _ok(r)


@tool(
    name="docker_logs",
    description="Fetch logs for a Docker container.",
    parameters={
        "type": "object",
        "properties": {
            "container": {"type": "string"},
            "tail": {"type": "integer", "default": 100},
        },
        "required": ["container"],
    },
    category="containers",
)
def docker_logs(container: str, tail: int = 100) -> dict:
    r = _run(["docker", "logs", "--tail", str(tail), container], timeout=30)
    return _ok(r["stdout"] or r["stderr"])


# ═══════════════════════════════════════════════════════════════════════════
# CLOUD
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="cloud_cli_status",
    description="Detect installed AWS, Azure, and Google Cloud CLIs and report their versions.",
    parameters={"type": "object", "properties": {}, "required": []},
    category="cloud",
)
def cloud_cli_status() -> dict:
    clients = {
        "aws": ["aws", "--version"],
        "azure": ["az", "--version"],
        "gcloud": ["gcloud", "--version"],
    }
    status: dict[str, dict[str, Any]] = {}
    for name, command in clients.items():
        executable = shutil.which(command[0])
        if not executable:
            status[name] = {"installed": False}
            continue
        result = _run([executable, *command[1:]], timeout=15)
        status[name] = {
            "installed": result["returncode"] == 0,
            "path": executable,
            "version": (result["stdout"] or result["stderr"]).splitlines()[0]
            if result["returncode"] == 0 else "",
        }
    return _ok(status)


# ═══════════════════════════════════════════════════════════════════════════
# VIRTUAL MACHINES
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="list_virtual_machines",
    description="List local virtual machines through libvirt or VirtualBox.",
    parameters={"type": "object", "properties": {}, "required": []},
    category="virt",
)
def list_virtual_machines() -> dict:
    virsh = shutil.which("virsh")
    if virsh:
        result = _run([virsh, "list", "--all"], timeout=20)
        if result["returncode"] == 0:
            return _ok({"provider": "libvirt", "machines": result["stdout"]})
        return _err(result["stderr"] or "Unable to query libvirt")

    virtualbox = shutil.which("VBoxManage")
    if virtualbox:
        result = _run([virtualbox, "list", "vms"], timeout=20)
        if result["returncode"] == 0:
            return _ok({"provider": "virtualbox", "machines": result["stdout"]})
        return _err(result["stderr"] or "Unable to query VirtualBox")

    return _err("Neither libvirt nor VirtualBox is installed")


# ═══════════════════════════════════════════════════════════════════════════
# EMAIL
# ═══════════════════════════════════════════════════════════════════════════

_EMAIL_ADDRESS = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


@tool(
    name="draft_email",
    description="Create a plain-text RFC 5322 email draft without sending it.",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "array", "items": {"type": "string"}},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "sender": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
    category="email",
)
def draft_email(to: list[str], subject: str, body: str, sender: str = "") -> dict:
    if not to or not all(_EMAIL_ADDRESS.fullmatch(address) for address in to):
        return _err("Provide one or more valid recipient email addresses")
    if any("\n" in value or "\r" in value for value in [subject, sender]):
        return _err("Email headers cannot contain line breaks")
    if sender and not _EMAIL_ADDRESS.fullmatch(sender):
        return _err("Provide a valid sender email address")

    headers = [f"To: {', '.join(to)}"]
    if sender:
        headers.append(f"From: {sender}")
    headers.extend([
        f"Subject: {subject}",
        f"Date: {datetime.now().astimezone().strftime('%a, %d %b %Y %H:%M:%S %z')}",
        "MIME-Version: 1.0",
        'Content-Type: text/plain; charset="utf-8"',
    ])
    return _ok({"draft": "\n".join(headers) + "\n\n" + body, "recipients": to})


@tool(
    name="categorize_email",
    description="Categorize an email subject and body using local keyword rules.",
    parameters={
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["subject", "body"],
    },
    category="email",
)
def categorize_email(subject: str, body: str) -> dict:
    text = f"{subject} {body}".lower()
    categories = {
        "security": ("password", "verify", "security alert", "sign-in"),
        "finance": ("invoice", "receipt", "payment", "refund", "billing"),
        "action_required": ("action required", "deadline", "respond", "approval"),
        "newsletter": ("unsubscribe", "newsletter", "weekly digest"),
    }
    for category, keywords in categories.items():
        if matched := next((word for word in keywords if word in text), None):
            return _ok({"category": category, "matched_keyword": matched})
    return _ok({"category": "general", "matched_keyword": None})


# ═══════════════════════════════════════════════════════════════════════════
# MOBILE
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="android_device_info",
    description="List Android devices connected through Android Debug Bridge (adb).",
    parameters={"type": "object", "properties": {}, "required": []},
    category="mobile",
)
def android_device_info() -> dict:
    adb = shutil.which("adb")
    if not adb:
        return _err("Android Debug Bridge (adb) is not installed")
    result = _run([adb, "devices", "-l"], timeout=20)
    if result["returncode"] != 0:
        return _err(result["stderr"] or "Unable to query adb devices")

    devices = []
    for line in result["stdout"].splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split()
        devices.append({
            "serial": parts[0],
            "state": parts[1] if len(parts) > 1 else "unknown",
            "details": " ".join(parts[2:]),
        })
    return _ok({"devices": devices, "count": len(devices)})


# ═══════════════════════════════════════════════════════════════════════════
# SMART HOME
# ═══════════════════════════════════════════════════════════════════════════

def _home_assistant_request(path: str, method: str = "GET", payload: Optional[dict] = None) -> dict:
    base_url = os.environ.get("HOME_ASSISTANT_URL", "").rstrip("/")
    token = os.environ.get("HOME_ASSISTANT_TOKEN", "")
    if not base_url or not token:
        return _err("Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN to use Home Assistant tools")

    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{base_url}/api/{path.lstrip('/')}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return _ok(json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as error:
        return _err(f"Home Assistant returned HTTP {error.code}")
    except urllib.error.URLError as error:
        return _err(f"Unable to reach Home Assistant: {error.reason}")
    except json.JSONDecodeError:
        return _err("Home Assistant returned invalid JSON")


@tool(
    name="home_assistant_states",
    description="Read all Home Assistant states or one entity state. Requires HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN.",
    parameters={
        "type": "object",
        "properties": {"entity_id": {"type": "string"}},
        "required": [],
    },
    category="smarthome",
)
def home_assistant_states(entity_id: str = "") -> dict:
    if entity_id and not re.fullmatch(r"[a-z_]+\.[a-zA-Z0-9_]+", entity_id):
        return _err("Invalid Home Assistant entity ID")
    suffix = f"/{urllib.parse.quote(entity_id, safe='._')}" if entity_id else ""
    return _home_assistant_request(f"states{suffix}")


@tool(
    name="home_assistant_call_service",
    description="Call a Home Assistant service. Requires HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN.",
    parameters={
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "Service domain, e.g. light"},
            "service": {"type": "string", "description": "Service name, e.g. turn_on"},
            "service_data": {"type": "object", "default": {}},
        },
        "required": ["domain", "service"],
    },
    category="smarthome",
    requires_approval=True,
)
def home_assistant_call_service(domain: str, service: str, service_data: Optional[dict] = None) -> dict:
    if not re.fullmatch(r"[a-z_]+", domain) or not re.fullmatch(r"[a-z_]+", service):
        return _err("Invalid Home Assistant service domain or name")
    return _home_assistant_request(
        f"services/{domain}/{service}",
        method="POST",
        payload=service_data or {},
    )


# ═══════════════════════════════════════════════════════════════════════════
# WEB
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="web_fetch",
    description="Fetch a URL and return its text content (HTML or plain text).",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "default": 8000},
        },
        "required": ["url"],
    },
    category="web",
)
def web_fetch(url: str, max_chars: int = 8000) -> dict:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AssistantBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read(max_chars * 4).decode("utf-8", errors="replace")
            # Strip HTML tags for readability
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()
            return _ok({"url": url, "content": text[:max_chars]})
    except Exception as e:
        return _err(str(e))


@tool(
    name="extract_links",
    description="Extract all hyperlinks from an HTML page.",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
    category="web",
)
def extract_links(url: str) -> dict:
    result = web_fetch(url, max_chars=200_000)
    if result["status"] == "error":
        return result
    # Attempt raw fetch for link extraction
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AssistantBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read(500_000).decode("utf-8", errors="replace")
    except Exception as e:
        return _err(str(e))
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    base = "{uri.scheme}://{uri.netloc}".format(uri=urllib.parse.urlparse(url))
    links = []
    for h in hrefs:
        if h.startswith("http"):
            links.append(h)
        elif h.startswith("/"):
            links.append(base + h)
    return _ok({"url": url, "links": list(dict.fromkeys(links))[:100]})


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTIVITY
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="create_task",
    description="Create a new task/to-do item.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "due": {"type": "string", "description": "ISO date or natural language"},
            "priority": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
            "project": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["title"],
    },
    category="productivity",
)
def create_task(
    title: str,
    due: str = "",
    priority: str = "medium",
    project: str = "",
    notes: str = "",
) -> dict:
    task = {
        "id": str(hash(title + str(time.time())))[:8],
        "title": title,
        "due": due,
        "priority": priority,
        "project": project,
        "notes": notes,
        "created": datetime.now().isoformat(),
        "done": False,
    }
    return _ok(task)


@tool(
    name="format_report",
    description="Format a structured data dict or list as a Markdown report.",
    parameters={
        "type": "object",
        "properties": {
            "data": {"description": "Data to format"},
            "title": {"type": "string", "default": "Report"},
        },
        "required": ["data"],
    },
    category="productivity",
)
def format_report(data: Any, title: str = "Report") -> dict:
    lines = [f"# {title}", f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_", ""]
    if isinstance(data, list) and data and isinstance(data[0], dict):
        keys = list(data[0].keys())
        lines.append("| " + " | ".join(keys) + " |")
        lines.append("| " + " | ".join("---" for _ in keys) + " |")
        for row in data:
            lines.append("| " + " | ".join(str(row.get(k, "")) for k in keys) + " |")
    elif isinstance(data, dict):
        for k, v in data.items():
            lines.append(f"- **{k}**: {v}")
    else:
        lines.append(str(data))
    return _ok("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════
# DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="extract_text_from_pdf",
    description="Extract text from a PDF file (requires pypdf).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_pages": {"type": "integer", "default": 50},
        },
        "required": ["path"],
    },
    category="documents",
)
def extract_text_from_pdf(path: str, max_pages: int = 50) -> dict:
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(path)
        pages = reader.pages[:max_pages]
        text = "\n\n".join(p.extract_text() or "" for p in pages)
        return _ok({"pages": len(reader.pages), "text": text})
    except ImportError:
        return _err("pypdf is not installed. Run: pip install pypdf")
    except Exception as e:
        return _err(str(e))


@tool(
    name="convert_document",
    description="Convert a document between formats using pandoc.",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "output": {"type": "string"},
            "from_format": {"type": "string"},
            "to_format": {"type": "string"},
        },
        "required": ["source", "output"],
    },
    category="documents",
    requires_approval=True,
)
def convert_document(
    source: str,
    output: str,
    from_format: str = "",
    to_format: str = "",
) -> dict:
    cmd = ["pandoc", source, "-o", output]
    if from_format:
        cmd += ["-f", from_format]
    if to_format:
        cmd += ["-t", to_format]
    r = _run(cmd, timeout=60)
    if r["returncode"] != 0:
        return _err(r["stderr"])
    return _ok(f"Converted {source} → {output}")


# ═══════════════════════════════════════════════════════════════════════════
# AI / DATA
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="analyze_csv",
    description="Load a CSV file and return basic statistics (row count, column types, sample).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_rows": {"type": "integer", "default": 5},
        },
        "required": ["path"],
    },
    category="ai_data",
)
def analyze_csv(path: str, max_rows: int = 5) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return _err(f"Not found: {p}")
    with open(p, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return _ok({"rows": 0, "columns": 0})
    header = rows[0]
    data = rows[1:]
    return _ok({
        "rows": len(data),
        "columns": len(header),
        "headers": header,
        "sample": data[:max_rows],
    })


@tool(
    name="describe_data",
    description="Describe a list of numbers: mean, median, std-dev, min, max.",
    parameters={
        "type": "object",
        "properties": {
            "numbers": {"type": "array", "items": {"type": "number"}},
        },
        "required": ["numbers"],
    },
    category="ai_data",
)
def describe_data(numbers: list[float]) -> dict:
    if not numbers:
        return _err("Empty list")
    n = len(numbers)
    mean = sum(numbers) / n
    sorted_n = sorted(numbers)
    median = sorted_n[n // 2] if n % 2 else (sorted_n[n // 2 - 1] + sorted_n[n // 2]) / 2
    variance = sum((x - mean) ** 2 for x in numbers) / n
    std = variance ** 0.5
    return _ok({
        "count": n,
        "mean": round(mean, 4),
        "median": round(median, 4),
        "std_dev": round(std, 4),
        "min": min(numbers),
        "max": max(numbers),
        "sum": sum(numbers),
    })


# ═══════════════════════════════════════════════════════════════════════════
# MULTIMEDIA
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="image_info",
    description="Return metadata for an image file (requires Pillow).",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    category="multimedia",
)
def image_info(path: str) -> dict:
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as img:
            return _ok({
                "path": path,
                "format": img.format,
                "mode": img.mode,
                "size": img.size,
                "width": img.size[0],
                "height": img.size[1],
            })
    except ImportError:
        return _err("Pillow is not installed. Run: pip install Pillow")
    except Exception as e:
        return _err(str(e))


@tool(
    name="resize_image",
    description="Resize an image to the specified dimensions (requires Pillow).",
    parameters={
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "output_path": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
        },
        "required": ["input_path", "output_path", "width", "height"],
    },
    category="multimedia",
    requires_approval=True,
)
def resize_image(input_path: str, output_path: str, width: int, height: int) -> dict:
    try:
        from PIL import Image  # type: ignore
        with Image.open(input_path) as img:
            resized = img.resize((width, height))
            resized.save(output_path)
        return _ok({"output": output_path, "size": (width, height)})
    except ImportError:
        return _err("Pillow is not installed")
    except Exception as e:
        return _err(str(e))


# ═══════════════════════════════════════════════════════════════════════════
# FINANCE
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="summarize_expenses",
    description="Summarize a list of expense records by category.",
    parameters={
        "type": "object",
        "properties": {
            "expenses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number"},
                        "category": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
        },
        "required": ["expenses"],
    },
    category="finance",
)
def summarize_expenses(expenses: list[dict]) -> dict:
    totals: dict[str, float] = {}
    for exp in expenses:
        cat = exp.get("category", "uncategorized")
        totals[cat] = totals.get(cat, 0.0) + exp.get("amount", 0.0)
    grand_total = sum(totals.values())
    return _ok({
        "by_category": {k: round(v, 2) for k, v in sorted(totals.items())},
        "total": round(grand_total, 2),
    })


# ═══════════════════════════════════════════════════════════════════════════
# RESEARCH / PKM
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="summarize_text",
    description="Extract the key points from a block of text using heuristics.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "max_sentences": {"type": "integer", "default": 5},
        },
        "required": ["text"],
    },
    category="research",
)
def summarize_text(text: str, max_sentences: int = 5) -> dict:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Simple extractive: keep first N non-trivial sentences
    selected = [s for s in sentences if len(s.split()) > 5][:max_sentences]
    return _ok({"summary": " ".join(selected), "original_sentences": len(sentences)})


@tool(
    name="word_frequency",
    description="Return the most frequent words in a text.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "top_n": {"type": "integer", "default": 20},
        },
        "required": ["text"],
    },
    category="research",
)
def word_frequency(text: str, top_n: int = 20) -> dict:
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    stopwords = {"the", "and", "for", "are", "but", "not", "you", "all",
                 "can", "has", "her", "was", "one", "our", "out", "day",
                 "had", "him", "his", "how", "its", "may", "new", "now",
                 "old", "see", "two", "way", "who", "boy", "did", "man"}
    freq: dict[str, int] = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1
    sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return _ok(dict(sorted_freq))


# ═══════════════════════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="cpu_memory_snapshot",
    description="Return a point-in-time CPU and memory usage snapshot.",
    parameters={"type": "object", "properties": {}, "required": []},
    category="monitoring",
)
def cpu_memory_snapshot() -> dict:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5, percpu=True)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk_parts = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_parts.append({
                    "mount": part.mountpoint,
                    "used_gb": round(usage.used / 1e9, 2),
                    "total_gb": round(usage.total / 1e9, 2),
                    "pct": usage.percent,
                })
            except PermissionError:
                continue
        return _ok({
            "cpu_per_core_pct": cpu,
            "cpu_avg_pct": round(sum(cpu) / len(cpu), 1),
            "memory": {
                "total_gb": round(mem.total / 1e9, 2),
                "used_gb": round(mem.used / 1e9, 2),
                "pct": mem.percent,
            },
            "swap": {"total_gb": round(swap.total / 1e9, 2), "pct": swap.percent},
            "disks": disk_parts,
        })
    except ImportError:
        return system_info()


@tool(
    name="tail_log",
    description="Return the last N lines of a log file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "lines": {"type": "integer", "default": 50},
        },
        "required": ["path"],
    },
    category="monitoring",
)
def tail_log(path: str, lines: int = 50) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return _err(f"Not found: {p}")
    with open(p, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        buf: list[bytes] = []
        remaining = size
        chunk = 4096
        while remaining > 0 and len(buf) < lines:
            read_size = min(chunk, remaining)
            remaining -= read_size
            f.seek(remaining)
            data = f.read(read_size)
            buf.insert(0, data)
        content = b"".join(buf).decode("utf-8", errors="replace")
        result_lines = content.splitlines()[-lines:]
    return _ok("\n".join(result_lines))


# ═══════════════════════════════════════════════════════════════════════════
# AUTOMATION
# ═══════════════════════════════════════════════════════════════════════════

@tool(
    name="watch_file",
    description="Poll a file for changes over a period and return a diff summary.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "duration_seconds": {"type": "integer", "default": 10},
            "interval_seconds": {"type": "number", "default": 1.0},
        },
        "required": ["path"],
    },
    category="automation",
)
def watch_file(path: str, duration_seconds: int = 10, interval_seconds: float = 1.0) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return _err(f"Not found: {p}")
    initial_mtime = p.stat().st_mtime
    initial_size = p.stat().st_size
    changes: list[dict] = []
    end = time.time() + duration_seconds
    while time.time() < end:
        time.sleep(interval_seconds)
        try:
            st = p.stat()
            if st.st_mtime != initial_mtime:
                changes.append({
                    "time": datetime.now().isoformat(),
                    "old_size": initial_size,
                    "new_size": st.st_size,
                })
                initial_mtime = st.st_mtime
                initial_size = st.st_size
        except FileNotFoundError:
            changes.append({"time": datetime.now().isoformat(), "event": "deleted"})
            break
    return _ok({"path": str(p), "changes_detected": len(changes), "changes": changes})


@tool(
    name="schedule_command",
    description="Schedule a one-time shell command via the 'at' utility (Unix).",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "at_time": {"type": "string", "description": "Time string accepted by 'at', e.g. 'now + 5 minutes'"},
        },
        "required": ["command", "at_time"],
    },
    category="automation",
    requires_approval=True,
)
def schedule_command(command: str, at_time: str) -> dict:
    try:
        proc = subprocess.Popen(
            ["at", at_time],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(input=command.encode(), timeout=10)
        return _ok({"stdout": stdout.decode(), "stderr": stderr.decode()})
    except FileNotFoundError:
        return _err("'at' utility not found on this system")
    except Exception as e:
        return _err(str(e))
