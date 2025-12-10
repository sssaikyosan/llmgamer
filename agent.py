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
from prompts import get_role_instruction, get_context_prompt
from agent_state import AgentState

from config import Config
from logger import get_logger

from dashboard import start_dashboard_thread, update_dashboard_state

logger = get_logger(__name__)

class GameAgent:
    def __init__(self, initial_task: str = "Play the game"):
        self.mcp_manager = MCPManager()
        self.memory_manager = MemoryManager()
        self.llm_client = LLMClient(
            provider=Config.LLM_PROVIDER, 
            model_name=Config.get_model_name()
        )
        self.state = AgentState(max_history=Config.MAX_HISTORY)
        
        # Initialize ultimate goal
        self.ultimate_goal = initial_task if initial_task else "Awaiting instructions."
        
    async def initialize(self):
        """Initialize the agent."""
        # Attach Memory Manager so MCPManager can route tools to it
        self.mcp_manager.attach_memory_manager(self.memory_manager)

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
        
        # Initial Dashboard Update
        update_dashboard_state(
            memories=self.memory_manager.memories, 
            tools=self.mcp_manager.get_tools_categorized(),
            mission=self.ultimate_goal 
        )
    
    async def shutdown(self):
        await self.mcp_manager.shutdown_all()

    async def get_screenshot(self) -> tuple[str, float]:
        return capture_screenshot()

    async def execute_tool(self, server_name: str, tool_name: str, args: Dict[str, Any]):
        logger.debug(f"Executing: {server_name}.{tool_name} with {args}")

        # INTERCEPTION for system tools
        if server_name == "system" and tool_name == "request_tool":
             self.state.variables["active_tool_request"] = args
             return f"Tool Request Received: {args}"

        output = ""
        try:
            result = await self.mcp_manager.call_tool(server_name, tool_name, args)
            
            # Update Dashboard tools if we modified them (create/delete)
            if server_name == "tool_factory" or server_name == "system_cleaner":
                 update_dashboard_state(tools=self.mcp_manager.get_tools_categorized())
            
            # Update Dashboard memories if memory was modified
            if server_name == "memory_store":
                 update_dashboard_state(memories=self.memory_manager.memories)
            
            # Handle result content structure
            if hasattr(result, 'content') and isinstance(result.content, list) and len(result.content) > 0:
                 output = result.content[0].text
            else:
                 output = str(result)

            logger.debug(f"Result: {output[:200]}..." if len(output) > 200 else f"Result: {output}")
            
        except Exception as e:
            output = f"Error executing tool: {e}"
            logger.error(output)
            
        # Update Dashboard with tool log (timestamped) - Args not shown in GUI
        timestamp = datetime.now().strftime("%H:%M:%S")
        update_dashboard_state(tool_log=f"[{timestamp}] Executed {server_name}.{tool_name}\nResult: {output}")

        return output

    async def _execute_phase(self, role: str, screenshot_base64: str, timestamp: float, current_turn: int, goal_override: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Execute a single phase of the pipeline.
        
        Arg: screenshot_base64 is the RAW base64 string for this turn.
        """
        logger.info(f"--- Phase: {role} ---")
        
        memory_str = self.memory_manager.get_memories_string()
        
        # 2. Prepare Tool Context (Filter tools if needed, but for now passing string repr)
        # Note: We need to set the actual tools in LLMClient for Function Calling
        
        # For now, give access to ALL tools to LLMClient, but prompt instructs what to use.
        # Ideally we should filter `self.llm_client.set_tools` here.
        all_tools = self.mcp_manager.get_all_tools()
        
        # Filter Tools for LLM Client to enforce role boundaries
        filtered_tools = []
        for tool in all_tools:
            server = tool['server']
            # Security Policies
            if role == "MemorySaver":
                 if server == "memory_store": filtered_tools.append(tool)
            elif role == "ToolCreator":
                 if server == "tool_factory": filtered_tools.append(tool)
            elif role == "ResourceCleaner":
                 if server == "system_cleaner": filtered_tools.append(tool)
            elif role == "Operator":
                 # Operator can access all User servers (not Virtual ones)
                 if server not in ["memory_store", "tool_factory", "system_cleaner"]: filtered_tools.append(tool)
        
        # Inject System Tools for Operator
        if role == "Operator":
             filtered_tools.append({
                 "server": "system",
                 "name": "request_tool",
                 "description": "Request the creation of a new tool from the Tool Creator.",
                 "inputSchema": {
                     "type": "object",
                     "properties": {
                         "name": {"type": "string", "description": "Suggested name for the tool"},
                         "description": {"type": "string", "description": "Detailed description of what the tool should do"},
                         "reason": {"type": "string", "description": "Why this tool is needed"}
                     },
                     "required": ["name", "description", "reason"]
                 }
             })
        
        self.llm_client.set_tools(filtered_tools)
        
        # Log available tools for debugging
        if role == "Operator":
            if not filtered_tools:
                logger.warning("[Operator] No tools available! Check if workspace MCP servers are running.")
                all_tools_list = [t["server"] + "." + t["name"] for t in all_tools]
                logger.warning(f"[Operator] All available tools: {all_tools_list}")
            else:
                avail_list = [t["server"] + "." + t["name"] for t in filtered_tools]
                logger.info(f"[Operator] Available tools: {avail_list}")
        # Tools string for Prompt
        tools_str = ", ".join([f"{t['server']}.{t['name']}" for t in filtered_tools]) if filtered_tools else "(none)"
        
        # 3. Prepare Prompt
        current_time_str = self.state.get_current_time_str(timestamp)
        
        # Inject Last Action for MemorySaver
        if role == "MemorySaver":
            last_action_desc = self.state.variables.get("last_action", "None (First Turn or No Action)")
            memory_str = f"PREVIOUS ACTION: {last_action_desc}\n\n" + memory_str

        # Inject Tool Request for ToolCreator
        if role == "ToolCreator":
            req = goal_override if goal_override else self.state.variables.get("active_tool_request", "None")
            mcp_list = self.mcp_manager.list_mcp_files_str()
            memory_str = f"URGENT REQUEST FROM OPERATOR: {req}\n\nExisting MCP Tools:\n{mcp_list}\n\n" + memory_str

        # Inject MCP List for ResourceCleaner
        if role == "ResourceCleaner":
            mcp_list = self.mcp_manager.list_mcp_files_str()
            memory_str = f"CURRENT MCP SERVERS:\n{mcp_list}\n\n" + memory_str

        context_prompt = get_context_prompt(
            mission=self.ultimate_goal,
            tools_str=tools_str,
            memory_str=memory_str,
            current_time=current_time_str,
            role=role
        )
        
        # 4. Prepare Images (History)
        screenshot_history = self.state.get_screenshot_history()
        # Decode current if needed, but get_screenshot_history returns PIL Images
        images_to_send = [img for _, img in screenshot_history]
        
        # 5. Get System Instruction
        system_instruction = get_role_instruction(role)
        
        # 6. Set Loop Parameters
        max_steps = 1
        if role == "ToolCreator":
            max_steps = 5
        
        # Short-term history for this phase
        phase_messages = [] 
        
        # The prompt for the first step is the context.
        # For subsequent steps (after tool execution), the prompt will be the tool result.
        current_prompt = context_prompt

        # Loop for multi-step reasoning (ReAct loop within phase)
        for step in range(max_steps):
            if step > 0:
                logger.info(f"[{role}] Step {step+1}/{max_steps}")

            # Call LLM
            # We pass phase_messages to maintain context within this loop
            update_dashboard_state(thought=f"[{role}] Thinking (Step {step+1})...")
            
            # Prepare messages for this step
            # - Step 0: Include role_history for long-term context
            # - Step 1+: Only use phase_messages (short-term history) to ensure
            #            Gemini API constraints are satisfied (function_call must be
            #            followed by function_response within the same history)
            messages_to_send = []
            
            if step == 0:
                # First step: include long-term history for context
                use_global = (role == "MemorySaver")
                role_history = self.state.get_messages_for_llm(role_filter=role, use_global=use_global)
                messages_to_send = role_history
            else:
                # Subsequent steps: only use phase_messages to maintain proper call structure
                messages_to_send = phase_messages

            try:
                response = await self.llm_client.generate_response(
                    prompt=current_prompt, 
                    images=images_to_send, 
                    messages=messages_to_send, 
                    system_instruction=system_instruction
                )
            except Exception as e:
                logger.error(f"LLM Error in {role} step {step+1}: {e}")
                break

            # 7. Process Response
            if response:
                thought = response.get("thought", "")
                tool_call = response.get("tool_call")
                
                # Log thought
                logger.info(f"[{role}] Thought: {thought}")
                update_dashboard_state(thought=f"[{role}] {thought}")
                
                # Record to Main History (for long-term logging)
                tool_call_id = self.state.add_assistant_message(thought, tool_call, agent_role=role)
                
                # If no tool call, we are done with this phase
                if not tool_call:
                    if role == "Operator":
                         self.state.variables["last_action"] = "Waited (No Action)"
                    break

                # --- Handle Tool Call and Update Phase History for Next Step ---
                
                # 1. Add the model's response to phase_messages
                #    (A) If this is step 0, we need to also add the initial user prompt first
                if step == 0:
                    # Initial user prompt
                    phase_messages.append({"role": "user", "parts": [context_prompt]})
                
                # (B) Add model's response (with function call)
                # Construct proper Gemini function_call part structure
                fc_part = {
                    "function_call": {
                        "name": f"{tool_call['server']}__{tool_call['name']}",
                        "args": tool_call['arguments']
                    }
                }
                model_parts = []
                if thought:
                    model_parts.append(thought)
                model_parts.append(fc_part)
                phase_messages.append({"role": "model", "parts": model_parts})

                # 2. Execute Tool
                server = tool_call.get("server")
                name = tool_call.get("name")
                args = tool_call.get("arguments", {})
                
                # Sanitize args
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                
                # Execute
                result_str = await self.execute_tool(server, name, args)
                
                # Record Tool Result to Main History
                if tool_call_id:
                     self.state.add_tool_result(tool_call_id, f"{server}.{name}", result_str, agent_role=role)
                
                # 3. Add function response to phase_messages (must come right after function_call)
                #    In Gemini, function_response is a 'user' turn with a special part structure
                fr_part = {
                    "function_response": {
                        "name": f"{server}__{name}",
                        "response": {"result": result_str}
                    }
                }
                phase_messages.append({"role": "user", "parts": [fr_part]})
                
                # 4. Prepare NEXT prompt (for subsequent steps, the prompt is a continuation message)
                #    Since we already added function_response to phase_messages, we just need a simple prompt
                current_prompt = "Continue based on the function response above. Decide if you need to take another action or if you're done."
                
                # If Operator, save as Last Action
                if role == "Operator":
                    self.state.variables["last_action"] = f"Executed {server}.{name} with {args}"
                    logger.info(f"Recorded Last Action: {self.state.variables['last_action']}")
            else:
                break # No response

        return None # We handled everything in the loop

    def save_checkpoint(self, filename: str = "agent_checkpoint.json"):
        """Save the current state of the agent to a file in the history directory."""
        history_dir = "history"
        if not os.path.exists(history_dir):
            os.makedirs(history_dir)
            
        filepath = os.path.join(history_dir, filename)
        
        data = {
            "memory_manager": self.memory_manager.memories, # Now a dict of objects
            "agent_state": self.state.to_dict(), # We allow state saving even if we don't use history for prompting
            "ultimate_goal": self.ultimate_goal,
            "timestamp": time.time()
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
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
                # Handle migration from old format {key: {content, category}} to new {key: content}
                memories = data["memory_manager"]
                new_memories = {}
                for k, v in memories.items():
                    if isinstance(v, dict) and "content" in v:
                         new_memories[k] = v["content"]
                    else:
                         new_memories[k] = v
                self.memory_manager.memories = new_memories
            
            # Restore AgentState
            if "agent_state" in data:
                self.state.from_dict(data["agent_state"])
                
            if "ultimate_goal" in data:
                self.ultimate_goal = data["ultimate_goal"]

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
        
        try:
            while True:
                logger.info("=== New Turn ===")
                
                # Sensing Phase (Shared)
                screenshot_base64, timestamp = await self.get_screenshot()
                
                # Update Dashboard
                update_dashboard_state(screenshot=screenshot_base64)
                
                # Add to History (Centralized)
                image_data = base64.b64decode(screenshot_base64)
                current_img = Image.open(io.BytesIO(image_data))
                current_turn = self.state.add_screenshot(current_img)
                
                # Phase 1: Memory Saver
                await self._execute_phase("MemorySaver", screenshot_base64, timestamp, current_turn)
                
                # Phase 2: Resource Cleaner
                await self._execute_phase("ResourceCleaner", screenshot_base64, timestamp, current_turn)
                
                # Phase 3: Operator
                await self._execute_phase("Operator", screenshot_base64, timestamp, current_turn)

                # Phase 4: Tool Creator (Conditional)
                if "active_tool_request" in self.state.variables and self.state.variables["active_tool_request"]:
                    logger.info("Handling Tool Request...")
                    await self._execute_phase("ToolCreator", screenshot_base64, timestamp, current_turn)
                    
                    # Auto-cleanup: Remove failed/stopped server files
                    cleaned = await self.mcp_manager.cleanup_stopped_files()
                    if cleaned:
                        logger.info(f"Auto-cleaned failed tool files: {cleaned}")

                    # Clear request after attempts
                    if "active_tool_request" in self.state.variables:
                        del self.state.variables["active_tool_request"]
                
                # Save Checkpoint
                self.save_checkpoint()
                
                # Update Dashboard memories finally
                update_dashboard_state(memories=self.memory_manager.memories)
                
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Stopping agent...")
            self.save_checkpoint() 
        except Exception as e:
            error_msg = f"Agent Error: {e}"
            logger.error(error_msg)
            import traceback
            traceback.print_exc()
            
            update_dashboard_state(error=str(e))
            self.save_checkpoint()
            
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
    
    # Start Dashboard Thread EARLY
    try:
        start_dashboard_thread()
    except Exception as e:
        logger.error(f"Failed to start dashboard: {e}")

    parser = argparse.ArgumentParser(description="LLM Gamer Agent")
    parser.add_argument("task", nargs="?", help="The initial task for the agent to perform")
    parser.add_argument("--resume", action="store_true", help="Resume from the last checkpoint")
    args = parser.parse_args()
    
    initial_task = args.task
    
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
        
        if user_choice and user_choice.lower() in ["resume", "yes", "y", "true", "1"]:
            should_resume = True
        else:
            should_resume = False
            logger.info("User chose to start from scratch. Clearing checkpoint and workspace.")
            try:
                if os.path.exists(checkpoint_path):
                    os.remove(checkpoint_path)
                
                workspace_dir = "workspace"
                if os.path.exists(workspace_dir):
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
        initial_task = get_user_input_via_dashboard("Enter the task you want the agent to perform:")
        if not initial_task:
            initial_task = "Play the game currently on screen."
    
    logger.info("Starting agent...")
    
    agent = GameAgent(initial_task=initial_task if initial_task else "Resume Task")
    asyncio.run(agent.run_loop(resume=should_resume))
