"""Plugin loader — discovers and loads Kevin's self-authored tool plugins.

Kevin can create new tools by dropping a .py file into
backend/services/plugins/ that exports:

    TOOL_DEFINITIONS: list   — one or more OpenAI-format tool defs
    execute(tool_name, arguments) -> dict   — handles all tools in that file

After writing a new plugin Kevin can call the built-in `reload_plugins` tool
to make the new tool available immediately, without a server restart.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

PLUGINS_DIR = Path(__file__).parent / "plugins"


def load_plugins() -> Tuple[List[Dict[str, Any]], Dict[str, Callable]]:
    """Scan the plugins directory and import every valid plugin.

    Returns:
        tool_defs   — flat list of OpenAI-format tool definitions
        executors   — mapping of tool_name -> plugin execute() function
    """
    tool_defs: List[Dict[str, Any]] = []
    executors: Dict[str, Callable] = {}

    if not PLUGINS_DIR.exists():
        return tool_defs, executors

    for plugin_file in sorted(PLUGINS_DIR.glob("*.py")):
        # Skip __init__.py and any private helpers
        if plugin_file.name.startswith("_"):
            continue

        module_name = f"backend.services.plugins.{plugin_file.stem}"

        try:
            # Force-reload if already imported (supports reload_plugins at runtime)
            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            defs: List[Dict] = getattr(module, "TOOL_DEFINITIONS", [])
            execute_fn: Callable = getattr(module, "execute", None)

            if not defs:
                print(f"[plugins] {plugin_file.name}: no TOOL_DEFINITIONS, skipping")
                continue
            if execute_fn is None:
                print(f"[plugins] {plugin_file.name}: no execute() function, skipping")
                continue

            loaded = 0
            for tool_def in defs:
                tool_name = tool_def.get("function", {}).get("name")
                if not tool_name:
                    print(f"[plugins] {plugin_file.name}: tool def missing name, skipping entry")
                    continue
                tool_defs.append(tool_def)
                executors[tool_name] = execute_fn
                loaded += 1

            print(f"[plugins] Loaded {loaded} tool(s) from {plugin_file.name}")

        except Exception as e:
            # Bad plugin must not break the server — just log and skip
            print(f"[plugins] ERROR loading {plugin_file.name}: {e}")

    return tool_defs, executors
