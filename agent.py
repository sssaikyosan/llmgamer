import asyncio
import os
import sys
import json
import time
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv

# Local imports
from mcp_manager import MCPManager
from memory_manager import MemoryManager
from llm_client import LLMClient
from utils.vision import capture_screenshot
from prompts import get_system_prompt, get_user_turn_prompt
from agent_state import AgentState

from config import Config

# Configuration
# LLM Provider and Model are now loaded from Config

class GameAgent:
    def __init__(self, initial_task: str = "Play the game"):
        self.mcp_manager = MCPManager()
        self.memory_manager = MemoryManager()
        self.mcp_manager = MCPManager()
        self.memory_manager = MemoryManager()
        self.llm_client = LLMClient(provider=Config.LLM_PROVIDER, model_name=Config.MODEL_NAME)
        self.state = AgentState(max_history=Config.MAX_HISTORY)
        
        # Initialize memory with initial task if provided and empty
        if initial_task:
             self.memory_manager.set_memory("Main Task", initial_task)
        
    async def initialize(self):
        """Initialize the agent and start the meta_manager server."""
        # Attach Memory Manager so MCPManager can route tools to it
        self.mcp_manager.attach_memory_manager(self.memory_manager)

        # Ensure meta_manager exists (virtual, so always True for now in revised logic)
        pass

        # Discover and start all MCP servers in workspace
        workspace_dir = os.path.join(os.getcwd(), "workspace")
        if os.path.exists(workspace_dir):
            for filename in os.listdir(workspace_dir):
                if filename.endswith(".py"):
                    server_name = filename[:-3]
                    success, msg = await self.mcp_manager.start_server(server_name)
                    if success:
                        print(f"Started server: {server_name}")
                    else:
                        print(f"Warning: Failed to start server {server_name}: {msg}")
        
        print("Agent Initialized. All discovered tools are running.")

    async def shutdown(self):
        await self.mcp_manager.shutdown_all()

    async def get_screenshot(self) -> tuple[str, float]:
        return capture_screenshot()

    async def execute_tool(self, server_name: str, tool_name: str, args: Dict[str, Any]):
        print(f"Executing: {server_name}.{tool_name} with {args}")
        try:
            result = await self.mcp_manager.call_tool(server_name, tool_name, args)
            # Handle result content structure properly if it's the specific object or string
            if hasattr(result, 'content') and isinstance(result.content, list) and len(result.content) > 0:
                 output = result.content[0].text
            else:
                 output = str(result)

            print(f"Result: {output[:200]}..." if len(output) > 200 else f"Result: {output}")
            return output
        except Exception as e:
            error_msg = f"Error executing tool: {e}"
            print(error_msg)
            return error_msg

    async def create_new_tool(self, name: str, description: str, code: str):
        print(f"Creating new MCP server: {name}...")
        try:
            await self.mcp_manager.create_server(name, code)
            await self.mcp_manager.start_server(name)
            return f"Successfully created and started server '{name}'."
        except Exception as e:
            return f"Failed to create server '{name}': {e}"

    async def delete_tool(self, name: str):
        print(f"Deleting MCP server: {name}...")
        try:
            await self.mcp_manager.delete_server(name)
            return f"Successfully deleted server '{name}'."
        except Exception as e:
            return f"Failed to delete server '{name}': {e}"

    async def think(self, screenshot_base64: str, timestamp: float) -> Optional[Dict[str, Any]]:
        print("Thinking...")
        
        # Decode screenshot for current turn usage if needed (LLMClient handles it? No, LLMClient expects PIL or list)
        # We need to convert base64 to PIL Image for LLMClient
        import base64
        import io
        from PIL import Image
        
        current_img = None
        if screenshot_base64:
            image_data = base64.b64decode(screenshot_base64)
            current_img = Image.open(io.BytesIO(image_data))

        # Get Contexts
        mem_lines = []
        if self.memory_manager.memories:
            for title, content in self.memory_manager.memories.items():
                mem_lines.append(f"- {title}: {content}")
            memory_str = "\n".join(mem_lines)
        else:
            memory_str = "(No active memories)"

        current_time_str = self.state.get_current_time_str(timestamp)
        
        # Get categorized tools for System Prompt
        tools_cat = self.mcp_manager.get_tools_categorized()
        core_desc = json.dumps(tools_cat["core"], indent=2)
        user_desc = json.dumps(tools_cat["user"], indent=2)
        
        # 1. System Prompt (Dynamic part of system instructions)
        system_prompt = get_system_prompt(core_desc, user_desc, memory_str, max_history=self.state.max_history)
        
        # 2. User Turn Prompt
        user_prompt = get_user_turn_prompt(
            current_time=current_time_str
        )
        
        # Construct Messages for LLM
        # We prepend the system prompt as the first user message
        # Limit history to the last 'max_history' turns (user + assistant = 2 messages per turn)
        history_limit = self.state.max_history * 2
        recent_messages = self.state.messages[-history_limit:] if history_limit > 0 else self.state.messages
        messages_to_send = [{"role": "user", "content": system_prompt}] + recent_messages
        
        # Current input images
        current_inputs = [current_img] if current_img else []

        # Generate Response via LLMClient
        response = await self.llm_client.generate_response(user_prompt, current_inputs, messages=messages_to_send)
        
        if response:
             # Add the User's turn to history (TEXT ONLY)
             self.state.add_message("user", user_prompt)
             
             # Add the Model's response to history
             self.state.add_message("assistant", json.dumps(response))
             
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
            print(f"Failed to save checkpoint: {e}")

    async def load_checkpoint(self, filename: str = "agent_checkpoint.json"):
        """Load agent state from a file in the history directory."""
        history_dir = "history"
        filepath = os.path.join(history_dir, filename)
        
        print(f"Loading checkpoint from {filepath}...")
        try:
            if not os.path.exists(filepath):
                print("Checkpoint file not found.")
                return False

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Restore MemoryManager
            if "memory_manager" in data and isinstance(data["memory_manager"], dict):
                self.memory_manager.memories = data["memory_manager"]
            
            # Restore AgentState
            if "agent_state" in data:
                self.state.from_dict(data["agent_state"])



            print("Checkpoint loaded successfully.")
            return True
        except Exception as e:
            print(f"Failed to load checkpoint: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def run_loop(self, resume: bool = False):
        await self.initialize()
        
        if resume:
            if await self.load_checkpoint():
                print("Resumed from checkpoint.")
            else:
                print("Could not resume. Starting fresh.")
        
        # No screenshot cleanup needed anymore
        
        try:
            while True:
                print("\n--- New Turn ---")
                
                await self.mcp_manager.cleanup_unused_servers()

                screenshot, timestamp = await self.get_screenshot()
                
                decision = await self.think(screenshot, timestamp)
                
                if decision:
                    thought = decision.get("thought")
                    action_type = decision.get("action_type")
                    print(f"Thought: {thought}")
                    
                    # Handle Actions
                    if action_type == "CALL_TOOL":
                        server = decision.get("server_name")
                        tool = decision.get("tool_name")
                        args = decision.get("args", {})
                        
                        # Execute the tool
                        result = await self.execute_tool(server, tool, args)
                        
                        # Add tool result to message history so the model sees it in the next turn
                        self.state.add_message("user", f"Tool '{tool}' executed. Result: {str(result)[:500]}")
                        self.state.add_history(f"Called {tool} (Args: {args}) -> Result: {str(result)[:500]}") # Keep for logging/compatibility if needed
                        
                    else:
                        pass
                        # Removed task update logic
                        
                else:
                    print("No decision made.")
                
                # Save checkpoint after every turn (regardless of decision)
                self.save_checkpoint()
                
                time.sleep(2)

                        
                
        except KeyboardInterrupt:
            print("Stopping agent...")
            self.save_checkpoint() # Save on exit too
        finally:
            await self.shutdown()

if __name__ == "__main__":
    import argparse
    
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

    should_resume = args.resume or (not initial_task and has_checkpoint)

    if not initial_task and not should_resume:
        print("\n=== LLM Gamer Agent ===")
        initial_task = input("Enter the task you want the agent to perform: ").strip()
        if not initial_task:
            initial_task = "Play the game currently on screen."
    
    # If resuming, initial_task arg is ignored during load, but if load fails, it uses it?
    # TaskManager init happens in __init__, so we init with something then overwrite on load.
    
    print(f"\nStarting agent...\n")
    
    agent = GameAgent(initial_task=initial_task if initial_task else "Resume Task")
    asyncio.run(agent.run_loop(resume=should_resume))
