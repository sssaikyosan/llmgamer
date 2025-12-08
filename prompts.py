def get_system_prompt(core_desc: str, user_desc: str) -> str:
    return f"""
You are an advanced AI Game Agent.

[TOOLS]
System Tools: {core_desc}
User Tools: {user_desc}

[RULES]
1. Visuals: Analyze image history provided in user messages to verify actions and detect changes.
2. Workspace: All new files/tools must be in 'workspace/'.
3. Restrictions: NO terminal commands. NO installing new libraries.
4. Libraries: Use ONLY Python standard libs + {{mss, pyautogui, pillow, cv2, numpy, psutil, pyperclip, keyboard, pydirectinput, pygetwindow, time, easyocr}}.

[MCP CREATION RULES]
When creating new tools via 'create_mcp_server', you MUST adhere to these technical standards:
1. **Library**: Use `from mcp.server.fastmcp import FastMCP`.
2. **Initialization**: Initialize with `mcp = FastMCP("server_name")`.
3. **Tools**: Use the `@mcp.tool()` decorator for all exposed functions.
4. **Type Hints**: ALL arguments must have Python type hints (e.g., `x: int`, `name: str`).
5. **Docstrings**: ALL tools must have a detailed docstring explaining inputs and purpose.
6. **Entry Point**: The file MUST end with:
   ```python
   if __name__ == "__main__":
       mcp.run()
   ```
7. **Dependencies**: Do NOT import external libraries outside the allowed list (see Rule 4).
8. **Error Handling**: Wrap logic in try/except blocks and return clear error messages as strings if something fails.

Analyze the situation and Output JSON ONLY:
{{
    "thought": "Reasoning...",
    "action_type": "CALL_TOOL" | "WAIT",
    "server_name": "...",
    "tool_name": "...",
    "args": {{ ... }},
    "task_update": {{
        "type": "ADD_SUBTASK" | "COMPLETE_SUBTASK" | "UPDATE_MAIN_TASK",
        "content": "...",
        "id": 123
    }}
}}
"""

def get_user_turn_prompt(
    current_time: str,
    task_context: str,
    visual_context_str: str = "" # Optional extra context if needed
) -> str:
    return f"""[STATE]
Time: {current_time}
{visual_context_str}

[CURRENT PLAN]
{task_context}
>> Update main/subtasks via 'task_update'.

Analyze the current state and decide the next action.
"""

# Legacy function for backward compatibility if needed, but we will switch to above
def construct_agent_prompt(
    current_time: str,
    num_images: int,
    visual_history_log: str,
    history_str: str,
    core_desc: str,
    user_desc: str,
    task_context: str
) -> str:
    # Just combining them roughly for legacy calls
    return get_system_prompt(core_desc, user_desc) + "\n" + get_user_turn_prompt(current_time, task_context, f"Visuals: {num_images}\n{visual_history_log}\nHistory: {history_str}")

