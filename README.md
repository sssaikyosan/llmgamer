# LLM Gamer Agent (Self-Evolving)

A completely autonomous AI agent that plays games by seeing the screen and operating the mouse/keyboard.
Unlike traditional bots, it **writes its own tools** (MCP Servers) to adapt to any game.

## 🧠 Core Philosophy: Self-Evolution

This agent starts with almost NO specialized game tools. It only has a "Meta Manager" that allows it to:
1.  **Create Tools**: Write Python code to build new capabilities (Screen capture, OCR, Clickers).
2.  **Manage Tools**: Start/Stop/Delete tools as needed to manage context window.
3.  **Inspect Tools**: Read its own source code to improve itself.

The agent uses a dual-directory system for tool management:
*   `servers/`: Core system tools (Meta Manager). Read-only for the agent.
*   `workspace/`: Agent-created tools (Game Interface, Memory, etc.). Fully managed by the agent.

## 🛠️ Pre-Installed Capabilities (The "Body")

While the agent must write the *logic* (The "Mind"), the *body* parts are pre-installed in the environment:
*   **Vision**: `mss` (Ultra-fast screenshot), `opencv-python` (Computer Vision), `pillow`, `pygetwindow`
*   **Action**: `pyautogui` (Mouse/Key), `pydirectinput` (DirectX Games), `keyboard`, `pyperclip`
*   **Brain**: `numpy` (High-speed math/data processing)
*   **System**: `psutil` (Process management)

## 🚀 How to Run

1.  **Install Dependencies** (One-time setup):
    The environment is pre-configured with a curated list of powerful libraries.
    ```bash
    pip install -r requirements.txt
    ```

2.  **Start the Agent**:
    ```bash
    ./run.bat
    ```
    *   Or directly: `python agent.py "Clear Cookie Clicker"`

3.  **Watch it Evolve**:
    *   The agent will wake up, realize it cannot see the screen.
    *   It will check available libraries (`meta_manager.list_installed_packages` or via prompt context).
    *   It will write `workspace/game_interface.py` using `mss` and `pyautogui`.
    *   It will start this new server and begin playing.

## 📂 Project Structure

*   `agent.py`: The main brain loop (LLM interaction, Task Management).
*   `mcp_manager.py`: Handles the lifecycle of MCP servers (Start/Stop/Connect).
*   `servers/`: Contains `meta_manager.py` (The tool to build tools).
*   `workspace/`: **(Empty at start)** The destination for AI-generated tools.
*   `requirements.txt`: The definitive list of installed capabilities.

## 🤖 Supported LLMs
*   **Gemini 2.0 Flash/Pro** (Recommended for speed and vision)
*   **OpenAI GPT-4o**
*   **Local LLMs** (via LM Studio, connecting to `localhost:1234`)

## 🛡️ Safety Features
*   **Sandboxed Creation**: Agent can only delete tools in `workspace/`. Core tools are protected.
*   **No Random Installs**: The agent cannot run `pip install`. It must innovate using the robust pre-installed toolset.
