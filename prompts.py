from config import Config

def get_system_instruction() -> str:
    """
    固定のシステム指示（Gemini system_instruction用）。
    API呼び出し時に一度だけ設定される。
    """
    return """Game AI Agent. Screen → Tools.

JSON: {"thought":"...","action_type":"CALL_TOOL"|"WAIT","server_name":"...","tool_name":"...","args":{}}
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
