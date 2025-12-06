import asyncio
import os
import sys
import json
import time
import shutil
import traceback
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

@dataclass
class ActiveServer:
    name: str
    script_path: str
    process: Any = None
    session: ClientSession = None
    exit_stack: AsyncExitStack = None
    transport: Any = None
    tools: List[Any] = field(default_factory=list)
    last_used: float = field(default_factory=time.time)
    usage_count: int = 0
    created_at: float = field(default_factory=time.time)

class MCPManager:
    def __init__(self):
        self.core_dir = os.path.join(os.getcwd(), "servers")
        self.work_dir = os.path.join(os.getcwd(), "workspace")
        self.active_servers: Dict[str, ActiveServer] = {}
        self.python_exe = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        
        if not os.path.exists(self.core_dir):
            os.makedirs(self.core_dir)
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

    async def create_server(self, name: str, code: str) -> str:
        """
        Create a new MCP server script file in the workspace directory.
        """
        filename = f"{name}.py"
        filepath = os.path.join(self.work_dir, filename)
        
        # Basic validation to ensure it imports mcp
        if "import mcp" not in code and "from mcp" not in code:
             # Add basic boilerplate if missing (simplified)
             pass 

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
            
        return filepath



    async def _server_lifecycle(self, name: str, params: StdioServerParameters, init_future: asyncio.Future):
        """
        Background task to manage the server lifecycle within proper context scopes.
        """
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize
                    await session.initialize()
                    
                    # Store session in active server object (it's now ready)
                    if name in self.active_servers:
                         self.active_servers[name].session = session
                    
                    # Get tools to verify and cache
                    tools_result = await session.list_tools()
                    if name in self.active_servers:
                        self.active_servers[name].tools = tools_result.tools

                    # Signal success
                    if not init_future.done():
                        init_future.set_result(True)
                    
                    print(f"Server {name} connected and running.")
                    
                    # Wait until we are told to stop
                    if name in self.active_servers:
                        await self.active_servers[name].stop_event.wait()
                        
        except Exception as e:
            # Signal failure if it happened during init
            if not init_future.done():
                init_future.set_exception(e)
            else:
                print(f"Server {name} crashed or disconnected: {e}")
        finally:
            # Cleanup is automatic via context managers
            if name in self.active_servers:
                print(f"Server {name} lifecycle ended.")

    async def start_server(self, name: str) -> (bool, str):
        """
        Start an MCP server and connect to it.
        Returns (success, message).
        """
        # Search in workspace first, then core
        filepath = os.path.join(self.work_dir, f"{name}.py")
        if not os.path.exists(filepath):
            filepath = os.path.join(self.core_dir, f"{name}.py")
            
        if not os.path.exists(filepath):
            msg = f"Server script not found: {name}.py (searched in workspace and servers)"
            print(msg)
            return False, msg

        if name in self.active_servers:
            msg = f"Server {name} is already running."
            print(msg)
            return True, msg

        print(f"Starting MCP Server: {name}...")
        
        server_params = StdioServerParameters(
            command=self.python_exe,
            args=[filepath],
            env=os.environ.copy()
        )
        
        stop_event = asyncio.Event()
        init_future = asyncio.Future()
        
        # Create the ActiveServer entry partial structure (session added later)
        self.active_servers[name] = ActiveServer(
            name=name,
            script_path=filepath, # This filepath is correctly resolved now
            session=None, # injected by loop
            tools=[],     # injected by loop
            process=None, # handled by stdio context
            exit_stack=None, # not used anymore
            transport=None   # handled by context
        )
        # We attach the stop event to the object so we can trigger it later
        # Note: ActiveServer dataclass needs to allow extra fields or we rely on dynamic attr
        self.active_servers[name].stop_event = stop_event

        # Start the background lifecycle task
        asyncio.create_task(self._server_lifecycle(name, server_params, init_future))
        
        try:
            # Wait for initialization
            await asyncio.wait_for(init_future, timeout=5.0)
            
            # If we are here, init succeeded
            tools = [t.name for t in self.active_servers[name].tools]
            return True, f"Successfully started server {name}. Tools: {tools}"
            
        except Exception as e:
            # Capture full traceback to debug TaskGroup/async errors
            error_details = traceback.format_exc()
            msg = f"Failed to start server {name}:\nError: {e}\nTraceback:\n{error_details}"
            print(msg)
            # Cleanup failed entry
            if name in self.active_servers:
                del self.active_servers[name]
            return False, msg

    async def stop_server(self, name: str):
        """
        Stop an active MCP server.
        """
        if name in self.active_servers:
            server = self.active_servers[name]
            print(f"Stopping server: {name}")
            
            # Signal the lifecycle loop to exit
            if hasattr(server, 'stop_event'):
                server.stop_event.set()
                
            # Give it a moment to cleanup (optional)
            # await asyncio.sleep(0.1) 
            
            # Remove from active list
            if name in self.active_servers:
                del self.active_servers[name]
            return True
        return False

    async def delete_server(self, name: str):
        """
        Stop and delete the server file.
        """
        await self.stop_server(name)
        
        # Check workspace first
        filepath = os.path.join(self.work_dir, f"{name}.py")
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"Deleted server file: {filepath}")
            return
            
        # Then check core (optional: maybe prevent deleting core?)
        filepath = os.path.join(self.core_dir, f"{name}.py")
        if os.path.exists(filepath):
            # Safe-guard: Don't delete meta_manager
            if name == "meta_manager":
                print("Cannot delete meta_manager.")
                return
            os.remove(filepath)
            print(f"Deleted server file: {filepath}")

    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        """
        Call a tool on a specific server.
        """
        if server_name not in self.active_servers:
            raise ValueError(f"Server {server_name} is not active.")
        
        server = self.active_servers[server_name]
        server.last_used = time.time()
        server.usage_count += 1
        
        result = await server.session.call_tool(tool_name, args)
        return result

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """
        Return a list of all available tools across all active servers.
        Format suitable for LLM context.
        """
        all_tools = []
        for server_name, server in self.active_servers.items():
            for tool in server.tools:
                all_tools.append({
                    "server": server_name,
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                })
        return all_tools

    def get_tools_categorized(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return tools separated by Core (servers/) and User (workspace/).
        """
        core_tools = []
        user_tools = []

        for server_name, server in self.active_servers.items():
            # Normalize paths to be safe
            server_path = os.path.normpath(server.script_path)
            core_path = os.path.normpath(self.core_dir)
            
            # Check if it starts with the core directory path
            is_core = server_path.startswith(core_path)
            
            for tool in server.tools:
                tool_dict = {
                    "server": server_name,
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                }
                if is_core:
                    core_tools.append(tool_dict)
                else:
                    user_tools.append(tool_dict)
                    
        return {"core": core_tools, "user": user_tools}

    async def cleanup_unused_servers(self, max_idle_seconds: float = 600, min_usage: int = 1):
        """
        Stop and potentially delete servers that haven't been used recently.
        """
        now = time.time()
        to_remove = []
        
        for name, server in self.active_servers.items():
            idle_time = now - server.last_used
            if idle_time > max_idle_seconds:
                print(f"Server {name} has been idle for {idle_time:.0f}s. Stopping.")
                to_remove.append(name)
        
        for name in to_remove:
            await self.stop_server(name)

    async def shutdown_all(self):
        keys = list(self.active_servers.keys())
        for key in keys:
            await self.stop_server(key)
