from mcp.server.fastmcp import FastMCP
import os
import subprocess
import sys

mcp = FastMCP("MetaManager")



@mcp.tool()
def create_mcp_server(name: str, code: str) -> str:
    """
    Create a new MCP server file in the 'workspace' directory.
    
    Args:
        name: Name of the server (without .py extension).
        code: The full Python code for the MCP server.
    """
    try:
        if not os.path.exists("workspace"):
            os.makedirs("workspace")
            
        filepath = os.path.join("workspace", f"{name}.py")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        return f"Successfully created MCP server file at {filepath}"
    except Exception as e:
        return f"Error creating server file: {str(e)}"

@mcp.tool()
def delete_mcp_server(name: str) -> str:
    """
    Delete an existing MCP server file from the 'workspace' directory.
    Cannot delete system servers in 'servers/'.
    
    Args:
        name: Name of the server to delete (without .py extension).
    """
    if name == "meta_manager":
        return "Error: Cannot delete the meta_manager server itself."
    
    try:
        filepath = os.path.join("workspace", f"{name}.py")
        if os.path.exists(filepath):
            os.remove(filepath)
            return f"Successfully deleted MCP server file at {filepath}"
            
        # Check if it's a core server
        core_path = os.path.join("servers", f"{name}.py")
        if os.path.exists(core_path):
             return f"Error: Cannot delete core server '{name}' in 'servers/' directory."
             
        return f"Error: Server file '{name}.py' not found in workspace."
    except Exception as e:
        return f"Error deleting server file: {str(e)}"

@mcp.tool()
def list_mcp_files() -> str:
    """
    List all available MCP server files in 'servers/' (Core) and 'workspace/' (Created).
    Useful to see what tools can be started.
    """
    try:
        output = []
        
        # Core servers
        if os.path.exists("servers"):
            core_files = [f[:-3] for f in os.listdir("servers") if f.endswith(".py")]
            output.append(f"Core servers: {', '.join(core_files)}")
            
        # Workspace servers
        if os.path.exists("workspace"):
            ws_files = [f[:-3] for f in os.listdir("workspace") if f.endswith(".py")]
            if ws_files:
                output.append(f"Workspace servers: {', '.join(ws_files)}")
            else:
                output.append("Workspace servers: (none)")
                
        return "\n".join(output)
    except Exception as e:
        return f"Error listing files: {str(e)}"

@mcp.tool()
def start_mcp_server(name: str) -> str:
    """
    Request to start an existing MCP server to add its tools to the context.
    Checks 'workspace/' then 'servers/'.
    
    Args:
        name: Name of the server to start (without .py extension).
    """
    # Check workspace
    if os.path.exists(os.path.join("workspace", f"{name}.py")):
        return f"Requesting start for server: {name}..."
    # Check servers
    if os.path.exists(os.path.join("servers", f"{name}.py")):
        return f"Requesting start for server: {name}..."
        
    return f"Error: Server file '{name}.py' not found."

@mcp.tool()
def stop_mcp_server(name: str) -> str:
    """
    Request to stop a running MCP server without deleting the file.
    
    Args:
        name: Name of the server to stop (without .py extension).
    """
    if os.path.exists(os.path.join("workspace", f"{name}.py")) or \
       os.path.exists(os.path.join("servers", f"{name}.py")):
        return f"Requesting stop for server: {name}..."
        
    return f"Error: Server file '{name}.py' not found."

@mcp.tool()
def read_mcp_code(name: str) -> str:
    """
    Read the source code of an existing MCP server.
    checks 'workspace/' then 'servers/'.
    
    Args:
        name: Name of the server to read (without .py extension).
    """
    try:
        filepath = os.path.join("workspace", f"{name}.py")
        if not os.path.exists(filepath):
            filepath = os.path.join("servers", f"{name}.py")
            
        if not os.path.exists(filepath):
            return f"Error: Server file '{name}.py' not found."
            
        with open(filepath, "r", encoding="utf-8") as f:
            code = f.read()
            
        return f"--- Code for {name}.py ---\n{code}\n---------------------------"
    except Exception as e:
        return f"Error reading server file: {str(e)}"

if __name__ == "__main__":
    mcp.run()
