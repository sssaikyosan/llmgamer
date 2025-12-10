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
    """
    Manages both virtual (built-in) MCP servers and user-created workspace MCP servers.
    Virtual Servers:
    - memory_store: For MemorySaver (save operations)
    - tool_factory: For ToolCreator (create/edit/read operations)
    - system_cleaner: For ResourceCleaner (delete/prune operations)
    """
    def __init__(self):
        self.work_dir = os.path.join(os.getcwd(), "workspace")
        self.active_servers: Dict[str, ActiveServer] = {}
        self.python_exe = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

        self.memory_manager_instance = None # To be attached

        # Define Virtual Tools Mapping
        self.VIRTUAL_SERVERS = ["memory_store", "tool_factory", "system_cleaner"]
        
        # Initialize virtual tools definitions
        self.tool_factory_tools = self._init_tool_factory_tools()
        self.system_cleaner_tools = self._init_system_cleaner_tools()
        self.memory_store_tools = self._init_memory_store_tools()

    def attach_memory_manager(self, memory_manager):
        """Attach the agent's MemoryManager instance to expose its tools."""
        self.memory_manager_instance = memory_manager

    def _get_allowed_libraries_str(self) -> str:
        from config import Config
        return ", ".join(Config.ALLOWED_LIBRARIES)

    def _init_memory_store_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "set_memory",
                "description": "Save persistent info (plan, coords, facts). Supports batch updates.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "memories": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "content": {"type": "string"},
                                    "accuracy": {
                                        "type": "integer",
                                        "description": "Confidence score 0-100",
                                        "minimum": 0,
                                        "maximum": 100
                                    }
                                },
                                "required": ["title", "content"]
                            }
                        }
                    },
                    "required": ["memories"]
                }
            }
        ]

    def _init_system_cleaner_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "cleanup_resources",
                "description": "Delete multiple memories and MCP servers at once.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "memory_titles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of memory titles to delete"
                        },
                        "mcp_servers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of MCP server names to delete (without .py)"
                        }
                    }
                }
            }
        ]

    def _init_tool_factory_tools(self) -> List[Dict[str, Any]]:
        libs = self._get_allowed_libraries_str()
        mcp_creation_rules = f"""Create Python MCP server in 'workspace/'. Use 'from fastmcp import FastMCP'. Libs: stdlib + [{libs}]"""
        mcp_edit_rules = f"""Edit MCP server in 'workspace/'. Libs: stdlib + [{libs}]"""

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
                "name": "read_mcp_code",
                "description": "Read MCP source code.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "without .py"}},
                    "required": ["name"]
                }
            }
        ]

    async def create_server(self, name: str, code: str) -> tuple[str, str]:
        """
        Create a new MCP server script file in the workspace directory.
        Returns (filepath, error_message). error_message is empty if no issues.
        """
        import ast
        
        filename = f"{name}.py"
        filepath = os.path.join(self.work_dir, filename)
        
        # Syntax validation
        try:
            ast.parse(code)
        except SyntaxError as e:
            error_msg = f"SYNTAX ERROR in generated code: {e.msg} at line {e.lineno}. Please fix the code."
            logger.error(error_msg)
            return filepath, error_msg
        
        # Check for forbidden patterns
        forbidden_patterns = [
            ("@self.mcp.tool()", "Do NOT use @self.mcp.tool() inside a class. Use @mcp.tool() at module level."),
            ("self.mcp = FastMCP", "Do NOT define mcp inside __init__. Define 'mcp = FastMCP(...)' at module level."),
        ]
        for pattern, message in forbidden_patterns:
            if pattern in code:
                error_msg = f"FORBIDDEN PATTERN DETECTED: {message}"
                logger.error(error_msg)
                return filepath, error_msg
        
        # Basic validation to ensure it imports fastmcp
        if "from fastmcp import FastMCP" not in code:
            logger.warning(f"MCP server '{name}' does not import FastMCP correctly. It may not function.")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
            
        return filepath, ""

    async def _server_lifecycle(self, name: str, params: StdioServerParameters, init_future: asyncio.Future, my_stop_event: asyncio.Event):
        """
        Background task to manage the server lifecycle within proper context scopes.
        my_stop_event is the specific Event for this lifecycle instance, used to check ownership on cleanup.
        """
        logger.debug(f"[{name}] _server_lifecycle starting...")
        try:
            logger.debug(f"[{name}] Entering stdio_client context...")
            async with stdio_client(params) as (read, write):
                logger.debug(f"[{name}] stdio_client context entered, creating ClientSession...")
                async with ClientSession(read, write) as session:
                    logger.debug(f"[{name}] ClientSession created, initializing...")
                    # Initialize
                    await session.initialize()
                    logger.debug(f"[{name}] Session initialized.")
                    
                    # Store session in active server object (it's now ready)
                    if name in self.active_servers:
                         self.active_servers[name].session = session
                    
                    # Get tools to verify and cache
                    tools_result = await session.list_tools()
                    logger.debug(f"[{name}] Got {len(tools_result.tools)} tools.")
                    if name in self.active_servers:
                        self.active_servers[name].tools = tools_result.tools
                        
                    # Signal success
                    if not init_future.done():
                        init_future.set_result(True)
                    
                    logger.info(f"Server {name} connected and running.")
                    
                    # Wait until we are told to stop
                    if name in self.active_servers:
                        logger.debug(f"[{name}] Waiting on stop_event...")
                        await my_stop_event.wait()
                        logger.debug(f"[{name}] stop_event triggered, exiting lifecycle.")
                    else:
                        logger.warning(f"[{name}] Not in active_servers after init, exiting lifecycle early.")
                        
                logger.debug(f"[{name}] Exiting ClientSession context.")
            logger.debug(f"[{name}] Exiting stdio_client context.")
                        
        except Exception as e:
            # Signal failure if it happened during init
            logger.error(f"[{name}] Exception in lifecycle: {e}")
            if not init_future.done():
                init_future.set_exception(e)
            else:
                logger.error(f"Server {name} crashed or disconnected: {e}")
        finally:
            # Cleanup: remove from active servers when lifecycle ends
            # BUT only if this lifecycle still "owns" the server entry (check via stop_event identity)
            logger.debug(f"[{name}] Entering finally block...")
            if name in self.active_servers:
                current_stop_event = getattr(self.active_servers[name], 'stop_event', None)
                if current_stop_event is my_stop_event:
                    logger.debug(f"Server {name} lifecycle ended. Removing from active servers (same instance).")
                    del self.active_servers[name]
                else:
                    logger.debug(f"[{name}] Not removing from active_servers: stop_event mismatch (server was restarted).")
            logger.debug(f"[{name}] _server_lifecycle finished.")

    async def start_server(self, name: str) -> tuple[bool, str]:
        """
        Start an MCP server and connect to it.
        Returns (success, message).
        """
        # Virtual Servers handling
        if name in self.VIRTUAL_SERVERS:
             return True, f"{name} is a virtual server and is always active."

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
        
        # Use the runner script to execute the server
        runner_script = os.path.join(os.getcwd(), "utils", "mcp_runner.py")
        
        server_params = StdioServerParameters(
            command=self.python_exe,
            args=[runner_script, filepath],
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
        self.active_servers[name].stop_event = stop_event

        # Start the background lifecycle task
        asyncio.create_task(self._server_lifecycle(name, server_params, init_future, stop_event))
        
        try:
            # Wait for initialization
            await asyncio.wait_for(init_future, timeout=15.0)
            
            # If we are here, init succeeded
            if name not in self.active_servers:
                raise RuntimeError(f"Server {name} started but terminated immediately.")

            tools = [t.name for t in self.active_servers[name].tools]
            return True, f"Successfully started server {name}. Tools: {tools}"
            
        except Exception as e:
            error_details = traceback.format_exc()
            msg = f"Failed to start server {name}:\nError: {e}\nTraceback:\n{error_details}"
            logger.error(msg)
            if name in self.active_servers:
                del self.active_servers[name]
            return False, msg

    async def stop_server(self, name: str) -> bool:
        """
        Stop an active MCP server.
        """
        if name in self.VIRTUAL_SERVERS:
            return True # Cannot stop virtual server

        if name in self.active_servers:
            server = self.active_servers[name]
            logger.info(f"Stopping server: {name}")
            
            if hasattr(server, 'stop_event'):
                server.stop_event.set()
                
            if name in self.active_servers:
                del self.active_servers[name]
            return True
        return False

    async def delete_server(self, name: str) -> str:
        """
        Stop and delete the server file.
        """
        if name in self.VIRTUAL_SERVERS:
            return "Error: Cannot delete virtual servers."

        await self.stop_server(name)
        
        filepath = os.path.join(self.work_dir, f"{name}.py")
        if os.path.exists(filepath):
            os.remove(filepath)
            msg = f"Deleted server file: {filepath}"
            logger.info(msg)
            return msg
            
        return f"Error: Server file '{name}.py' not found in workspace."

    async def call_tool(self, server_name: str, tool_name: str, args: dict) -> Any:
        # Route to Virtual Servers
        if server_name == "memory_store":
            return await self._call_memory_store_tool(tool_name, args)
        elif server_name == "tool_factory":
            return await self._call_tool_factory_tool(tool_name, args)
        elif server_name == "system_cleaner":
            return await self._call_system_cleaner_tool(tool_name, args)

        if server_name not in self.active_servers:
            raise ValueError(f"Server {server_name} is not active.")
        
        server = self.active_servers[server_name]
        server.last_used = time.time()
        server.usage_count += 1
        
        result = await server.session.call_tool(tool_name, args)
        return result

    async def _call_memory_store_tool(self, tool_name: str, args: dict) -> Any:
        if not self.memory_manager_instance:
             return MockResult(content=[MockTextContent(text="Error: Memory Manager not attached.")])
        output_text = ""
        try:
            if tool_name == "set_memory":
                memories = args.get("memories", [])
                if not memories:
                    # Fallback for single item if LLM messes up/legacy call
                    if "title" in args and "content" in args:
                        memories = [args]
                    else:
                        return MockResult(content=[MockTextContent(text="Error: 'memories' list is required.")])
                
                results = []
                for m in memories:
                    title = m.get("title")
                    content = m.get("content")
                    accuracy = m.get("accuracy", 0) # Default 0 if not set, but agent should set it
                    res = self.memory_manager_instance.set_memory(title, content, accuracy)
                    results.append(res)
                output_text = "\n".join(results)

            else:
                 output_text = f"Error: Unknown memory tool '{tool_name}' on memory_store"
        except Exception as e:
            output_text = f"Error executing memory tool: {e}"
        return MockResult(content=[MockTextContent(text=output_text)])

    async def _call_system_cleaner_tool(self, tool_name: str, args: dict) -> Any:
        output_text = ""
        try:
            if tool_name == "cleanup_resources":
                results = []
                
                # Delete Memories
                mem_titles = args.get("memory_titles", [])
                if mem_titles:
                    if self.memory_manager_instance:
                        for title in mem_titles:
                            res = self.memory_manager_instance.delete_memory(title)
                            results.append(res)
                    else:
                        results.append("Error: Memory Manager not attached.")
                
                # Delete MCP Servers
                mcp_servers = args.get("mcp_servers", [])
                if mcp_servers:
                    for name in mcp_servers:
                        res = await self.delete_server(name)
                        results.append(res)
                
                if not results:
                    output_text = "No actions taken (empty lists provided)."
                else:
                    output_text = "\n".join(results)
            else:
                 output_text = f"Error: Unknown tool '{tool_name}' on system_cleaner"
        except Exception as e:
            output_text = f"Error executing system cleaner tool: {e}"
        return MockResult(content=[MockTextContent(text=output_text)])

    async def _call_tool_factory_tool(self, tool_name: str, args: dict) -> Any:
        output_text = ""
        try:
            if tool_name == "create_mcp_server":
                name = args.get("name")
                code = args.get("code")
                if not name or not code:
                    output_text = "Error: 'name' and 'code' are required."
                else:
                    filepath, validation_error = await self.create_server(name, code)
                    if validation_error:
                        output_text = f"Error creating server '{name}': {validation_error}"
                    else:
                        # Auto start
                        if name in self.active_servers:
                            await self.stop_server(name)
                            await asyncio.sleep(0.5)
                        success, msg = await self.start_server(name)
                        output_text = f"Created and started server '{name}'. {msg}"

            elif tool_name == "edit_mcp_server":
                # Currently same logic as create (overwrite)
                name = args.get("name")
                code = args.get("code")
                if not name or not code:
                    output_text = "Error: 'name' and 'code' are required."
                else:
                    filepath = os.path.join(self.work_dir, f"{name}.py")
                    if not os.path.exists(filepath):
                        output_text = f"Error: Server '{name}' does not exist. Use create_mcp_server."
                    else:
                         filepath, validation_error = await self.create_server(name, code)
                         if validation_error:
                             output_text = f"Error editing server '{name}': {validation_error}"
                         else:
                            if name in self.active_servers:
                                await self.stop_server(name)
                                await asyncio.sleep(0.5)
                            success, msg = await self.start_server(name)
                            output_text = f"Edited and started server '{name}'. {msg}"

            elif tool_name == "read_mcp_code":
                name = args.get("name")
                if not name:
                    output_text = "Error: 'name' argument is required."
                else:
                    filepath = os.path.join(self.work_dir, f"{name}.py")
                    if os.path.exists(filepath):
                        with open(filepath, "r", encoding="utf-8") as f:
                            code = f.read()
                        output_text = f"--- Code for {name}.py ---\n{code}\n---------------------------"
                    else:
                        output_text = f"Error: Server file '{name}.py' not found."
            else:
                output_text = f"Error: Unknown tool '{tool_name}' on tool_factory"
        except Exception as e:
            output_text = f"Error executing tool factory tool: {e}"
        return MockResult(content=[MockTextContent(text=output_text)])

    def list_mcp_files_str(self) -> str:
        output = []
        if os.path.exists(self.work_dir):
            all_files = [f[:-3] for f in os.listdir(self.work_dir) if f.endswith(".py")]
            
            if not all_files:
                return "Workspace servers: (none)"

            output.append("=== WORKSPACE SERVERS ===")
            for name in all_files:
                status = "STOPPED"
                details = ""
                
                # Check if active
                if name in self.active_servers:
                    status = "RUNNING"
                    server = self.active_servers[name]
                    # List tools
                    tool_list = []
                    for t in server.tools:
                        tool_list.append(f"{t.name}: {t.description}")
                    if tool_list:
                        details = "\n    Tools:\n      - " + "\n      - ".join(tool_list)
                    else:
                        details = "\n    Tools: (none)"
                
                output.append(f"* {name} [{status}]{details}")
                
            return "\n".join(output)
        return "Workspace directory not found."

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """
        Return a list of all available tools across all active servers AND virtual servers.
        """
        all_tools = []
        
        # Add Virtual Tools
        def add_virtual_tools(server_name, tools_list):
            for tool in tools_list:
                all_tools.append({
                    "server": server_name,
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["inputSchema"]
                })
        
        add_virtual_tools("tool_factory", self.tool_factory_tools)
        add_virtual_tools("system_cleaner", self.system_cleaner_tools)
        add_virtual_tools("memory_store", self.memory_store_tools)

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
        Return tools separated by Core (Virtual) and User (Workspace).
        """
        core_tools = []
        user_tools = []

        def add_to_core(server_name, tools_list):
            for tool in tools_list:
                core_tools.append({
                    "server": server_name,
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["inputSchema"]
                })

        add_to_core("tool_factory", self.tool_factory_tools)
        add_to_core("system_cleaner", self.system_cleaner_tools)
        add_to_core("memory_store", self.memory_store_tools)

        for server_name, server in self.active_servers.items():
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

    async def cleanup_stopped_files(self) -> List[str]:
        """
        Delete .py files in workspace that are NOT in active_servers.
        Returns list of deleted filenames.
        """
        deleted = []
        if os.path.exists(self.work_dir):
            for filename in os.listdir(self.work_dir):
                if filename.endswith(".py"):
                    name = filename[:-3]
                    # Check if Active
                    if name not in self.active_servers:
                        try:
                            filepath = os.path.join(self.work_dir, filename)
                            if os.path.exists(filepath):
                                os.remove(filepath)
                                deleted.append(name)
                                logger.info(f"Cleaned up stopped server file: {filename}")
                        except Exception as e:
                            logger.error(f"Failed to cleanup file {filename}: {e}")
        return deleted

    def get_active_server_names(self) -> List[str]:
        return list(self.active_servers.keys())
