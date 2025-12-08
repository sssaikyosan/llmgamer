from config import Config

def get_system_prompt(core_desc: str, user_desc: str, memory_str: str, max_history: int = 10) -> str:
    return f"""Game AI Agent. Screen → Tools.

TOOLS:
{core_desc}
{user_desc}

MEMORY:
{memory_str}

JSON: {{"thought":"...","action_type":"CALL_TOOL"|"WAIT","server_name":"...","tool_name":"...","args":{{}}}}
"""

def get_user_turn_prompt(current_time: str, visual_context_str: str = "") -> str:
    return f"[{current_time}] Next action?"
