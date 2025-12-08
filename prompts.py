from config import Config

def get_system_instruction() -> str:
    """
    固定のシステム指示（Gemini system_instruction用）。
    API呼び出し時に一度だけ設定される。
    """
    return """Game AI Agent. Screen → Tools.

You can create new tools (MCP servers) to automate tasks.
Rules for creating MCP servers:
1. Use `from fastmcp import FastMCP`.
2. Initialize `mcp = FastMCP("name")`.
3. Use `@mcp.tool()` decorators to expose functions.
4. Only use allowed libraries (see config).

Response JSON Format:
{"thought":"...","action_type":"CALL_TOOL"|"WAIT","server_name":"...","tool_name":"...","args":{}}
"""

def get_context_prompt(tools_str: str, memory_str: str, current_time: str) -> str:
    """
    動的コンテキスト + 現在のターンプロンプト。
    ユーザーメッセージとして毎ターン送信される。
    """
    return f"""TOOLS:
{tools_str}

MEMORY:
{memory_str}

[{current_time}] Next action?"""
