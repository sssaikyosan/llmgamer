import asyncio
import os
import sys
import json
import time
import traceback
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
from logger import get_logger

logger = get_logger(__name__)

# Dynamically imported to avoid circular imports usually, but we inject instance
# from memory_manager import MemoryManager 

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
    stop_event: asyncio.Event = None

# Mock classes for virtual tool results (matching MCP SDK structure)
@dataclass
class MockTextContent:
    text: str

@dataclass
class MockResult:
    content: List['MockTextContent']

class MCPManager:
    def __init__(self):
        self.work_dir = os.path.join(os.getcwd(), "workspace")
        self.active_servers: Dict[str, ActiveServer] = {}
        self.python_exe = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

        self.meta_tools = self._init_meta_tools()
        self.memory_manager_instance = None # To be attached
        self.memory_tools = self._init_memory_tools()

    def attach_memory_manager(self, memory_manager):
        """Attach the agent's MemoryManager instance to expose its tools."""
        self.memory_manager_instance = memory_manager

    def _init_memory_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "set_memory",
                "description": "Save persistent info (plan, coords, facts).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["title", "content"]
                }
            },
            {
                "name": "delete_memory",
                "description": "Delete memory by title.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"}
                    },
                    "required": ["title"]
                }
            }
        ]

    def _get_allowed_libraries_str(self) -> str:
        from config import Config
        return ", ".join(Config.ALLOWED_LIBRARIES)

    def _init_meta_tools(self) -> List[Dict[str, Any]]:
        libs = self._get_allowed_libraries_str()
        
        mcp_creation_rules = f"""Create Python MCP server in 'workspace/'. Use FastMCP. Libs: stdlib + [{libs}]"""
        
        mcp_edit_rules = f"""Edit MCP server in 'workspace/' and restart. Libs: stdlib + [{libs}]"""

        return [
            {
                "name": "create_mcp_server",
                "description": mcp_creation_rules,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "without .py"},
                        "code": {"type": "string", "description": "full code"}
                    },
                    "required": ["name", "code"]
                }
            },
            {
                "name": "edit_mcp_server",
                "description": mcp_edit_rules,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "without .py"},
                        "code": {"type": "string", "description": "full code (replaces entire file)"}
                    },
                    "required": ["name", "code"]
                }
            },
            {
                "name": "delete_mcp_server",
                "description": "Delete MCP server.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "without .py"}},
                    "required": ["name"]
                }
            },
            {
                "name": "list_mcp_files",
                "description": "List MCP servers.",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "read_mcp_code",
                "description": "Read MCP source code.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "without .py"}},
                    "required": ["name"]
                }
            }
        ]

    async def create_server(self, name: str, code: str) -> str:
        """
        Create a new MCP server script file in the workspace directory.
        """
        filename = f"{name}.py"
        filepath = os.path.join(self.work_dir, filename)
        
        # Basic validation to ensure it imports mcp
        if "import mcp" not in code and "from mcp" not in code:
            logger.warning(f"MCP server '{name}' does not appear to import mcp. It may not function correctly.")

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
                    
                    logger.info(f"Server {name} connected and running.")
                    
                    # Wait until we are told to stop
                    if name in self.active_servers:
                        await self.active_servers[name].stop_event.wait()
                        
        except Exception as e:
            # Signal failure if it happened during init
            if not init_future.done():
                init_future.set_exception(e)
            else:
                logger.error(f"Server {name} crashed or disconnected: {e}")
        finally:
            # Cleanup: remove from active servers when lifecycle ends
            if name in self.active_servers:
                logger.debug(f"Server {name} lifecycle ended. Removing from active servers.")
                del self.active_servers[name]

    async def start_server(self, name: str) -> tuple[bool, str]:
        """
        Start an MCP server and connect to it.
        Returns (success, message).
        """
        # Virtual Meta Manager handling
        if name == "meta_manager":
            return True, "Meta Manager is a virtual server and is always active."
        if name == "memory_manager":
            return True, "Memory Manager is a virtual server and is always active."

        # Search in workspace only
        filepath = os.path.join(self.work_dir, f"{name}.py")
            
        if not os.path.exists(filepath):
            msg = f"Server script not found: {name}.py (searched in workspace)"
            logger.warning(msg)
            return False, msg

        if name in self.active_servers:
            msg = f"Server {name} is already running."
            logger.debug(msg)
            return True, msg

        logger.info(f"Starting MCP Server: {name}...")
        
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
            script_path=filepath, 
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
            logger.error(msg)
            # Cleanup failed entry
            if name in self.active_servers:
                del self.active_servers[name]
            return False, msg

    async def stop_server(self, name: str) -> bool:
        """
        Stop an active MCP server.
        """
        if name == "meta_manager" or name == "memory_manager":
            return True # Cannot stop virtual server

        if name in self.active_servers:
            server = self.active_servers[name]
            logger.info(f"Stopping server: {name}")
            
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

    async def delete_server(self, name: str) -> str:
        """
        Stop and delete the server file.
        """
        if name == "meta_manager" or name == "memory_manager":
            return "Error: Cannot delete virtual servers."

        await self.stop_server(name)
        
        # Check workspace first
        filepath = os.path.join(self.work_dir, f"{name}.py")
        if os.path.exists(filepath):
            os.remove(filepath)
            msg = f"Deleted server file: {filepath}"
            logger.info(msg)
            return msg
            
        return f"Error: Server file '{name}.py' not found in workspace."

    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        """
        Call a tool on a specific server.
        """
        # Handle Virtual Meta Manager Tools
        if server_name == "meta_manager":
            return await self._call_meta_tool(tool_name, args)
        
        if server_name == "memory_manager":
            return await self._call_memory_tool(tool_name, args)

        if server_name not in self.active_servers:
            raise ValueError(f"Server {server_name} is not active.")
        
        server = self.active_servers[server_name]
        server.last_used = time.time()
        server.usage_count += 1
        
        result = await server.session.call_tool(tool_name, args)
        return result

    async def _call_memory_tool(self, tool_name: str, args: dict) -> Any:
        if not self.memory_manager_instance:
             return MockResult(content=[MockTextContent(text="Error: Memory Manager not attached.")])

        output_text = ""
        try:
            if tool_name == "set_memory":
                output_text = self.memory_manager_instance.set_memory(args.get("title"), args.get("content"))
            elif tool_name == "delete_memory":
                output_text = self.memory_manager_instance.delete_memory(args.get("title"))
            else:
                 output_text = f"Error: Unknown memory tool '{tool_name}'"
        except Exception as e:
            output_text = f"Error executing memory tool: {e}"
        
        return MockResult(content=[MockTextContent(text=output_text)])

    async def _call_meta_tool(self, tool_name: str, args: dict) -> Any:
        """Compatibility wrapper for tool results to match MCP SDK structure."""
        output_text = ""
        
        try:
            if tool_name == "create_mcp_server":
                name = args.get("name")
                code = args.get("code")
                
                # Create file
                await self.create_server(name, code)
                
                # Auto start (delete old if running)
                if name in self.active_servers:
                    await self.stop_server(name)
                    await asyncio.sleep(0.5)
                
                success, msg = await self.start_server(name)
                output_text = f"Created and started server '{name}'. {msg}"

            elif tool_name == "delete_mcp_server":
                name = args.get("name")
                output_text = await self.delete_server(name)

            elif tool_name == "list_mcp_files":
                output = []
                if os.path.exists(self.work_dir):
                    ws_files = [f[:-3] for f in os.listdir(self.work_dir) if f.endswith(".py")]
                    output.append(f"Workspace servers: {', '.join(ws_files) if ws_files else '(none)'}")
                output_text = "\n".join(output)

            
            elif tool_name == "read_mcp_code":
                name = args.get("name")
                filepath = os.path.join(self.work_dir, f"{name}.py")
                
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        code = f.read()
                    output_text = f"--- Code for {name}.py ---\n{code}\n---------------------------"
                else:
                    output_text = f"Error: Server file '{name}.py' not found."

            elif tool_name == "edit_mcp_server":
                name = args.get("name")
                code = args.get("code")
                filepath = os.path.join(self.work_dir, f"{name}.py")
                
                if not os.path.exists(filepath):
                    output_text = f"Error: Server '{name}' does not exist. Use create_mcp_server to create a new one."
                else:
                    # Update file
                    await self.create_server(name, code)
                    
                    # Restart/Start
                    if name in self.active_servers:
                        await self.stop_server(name)
                        await asyncio.sleep(0.5)
                    
                    success, msg = await self.start_server(name)
                    output_text = f"Edited and started server '{name}'. {msg}"

            else:
                output_text = f"Error: Unknown meta tool '{tool_name}'"

        except Exception as e:
            output_text = f"Error executing meta tool {tool_name}: {str(e)}"
            import traceback
            traceback.print_exc()

        return MockResult(content=[MockTextContent(text=output_text)])

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """
        Return a list of all available tools across all active servers AND meta tools.
        """
        all_tools = []
        
        # Add Meta Tools
        for tool in self.meta_tools:
            all_tools.append({
                "server": "meta_manager",
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"]
            })
            
        # Add Memory Tools (if active) - Actually they are always available as "virtual"
        # but the agent needs to attach the manager first. We assume it will.
        if self.memory_manager_instance:
             for tool in self.memory_tools:
                all_tools.append({
                    "server": "memory_manager",
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["inputSchema"]
                })

        # Add Active Server Tools
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
        Return tools separated by Core (Meta Manager, Memory Manager) and User (workspace/*).
        """
        core_tools = []
        user_tools = []

        # Add Meta Tools to Core
        for tool in self.meta_tools:
            core_tools.append({
                "server": "meta_manager",
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"]
            })
            
        # Add Memory Tools to Core
        if self.memory_manager_instance:
             for tool in self.memory_tools:
                core_tools.append({
                    "server": "memory_manager",
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["inputSchema"]
                })

        for server_name, server in self.active_servers.items():
            # All running file-based servers are now considered User tools
            for tool in server.tools:
                tool_dict = {
                    "server": server_name,
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                }
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
                logger.info(f"Server {name} has been idle for {idle_time:.0f}s. Stopping.")
                to_remove.append(name)
        
        for name in to_remove:
            await self.stop_server(name)

    async def shutdown_all(self):
        keys = list(self.active_servers.keys())
        for key in keys:
            await self.stop_server(key)

    def get_active_server_names(self) -> List[str]:
        """Returns a list of currently active server names."""
        return list(self.active_servers.keys())

    def get_tools_compact(self) -> tuple[str, str]:
        """
        ツール情報をコンパクトな文字列で返す。
        Returns (core_tools_str, user_tools_str)
        """
        tools_cat = self.get_tools_categorized()
        
        def format_tools(tools: list) -> str:
            if not tools:
                return "(none)"
            lines = []
            for t in tools:
                props = t.get("inputSchema", {}).get("properties", {})
                # 引数名と説明を含める
                args_parts = []
                for arg_name, arg_info in props.items():
                    desc = arg_info.get("description", "")
                    if desc:
                        args_parts.append(f"{arg_name}:{desc}")
                    else:
                        args_parts.append(arg_name)
                args_str = ", ".join(args_parts) if args_parts else ""
                lines.append(f"- {t['server']}.{t['name']}({args_str}): {t['description']}")
            return "\n".join(lines)
        
        core_str = format_tools(tools_cat["core"])
        user_str = format_tools(tools_cat["user"])
        
        return core_str, user_str
