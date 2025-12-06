import asyncio
import os
import sys
import json
import time
import base64
from typing import List, Dict, Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
# You can switch this to 'openai' or 'anthropic' if you implement the adapters.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini") 
API_KEY = os.getenv("API_KEY")

import asyncio
import os
import sys
import json
import time
import base64
import re
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from mcp_manager import MCPManager
from task_manager import TaskManager

# Load environment variables
load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini") 
API_KEY = os.getenv("API_KEY")

class GameAgent:
    def __init__(self, initial_task: str = "Play the game"):
        self.mcp_manager = MCPManager()
        self.task_manager = TaskManager(initial_task)
        self.history = []
        self.screenshot_history = [] # Stores PIL Images of recent screenshots
        
    async def initialize(self):
        """Initialize the agent and start the meta_manager server."""
        # Ensure meta_manager exists
        if not os.path.exists(os.path.join("servers", "meta_manager.py")):
             pass

        # Start Meta Manager
        success, _ = await self.mcp_manager.start_server("meta_manager")
        if not success:
            print("CRITICAL ERROR: Failed to start meta_manager server.")
            sys.exit(1)

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
        try:
            import mss
            import mss.tools
            
            with mss.mss() as sct:
                # Get the primary monitor
                monitor = sct.monitors[1]
                
                # Capture the screen
                sct_img = sct.grab(monitor)
                
                # Convert to PNG
                png_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
                
                # Load as PIL Image for preprocessing
                from PIL import Image, ImageDraw
                import io
                img = Image.open(io.BytesIO(png_bytes))
                
                # Draw Grid Overlay
                draw = ImageDraw.Draw(img)
                width, height = img.size
                grid_size = 100
                
                for x in range(0, width, grid_size):
                    draw.line([(x, 0), (x, height)], fill=(255, 0, 0, 128), width=1)
                for y in range(0, height, grid_size):
                    draw.line([(0, y), (width, y)], fill=(255, 0, 0, 128), width=1)

                # Draw Coordinates Text
                for x in range(0, width, grid_size):
                    for y in range(0, height, grid_size):
                        # Draw coordinate text at intersections
                        text = f"{x},{y}"
                        # Simple shadow for readability
                        draw.text((x+2, y+2), text, fill="black")
                        draw.text((x, y), text, fill="red")

                # Save back to bytes
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
                
                return (img_str, time.time())
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            return ("", 0.0)

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

    def _parse_response(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response handling <think> tags and markdown code blocks."""
        think_match = re.search(r'<think>(.*?)</think>', text, re.DOTALL)
        if think_match:
            thought_content = think_match.group(1).strip()
            print(f"\n=== Model Thought ===\n{thought_content}\n=====================\n")
            text = text.replace(think_match.group(0), "")
        
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except:
                    pass
            print(f"Failed to parse JSON: {text}")
            return None

    async def think(self, screenshot_base64: str, timestamp: float) -> Optional[Dict[str, Any]]:
        print("Thinking...")
        
        if not API_KEY:
            print("WARNING: No API_KEY found.")
            return None



        
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
        
        # Combine for token counting
        tools_desc = core_desc + "\n" + user_desc

        if LLM_PROVIDER == "gemini":
            try:
                import google.generativeai as genai
                genai.configure(api_key=API_KEY)
                # Using Gemini 2.0 Flash Experimental as requested (often referred to as the latest)
                model = genai.GenerativeModel('gemini-3-pro-preview')
                
                import datetime
                
                # Use the passed timestamp for consistent time reference
                if timestamp > 0:
                    now = datetime.datetime.fromtimestamp(timestamp)
                else:
                    now = datetime.datetime.now()
                    
                current_timestamp = now.strftime("%H:%M:%S")

                if screenshot_base64:
                    image_data = base64.b64decode(screenshot_base64)
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(image_data))
                    
                    # Update History (Keep last 3) with timestamps
                    self.screenshot_history.append({"time": current_timestamp, "img": img})
                    if len(self.screenshot_history) > 3:
                        self.screenshot_history.pop(0)
                    
                    # Inputs: Extract just the images for Gemini
                    inputs = [item["img"] for item in self.screenshot_history]
                    
                    # Create a log of timestamps for the prompt
                    visual_history_log = "\n".join(
                        [f"   - Image {i}: Captured at {item['time']} {'(CURRENT)' if i == len(self.screenshot_history)-1 else ''}" 
                         for i, item in enumerate(self.screenshot_history)]
                    )
                else:
                    inputs = []
                    visual_history_log = "(No visual history available)"

                current_time = now.strftime("%Y-%m-%d %H:%M:%S")
                


                prompt = f"""
                You are an advanced AI Game Agent.

                [STATE]
                Time: {current_time}
                Visuals: {len(inputs)} images (Oldest -> Newest).
                {visual_history_log}
                History: {history_str}

                [TOOLS]
                Core (Immutable): {core_desc}
                Custom (Mutable): {user_desc}

                [CURRENT PLAN]
                {task_context}
                >> Update main/subtasks via 'task_update'.

                [RULES]
                1. Visuals: Analyze image history to verify actions and detect changes.
                2. Workspace: All new files/tools must be in 'workspace/'.
                3. Restrictions: NO terminal commands. NO installing new libraries.
                4. Libraries: Use ONLY Python standard libs + {{mss, pyautogui, pillow, cv2, numpy, psutil, pyperclip, keyboard, pydirectinput, pygetwindow, time}}.

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
                
                inputs.insert(0, prompt)
                
                response = model.generate_content(inputs)
                return self._parse_response(response.text)
                
            except Exception as e:
                print(f"LLM Error: {e}")
                return None


        
        return None

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
                        
                        # SPECIAL HANDLING: If the tool was create_mcp_server, automatically start the new server
                        if server == "meta_manager" and tool == "create_mcp_server":
                            new_server_name = args.get("name")
                            if new_server_name:
                                # If server exists and is running, stop it first to allow reload
                                if new_server_name in self.mcp_manager.active_servers:
                                    print(f"Reloading updated server: {new_server_name}...")
                                    await self.mcp_manager.stop_server(new_server_name)
                                    # Give it a tiny moment to ensure file handle release (OS dependent)
                                    await asyncio.sleep(0.5)

                                print(f"Auto-starting new server: {new_server_name}...")
                                success, msg = await self.mcp_manager.start_server(new_server_name)
                                if success:
                                    self.history.append(f"System: Started server {new_server_name}")
                                else:
                                    # Crucial: Feed the error back to the LLM so it can fix the code
                                    self.history.append(f"System: Failed to start server {new_server_name}. Error: {msg}")
                        
                        # SPECIAL HANDLING: If the tool was delete_mcp_server, stop the running server
                        elif server == "meta_manager" and tool == "delete_mcp_server":
                            del_server_name = args.get("name")
                            if del_server_name:
                                print(f"Auto-stopping deleted server: {del_server_name}...")
                                await self.mcp_manager.stop_server(del_server_name)
                                self.history.append(f"System: Stopped server {del_server_name}")

                        # SPECIAL HANDLING: If the tool was start_mcp_server, start the existing server
                        elif server == "meta_manager" and tool == "start_mcp_server":
                            start_server_name = args.get("name")
                            if start_server_name:
                                print(f"Auto-starting existing server: {start_server_name}...")
                                success, msg = await self.mcp_manager.start_server(start_server_name)
                                if success:
                                    self.history.append(f"System: Started server {start_server_name}")
                                else:
                                    self.history.append(f"System: Failed to start server {start_server_name}. Error: {msg}")
                        
                        # SPECIAL HANDLING: stop_mcp_server
                        elif server == "meta_manager" and tool == "stop_mcp_server":
                            stop_server_name = args.get("name")
                            if stop_server_name:
                                print(f"Auto-stopping server: {stop_server_name}...")
                                if await self.mcp_manager.stop_server(stop_server_name):
                                    self.history.append(f"System: Stopped server {stop_server_name}")
                                else:
                                    self.history.append(f"System: Server {stop_server_name} was not running or failed to stop.")

                    elif action_type == "CREATE_SERVER":
                        # Legacy/Direct support (can remove if strictly following new instruction, but harmless to keep as fallback)
                        name = decision.get("server_name")
                        desc = decision.get("description")
                        code = decision.get("code")
                        res = await self.create_new_tool(name, desc, code)
                        print(res)
                        self.history.append(f"Created server {name}")
                        
                    elif action_type == "DELETE_SERVER":
                        name = decision.get("server_name")
                        res = await self.delete_tool(name)
                        print(res)
                        self.history.append(f"Deleted server {name}")
                        
                    elif action_type == "WAIT":
                        print("Waiting...")
                        self.history.append("Waited")
                        
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
