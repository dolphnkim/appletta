"""Example plugin — copy this file to create a new tool.

Filename becomes the plugin name. Kevin can create as many plugins as he wants;
each one is loaded automatically when the server starts or when `reload_plugins`
is called.

Required exports:
  TOOL_DEFINITIONS  — list of OpenAI-format tool definitions
  execute(tool_name, arguments) -> dict  — called when the tool is invoked

Tips:
  - Return {"error": "..."} to signal failure (Kevin will see this)
  - Return any dict for success
  - One file can contain multiple tools; handle each name in execute()
  - Call `reload_plugins` after creating / editing a plugin to activate it
    without restarting the server
"""

from typing import Any, Dict

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "hello_world",
            "description": (
                "Example tool — returns a greeting. "
                "Delete or replace this file with your own plugin."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Who to greet"
                    }
                },
                "required": ["name"]
            }
        }
    }
]


def execute(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name == "hello_world":
        name = arguments.get("name", "world")
        return {"message": f"Hello, {name}! This tool works."}

    return {"error": f"Unknown tool in example_plugin: {tool_name}"}
