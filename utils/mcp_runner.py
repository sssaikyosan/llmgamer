import sys
import importlib.util
import os
from fastmcp import FastMCP

def run_mcp_server(file_path):
    # Ensure the directory of the script is in sys.path so relative imports work
    script_dir = os.path.dirname(os.path.abspath(file_path))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    module_name = os.path.basename(file_path).replace('.py', '')
    
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
             print(f"Error: Could not load spec for {file_path}", file=sys.stderr)
             sys.exit(1)
             
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find FastMCP instance
        mcp_instance = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, FastMCP):
                mcp_instance = attr
                break
        
        if mcp_instance:
            # Run the server
            mcp_instance.run()
        else:
            print(f"Error: No FastMCP instance found in {file_path}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error running MCP server runner: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mcp_runner.py <script_path>", file=sys.stderr)
        sys.exit(1)
    
    run_mcp_server(sys.argv[1])
