# Implementation Plan: LLM Gamer Agent

## 1. Core Architecture (Completed)
- [x] **Agent Loop**: `agent.py` implements the See-Think-Act loop.
- [x] **MCP Managers**: `mcp_manager.py` handles StdIO communication with servers.
- [x] **Meta Manager**: `servers/meta_manager.py` allows creating/managing other servers.
- [x] **Task Manager**: Maintains subtasks and context.

## 2. Infrastructure & Safety (Completed)
- [x] **Dual-Dir System**: 
    - `servers/` for immutable core tools.
    - `workspace/` for mutable AI-generated tools.
- [x] **Dependency Locking**:
    - Removed `install_package` capability to prevent environment breakage.
    - Curated a "God Tier" `requirements.txt` with `mss`, `cv2`, `pyautogui`, etc.
    - Hardcoded library availability into the System Prompt.

## 3. Self-Evolving Workflow (Ready to Run)
The agent is designed to follow this boot sequence:
1.  **Boot**: Starts with only `meta_manager`.
2.  **Perception Check**: Tries to see screen -> Fails (No tool).
3.  **Tool Creation**: 
    - Writes `workspace/game_interface.py` using `mss` and `pyautogui`.
    - Function: `take_screenshot`, `click_at`, `press_key`.
4.  **Tool Loading**: Starts the new server.
5.  **Gameplay**: Uses the new body to play the game.

## 4. Future Roadmap
- [ ] **Memory Module**: Agent creates a vector DB or JSON store for long-term strategy.
- [ ] **Skill Library**: Saving successful "Action Sequences" (e.g. "Combo X") as reusable python scripts.
- [ ] **Multi-Agent**: Spawning a separate "Analyst" agent to watch the screen while the "Actor" plays.
