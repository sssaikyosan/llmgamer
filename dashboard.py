import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from logger import get_logger

# Get logger for this module
logger = get_logger(__name__)

# Template directory
_TEMPLATE_DIR = Path(__file__).parent / "templates"

# Suppress Uvicorn logs
logging.getLogger("uvicorn").setLevel(logging.WARNING)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared State
class DashboardState:
    def __init__(self):
        self._lock = threading.Lock()
        self.screenshot_base64: Optional[str] = None
        self.thought: str = "Waiting for agent thought process..."
        self.memories: Dict[str, str] = {}
        self.tools: Dict[str, Any] = {}
        self.tool_log: str = "Waiting for tool execution..."
        
        # User Input Handling
        self.waiting_for_input: bool = False
        self.input_prompt: str = ""
        self.last_user_input: Optional[str] = None

state = DashboardState()

def update_dashboard_state(screenshot=None, thought=None, memories=None, tools=None, tool_log=None):
    with state._lock:
        if screenshot:
            state.screenshot_base64 = screenshot
        if thought:
            state.thought = thought
        if memories:
            state.memories = memories
        if tools:
            state.tools = tools
        if tool_log:
            state.tool_log = tool_log

def request_user_input(prompt: str):
    with state._lock:
        state.waiting_for_input = True
        state.input_prompt = prompt
        state.last_user_input = None  # Reset previous input

def get_submitted_input() -> Optional[str]:
    with state._lock:
        if state.last_user_input is not None:
            input_val = state.last_user_input
            # Reset state after reading
            state.waiting_for_input = False
            state.input_prompt = ""
            state.last_user_input = None
            return input_val
        return None

from pydantic import BaseModel
class UserInput(BaseModel):
    text: str

@app.post("/api/submit_input")
async def submit_input(input_data: UserInput):
    with state._lock:
        state.last_user_input = input_data.text
        state.waiting_for_input = False
    return {"status": "ok"}

@app.get("/api/state")
async def get_state():
    with state._lock:
        return {
            "screenshot": state.screenshot_base64,
            "thought": state.thought,
            "memories": state.memories.copy(),  # Copy to avoid race conditions
            "tools": state.tools.copy() if state.tools else {},
            "tool_log": state.tool_log,
            
            # Input State
            "waiting_for_input": state.waiting_for_input,
            "input_prompt": state.input_prompt
        }

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return (_TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")

def start_server():
    # Run uvicorn programmatically
    # Using Config and Server instance to avoid some signal handling issues in threads
    config = uvicorn.Config(app, host="0.0.0.0", port=15000, log_level="error")
    server = uvicorn.Server(config)
    
    # We need to run this in a loop if we were async, but since we are threading a blocking call:
    server.run()

def start_dashboard_thread():
    thread = threading.Thread(target=start_server, daemon=True)
    thread.start()
    logger.info("---------------------------------------------------------")
    logger.info(" >>> DASHBOARD RUNNING AT: http://localhost:15000 <<<")
    logger.info("---------------------------------------------------------")
