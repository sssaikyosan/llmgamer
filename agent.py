import asyncio
import os
import sys
import json
import time
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv

# Local imports
from mcp_manager import MCPManager
from task_manager import TaskManager
from llm_client import LLMClient
from utils.vision import capture_screenshot
from prompts import get_system_prompt, get_user_turn_prompt
from agent_state import AgentState

# Load environment variables
load_dotenv()

# Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini") 
# Model name can be adjusted here or passed to LLMClient
if LLM_PROVIDER == "gemini":
    MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
elif LLM_PROVIDER == "lmstudio":
    MODEL_NAME = os.getenv("LM_STUDIO_MODEL", "local-model")
else:
    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3-pro-preview") 

class GameAgent:
    def __init__(self, initial_task: str = "Play the game"):
        self.mcp_manager = MCPManager()
        self.task_manager = TaskManager(initial_task)
        self.llm_client = LLMClient(provider=LLM_PROVIDER, model_name=MODEL_NAME)
        self.state = AgentState()
        
    async def initialize(self):
        """Initialize the agent and start the meta_manager server."""
        # Ensure meta_manager exists (virtual, so always True for now in revised logic)
        pass

        # Start Input Tools (for Basic Interactions) - Check workspace
        if os.path.exists(os.path.join("workspace", "input_tools.py")):
             success, msg = await self.mcp_manager.start_server("input_tools")
             if success:
                 print("Input Tools Server started.")
             else:
                 print(f"Warning: Failed to start input_tools from workspace: {msg}")
            
        print("Agent Initialized. LLM can now create its own tools in workspace.")

    async def shutdown(self):
        await self.mcp_manager.shutdown_all()

    async def get_screenshot(self) -> tuple[str, float]:
        return capture_screenshot()

    async def execute_tool(self, server_name: str, tool_name: str, args: Dict[str, Any]):
        print(f"Executing: {server_name}.{tool_name} with {args}")
        try:
            result = await self.mcp_manager.call_tool(server_name, tool_name, args)
            output = result.content[0].text
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
        
        # Update State with new screenshot
        current_img = self.state.add_screenshot(screenshot_base64, timestamp)

        # Get Contexts
        task_context = self.task_manager.get_context_string()
        current_time_str = self.state.get_current_time_str(timestamp)
        
        # Get categorized tools for System Prompt
        tools_cat = self.mcp_manager.get_tools_categorized()
        core_desc = json.dumps(tools_cat["core"], indent=2)
        user_desc = json.dumps(tools_cat["user"], indent=2)
        
        # 1. System Prompt (Dynamic part of system instructions)
        system_prompt = get_system_prompt(core_desc, user_desc)
        
        # 2. User Turn Prompt
        user_prompt = get_user_turn_prompt(
            current_time=current_time_str,
            task_context=task_context
        )
        
        # Construct Messages for LLM
        # We prepend the system prompt as the first user message (or system message if supported)
        # to ensure the LLM knows the current tools and rules.
        messages_to_send = [{"role": "user", "content": system_prompt}] + self.state.messages
        
        # Current input images (only the latest one is strictly needed if history has them, 
        # but let's pass the current one explicitly with the prompt)
        current_inputs = [current_img] if current_img else []

        # Generate Response via LLMClient
        response = await self.llm_client.generate_response(user_prompt, current_inputs, messages=messages_to_send)
        
        if response:
             # Add the User's turn to history (so it's available for next turn)
             # Note: We store the 'user_prompt' and 'current_img' 
             self.state.add_message("user", [user_prompt, current_img] if current_img else user_prompt)
             
             # Add the Model's response to history
             # We store the raw response dict or a summary? 
             # Storing the JSON string representation is safer for reproduction
             self.state.add_message("assistant", json.dumps(response))
             
        return response

    async def run_loop(self):
        await self.initialize()
        
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
                    
                    # Handle Task Updates
                    task_update = decision.get("task_update")
                    if task_update:
                        update_type = task_update.get("type")
                        content = task_update.get("content")
                        t_id = task_update.get("id")
                        
                        if update_type == "ADD_SUBTASK" and content:
                            msg = self.task_manager.add_subtask(content)
                            print(f"[Task Manager] {msg}")
                        elif update_type == "COMPLETE_SUBTASK" and t_id:
                            msg = self.task_manager.complete_subtask(t_id)
                            print(f"[Task Manager] {msg}")
                        elif update_type == "UPDATE_MAIN_TASK" and content:
                            msg = self.task_manager.update_main_task(content)
                            print(f"[Task Manager] {msg}")

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
                        print(f"Unknown action type: {action_type}")
                else:
                    print("No decision made.")
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("Stopping agent...")
        finally:
            await self.shutdown()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Gamer Agent")
    parser.add_argument("task", nargs="?", help="The initial task for the agent to perform")
    args = parser.parse_args()
    
    initial_task = args.task
    if not initial_task:
        print("\n=== LLM Gamer Agent ===")
        initial_task = input("Enter the task you want the agent to perform: ").strip()
        if not initial_task:
            initial_task = "Play the game currently on screen."
    
    print(f"\nStarting agent with task: {initial_task}\n")
    
    agent = GameAgent(initial_task=initial_task)
    asyncio.run(agent.run_loop())
