import asyncio
import os
import sys
import json
import time
import base64
import datetime
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv

# Local imports
from mcp_manager import MCPManager
from task_manager import TaskManager
from llm_client import LLMClient
from utils.vision import capture_screenshot
from prompts import construct_agent_prompt

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
        self.history = []
        self.screenshot_history = [] # Stores {"time": str, "img": PIL.Image}
        
    async def initialize(self):
        """Initialize the agent and start the meta_manager server."""
        # Ensure meta_manager exists
        if not os.path.exists(os.path.join("servers", "meta_manager.py")):
             pass

        # Start Meta Manager (No longer needed as separate server)
        # self.meta_manager is now virtual inside mcp_manager


        # Start Input Tools (for Basic Interactions)
        if os.path.exists(os.path.join("servers", "input_tools.py")):
             success, msg = await self.mcp_manager.start_server("input_tools")
             if success:
                 print("Input Tools Server started.")
             else:
                 print(f"Warning: Failed to start input_tools: {msg}")
            
        print("Agent Initialized. LLM can now create its own tools.")

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
        
        # Get dynamic task context
        task_context = self.task_manager.get_context_string()
        
        # Format history
        history_str = "\n".join([f"- {h}" for h in self.history[-10:]]) # Last 10 actions
        if not history_str:
            history_str = "(No history yet)"

        # Get categorized tools
        tools_cat = self.mcp_manager.get_tools_categorized()
        core_desc = json.dumps(tools_cat["core"], indent=2)
        user_desc = json.dumps(tools_cat["user"], indent=2)
        
        # Prepare Visual Context
        if timestamp > 0:
            now = datetime.datetime.fromtimestamp(timestamp)
        else:
            now = datetime.datetime.now()
            
        current_timestamp_str = now.strftime("%H:%M:%S")
        current_date_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        inputs = []
        visual_history_log = "(No visual history available)"
        num_images = 0

        if screenshot_base64:
            image_data = base64.b64decode(screenshot_base64)
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_data))
            
            # Update History (Keep last 3) with timestamps
            self.screenshot_history.append({"time": current_timestamp_str, "img": img})
            if len(self.screenshot_history) > 3:
                self.screenshot_history.pop(0)
            
            # Inputs: Extract just the images for Gemini
            inputs = [item["img"] for item in self.screenshot_history]
            num_images = len(inputs)
            
            # Create a log of timestamps for the prompt
            visual_history_log = "\n".join(
                [f"   - Image {i}: Captured at {item['time']} {'(CURRENT)' if i == len(self.screenshot_history)-1 else ''}" 
                 for i, item in enumerate(self.screenshot_history)]
            )
        
        # Construct Prompt
        prompt = construct_agent_prompt(
            current_time=current_date_str,
            num_images=num_images,
            visual_history_log=visual_history_log,
            history_str=history_str,
            core_desc=core_desc,
            user_desc=user_desc,
            task_context=task_context
        )
        
        # Generate Response via LLMClient
        return await self.llm_client.generate_response(prompt, inputs)

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
                        self.history.append(f"Called {tool} (Args: {args}) -> Result: {str(result)[:500]}")
                        


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
