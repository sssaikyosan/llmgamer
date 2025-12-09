import asyncio
from datetime import datetime
import os
import sys
import json
import time
import base64
import io
from typing import List, Dict, Any, Optional
from PIL import Image
import shutil

from dotenv import load_dotenv

# Local imports
from mcp_manager import MCPManager
from memory_manager import MemoryManager
from llm_client import LLMClient, LLMError
from utils.vision import capture_screenshot
from prompts import get_system_instruction
from agent_state import AgentState

from config import Config
from logger import get_logger

from dashboard import start_dashboard_thread, update_dashboard_state

logger = get_logger(__name__)

# Configuration
# LLM Provider and Model are now loaded from Config

class GameAgent:
    def __init__(self, initial_task: str = "Play the game"):
        self.mcp_manager = MCPManager()
        self.memory_manager = MemoryManager()
        # Removed duplicate init lines
        self.llm_client = LLMClient(
            provider=Config.LLM_PROVIDER, 
            model_name=Config.get_model_name(),
            system_instruction=get_system_instruction()
        )
        self.state = AgentState(max_history=Config.MAX_HISTORY)
        
        # Initialize ultimate goal
        self.ultimate_goal = initial_task if initial_task else "Awaiting instructions."
        
    async def initialize(self):
        """Initialize the agent and start the meta_manager server."""
        # Attach Memory Manager so MCPManager can route tools to it
        self.mcp_manager.attach_memory_manager(self.memory_manager)

        # Dashboard is now started in __main__ to support initial input

        # Discover and start all MCP servers in workspace
        workspace_dir = os.path.join(os.getcwd(), "workspace")
        if os.path.exists(workspace_dir):
            for filename in os.listdir(workspace_dir):
                if filename.endswith(".py"):
                    server_name = filename[:-3]
                    success, msg = await self.mcp_manager.start_server(server_name)
                    if success:
                        logger.info(f"Started server: {server_name}")
                    else:
                        logger.warning(f"Failed to start server {server_name}: {msg}")
        
        logger.info("Agent Initialized. All discovered tools are running.")
        
        # Set tools for LLM Client (Native Function Calling)
        self._update_llm_tools()
        
        # Initial Dashboard Update
        update_dashboard_state(
            memories=self.memory_manager.memories, 
            tools=self.mcp_manager.get_tools_categorized(),
            mission=self.ultimate_goal 
        )
    
    def _update_llm_tools(self):
        """LLMClientにツール定義を設定する"""
        all_tools = self.mcp_manager.get_all_tools()
        self.llm_client.set_tools(all_tools)

    async def shutdown(self):
        await self.mcp_manager.shutdown_all()

    async def get_screenshot(self) -> tuple[str, float]:
        return capture_screenshot()

    async def execute_tool(self, server_name: str, tool_name: str, args: Dict[str, Any]):
        logger.debug(f"Executing: {server_name}.{tool_name} with {args}")
        output = ""
        try:
            result = await self.mcp_manager.call_tool(server_name, tool_name, args)
            
            # Update Dashboard tools if we modified them (create/delete)
            # A bit inefficient to do it on every tool call, but safe
            if server_name == "meta_manager":
                 update_dashboard_state(tools=self.mcp_manager.get_tools_categorized())
            
            # Handle result content structure properly if it's the specific object or string
            if hasattr(result, 'content') and isinstance(result.content, list) and len(result.content) > 0:
                 output = result.content[0].text
            else:
                 output = str(result)

            logger.debug(f"Result: {output[:200]}..." if len(output) > 200 else f"Result: {output}")
            
        except Exception as e:
            output = f"Error executing tool: {e}"
            logger.error(output)
            
        # Update Dashboard with tool log (timestamped)
        timestamp = datetime.now().strftime("%H:%M:%S")
        update_dashboard_state(tool_log=f"[{timestamp}] Executed {server_name}.{tool_name}\nArgs: {args}\nResult: {output}")

        return output

    async def think(self, screenshot_base64: str, timestamp: float) -> Optional[Dict[str, Any]]:
        logger.debug("Thinking...")
        
        # Decode screenshot for current turn usage - convert base64 to PIL Image
        current_img = None
        if screenshot_base64:
            image_data = base64.b64decode(screenshot_base64)
            current_img = Image.open(io.BytesIO(image_data))
            
            # スクリーンショットを履歴に追加
            current_turn = self.state.add_screenshot(current_img)
            logger.debug(f"Screenshot added to history. Current turn: {current_turn}")

        # Get Contexts
        mem_lines = []
        if self.memory_manager.memories:
            for title, content in self.memory_manager.memories.items():
                mem_lines.append(f"- {title}: {content}")
            memory_str = "\n".join(mem_lines)
        else:
            memory_str = "(No active memories)"

        current_time_str = self.state.get_current_time_str(timestamp)
        
        # Update LLM tools (in case new servers were added)
        self._update_llm_tools()
        
        # Get active MCP servers (user-created, can be edited/deleted)
        active_servers = self.mcp_manager.get_active_server_names()
        if active_servers:
            servers_str = ", ".join(active_servers)
        else:
            servers_str = "(none)"
        
        # スクリーンショット履歴の情報を構築
        screenshot_history = self.state.get_screenshot_history()
        if screenshot_history:
            history_turns = [f"Turn {turn}" for turn, _ in screenshot_history]
            screenshot_info = f"You are viewing {len(screenshot_history)} screenshots: {', '.join(history_turns)} (oldest to newest, current = Turn {screenshot_history[-1][0]})"
        else:
            screenshot_info = "No screenshot history available."
        
        # Context prompt with server info and screenshot history info
        context_prompt = f"""ULTIMATE GOAL: {self.ultimate_goal}

MEMORY:
{memory_str}

ACTIVE MCP SERVERS (can be edited/deleted):
{servers_str}

SCREENSHOT HISTORY:
{screenshot_info}

[{current_time_str}] Analyze the screen and decide the next action."""
        
        # History Prompt
        history_prompt = f"[{current_time_str}] Next action?"
        
        # Get messages for LLM (provider-specific format)
        messages_to_send = self.state.get_messages_for_llm(Config.LLM_PROVIDER)
        
        # 画像入力: 3ターン分のスクリーンショット履歴をラベル付きで渡す
        # 注意: LLMには古い順（左から右）で渡され、プロンプトでどのターンかを説明
        images_to_send = []
        for turn_num, img in screenshot_history:
            images_to_send.append(img)

        # Generate Response via LLMClient
        response = await self.llm_client.generate_response(context_prompt, images_to_send, messages=messages_to_send)
        
        if response:
             # Add user message to history
             self.state.add_user_message(history_prompt)
             
             # Add assistant response (with tool_call if present)
             tool_call = response.get("tool_call")
             thought = response.get("thought", "")
             tool_call_id = self.state.add_assistant_message(thought, tool_call)
             
             # Store tool_call_id in response for later use
             if tool_call_id:
                 response["_tool_call_id"] = tool_call_id
              
        return response

    def save_checkpoint(self, filename: str = "agent_checkpoint.json"):
        """Save the current state of the agent to a file in the history directory."""
        history_dir = "history"
        if not os.path.exists(history_dir):
            os.makedirs(history_dir)
            
        filepath = os.path.join(history_dir, filename)
        # print(f"Saving checkpoint to {filepath}...")
        
        data = {
            "memory_manager": self.memory_manager.memories,
            "agent_state": self.state.to_dict(),
            "timestamp": time.time()
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # print("Checkpoint saved.")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    async def load_checkpoint(self, filename: str = "agent_checkpoint.json"):
        """Load agent state from a file in the history directory."""
        history_dir = "history"
        filepath = os.path.join(history_dir, filename)
        
        logger.info(f"Loading checkpoint from {filepath}...")
        try:
            if not os.path.exists(filepath):
                logger.warning("Checkpoint file not found.")
                return False

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Restore MemoryManager
            if "memory_manager" in data and isinstance(data["memory_manager"], dict):
                self.memory_manager.memories = data["memory_manager"]
            
            # Restore AgentState
            if "agent_state" in data:
                self.state.from_dict(data["agent_state"])




            logger.info("Checkpoint loaded successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def run_loop(self, resume: bool = False):
        await self.initialize()
        
        if resume:
            if await self.load_checkpoint():
                logger.info("Resumed from checkpoint.")
            else:
                logger.warning("Could not resume. Starting fresh.")
        
        # No screenshot cleanup needed anymore
        
        try:
            while True:
                logger.info("--- New Turn ---")
                
                await self.mcp_manager.cleanup_unused_servers()

                screenshot, timestamp = await self.get_screenshot()
                
                # Update Dashboard with new screenshot (keep previous thought until new one arrives)
                update_dashboard_state(screenshot=screenshot)
                
                decision = await self.think(screenshot, timestamp)
                
                if decision:
                    tool = None
                    server = None
                    args = {}
                    thought = decision.get("thought", "No thought")

                    # Native Function Calling format: tool_call object with server/name/arguments
                    if "tool_call" in decision:
                        tool_call = decision["tool_call"]
                        server = tool_call.get("server")
                        tool = tool_call.get("name")
                        args = tool_call.get("arguments", {})
                        
                        # Handle string arguments (OpenAI style)
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                    
                    logger.info(f"Thought: {thought}")
                    
                    # Update Dashboard with thought and memories
                    update_dashboard_state(
                        thought=thought, 
                        memories=self.memory_manager.memories
                    )

                    # Handle Actions
                    if tool:
                        
                        # Execute the tool
                        result = await self.execute_tool(server, tool, args)
                        
                        # Add tool result to history (native function calling format)
                        tool_call_id = decision.get("_tool_call_id", "unknown")
                        full_tool_name = f"{server}.{tool}"
                        self.state.add_tool_result(tool_call_id, full_tool_name, str(result))
                        
                        # Update dashboard again after tool execution (in case memory/tools changed)
                        update_dashboard_state(
                            memories=self.memory_manager.memories,
                            tools=self.mcp_manager.get_tools_categorized()
                        )
                    # WAIT action or other non-tool actions - no processing needed
                else:
                    logger.warning("No decision made.")

                
                # Save checkpoint after every turn (regardless of decision)
                self.save_checkpoint()
                
                await asyncio.sleep(2)

                        
                
        except KeyboardInterrupt:
            logger.info("Stopping agent...")
            self.save_checkpoint() # Save on exit too
        except Exception as e:
            # Catch LLMError and any other unexpected exceptions
            error_msg = f"Agent Error: {e}"
            logger.error(error_msg)
            
            # Show error on dashboard
            update_dashboard_state(error=str(e))
            self.save_checkpoint()
            
            # Keep process alive so dashboard can display the error
            logger.error("Agent stopped due to error. Dashboard is still active. Press Ctrl+C to exit.")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                pass
        finally:
            await self.shutdown()

# Helper function to get input via dashboard (blocking)
def get_user_input_via_dashboard(prompt: str, options: Optional[List[str]] = None) -> str:
    from dashboard import request_user_input, get_submitted_input
    
    logger.debug(f"Waiting for user input via Dashboard: '{prompt}'")
    request_user_input(prompt, options)
    
    while True:
        val = get_submitted_input()
        if val is not None:
            return val
        time.sleep(0.5)

if __name__ == "__main__":
    import argparse
    
    # Start Dashboard Thread EARLY so we can get input
    try:
        start_dashboard_thread()
    except Exception as e:
        logger.error(f"Failed to start dashboard: {e}")

    parser = argparse.ArgumentParser(description="LLM Gamer Agent")
    parser.add_argument("task", nargs="?", help="The initial task for the agent to perform")
    parser.add_argument("--resume", action="store_true", help="Resume from the last checkpoint")
    args = parser.parse_args()
    
    initial_task = args.task
    
    # If resuming, we might not need an initial task, but if one is provided it overrides?
    # Usually resume implies continuing old task.
    # If no task and no resume, ask user.
    # Check if checkpoint exists to decide on auto-resume
    history_dir = "history"
    checkpoint_path = os.path.join(history_dir, "agent_checkpoint.json")
    has_checkpoint = os.path.exists(checkpoint_path)

    should_resume = args.resume

    # If we have history and didn't explicitly ask to resume or start a new task, prompt the user
    if has_checkpoint and not args.resume and not initial_task:
        logger.info("Found existing history.")
        # Ask via Dashboard
        user_choice = get_user_input_via_dashboard(
            "Found existing history. Resume?", 
            options=["Resume", "Start Fresh"]
        )
        
        # Check against button values
        if user_choice and user_choice.lower() in ["resume", "yes", "y", "true", "1"]:
            should_resume = True
        else:
            should_resume = False
            logger.info("User chose to start from scratch. Clearing checkpoint and workspace.")
            try:
                # Clear Checkpoint
                if os.path.exists(checkpoint_path):
                    os.remove(checkpoint_path)
                
                # Clear Workspace
                workspace_dir = "workspace"
                if os.path.exists(workspace_dir):
                    # Delete all files and dirs in workspace, but keep the workspace dir itself
                    for filename in os.listdir(workspace_dir):
                        file_path = os.path.join(workspace_dir, filename)
                        try:
                            if os.path.isfile(file_path) or os.path.islink(file_path):
                                os.unlink(file_path)
                            elif os.path.isdir(file_path):
                                shutil.rmtree(file_path)
                        except Exception as e:
                            logger.error(f'Failed to delete {file_path}. Reason: {e}')
                    logger.info("Workspace cleared.")
            except Exception as e:
                logger.error(f"Failed to clear state: {e}")

    if not initial_task and not should_resume:
        logger.info("=== LLM Gamer Agent ===")
        # Replace CLI input with Dashboard Input
        initial_task = get_user_input_via_dashboard("Enter the task you want the agent to perform:")
        if not initial_task:
            initial_task = "Play the game currently on screen."
    
    # If resuming, initial_task arg is ignored during load, but if load fails, it uses it?
    # TaskManager init happens in __init__, so we init with something then overwrite on load.
    
    logger.info("Starting agent...")
    
    agent = GameAgent(initial_task=initial_task if initial_task else "Resume Task")
    asyncio.run(agent.run_loop(resume=should_resume))
