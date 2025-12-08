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

