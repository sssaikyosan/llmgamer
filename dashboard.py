import logging
import threading
from typing import Dict, Any, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Suppress Uvicorn logs
logging.getLogger("uvicorn").setLevel(logging.WARNING)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared State
class DashboardState:
    def __init__(self):
        self.screenshot_base64: Optional[str] = None
        self.thought: str = "Waiting for agent thought process..."
        self.memories: Dict[str, str] = {}
        self.tools: Dict[str, Any] = {}
        self.logs: list = []

state = DashboardState()

def update_dashboard_state(screenshot=None, thought=None, memories=None, tools=None):
    if screenshot:
        state.screenshot_base64 = screenshot
    if thought:
        state.thought = thought
    if memories:
        state.memories = memories
    if tools:
        state.tools = tools

@app.get("/api/state")
async def get_state():
    return {
        "screenshot": state.screenshot_base64,
        "thought": state.thought,
        "memories": state.memories,
        "tools": state.tools
    }

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Gamer Agent Brain</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #09090b;
            --panel-bg: #18181b;
            --text-color: #e4e4e7;
            --accent-color: #3b82f6; /* Blue-500 */
            --border-color: #27272a;
            --thought-color: #10b981; /* Emerald-500 */
            --header-text: #a1a1aa;
        }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
            display: grid;
            grid-template-columns: 2fr 1fr;
            grid-template-rows: auto 1fr;
            gap: 20px;
            height: 95vh;
            overflow: hidden;
        }
        .panel {
            background-color: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }
        h2 {
            margin-top: 0;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 15px;
            margin-bottom: 15px;
            font-size: 1rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--header-text);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        h2::before {
            content: '';
            display: inline-block;
            width: 8px;
            height: 8px;
            background-color: var(--accent-color);
            border-radius: 50%;
        }
        
        /* Screen Panel */
        #screen-panel {
            grid-column: 1 / 2;
            grid-row: 1 / 2;
            min-height: 400px;
            position: relative;
            overflow: hidden;
            background: #000;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        #screen-img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            border-radius: 4px;
        }
        
        /* Thought Panel */
        #thought-panel {
            grid-column: 1 / 2;
            grid-row: 2 / 3;
            overflow: hidden;
        }
        #thought-content {
            font-family: 'JetBrains Mono', monospace;
            white-space: pre-wrap;
            color: var(--thought-color);
            background: #0e0e10; /* Slightly darker */
            padding: 15px;
            border-radius: 6px;
            overflow-y: auto;
            flex: 1;
            font-size: 0.9rem;
            line-height: 1.5;
            border: 1px solid #1f2937;
        }

        /* Sidebar */
        #sidebar {
            grid-column: 2 / 3;
            grid-row: 1 / 3;
            display: flex;
            flex-direction: column;
            gap: 20px;
            overflow: hidden;
        }
        .sidebar-section {
            flex: 1;
            overflow: hidden;
        }
        .scroll-area {
            overflow-y: auto;
            flex: 1;
            padding-right: 5px;
        }
        
        /* Lists */
        ul {
            list-style-type: none;
            padding: 0;
            margin: 0;
        }
        li {
            padding: 12px;
            border-bottom: 1px solid var(--border-color);
            font-size: 0.9rem;
        }
        li:last-child {
            border-bottom: none;
        }
        .memory-key {
            font-weight: 700;
            color: var(--accent-color);
            display: block;
            margin-bottom: 4px;
        }
        .tool-category {
            font-weight: 700;
            margin-top: 20px;
            margin-bottom: 10px;
            text-transform: uppercase;
            font-size: 0.8rem;
            color: #71717a;
            letter-spacing: 0.05em;
            padding-left: 12px;
        }
        .tool-category:first-child {
            margin-top: 0;
        }
        .tool-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .tool-name {
            font-family: 'JetBrains Mono', monospace;
            color: #d4d4d8;
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: var(--bg-color); 
        }
        ::-webkit-scrollbar-thumb {
            background: #3f3f46; 
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #52525b; 
        }
        
        /* Connection Status */
        #status-indicator {
            position: absolute;
            top: 20px;
            right: 20px;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background-color: #ef4444; /* Red */
            z-index: 100;
            box-shadow: 0 0 10px #ef4444;
            transition: background-color 0.3s;
        }
        #status-indicator.connected {
            background-color: #22c55e; /* Green */
            box-shadow: 0 0 10px #22c55e;
        }

    </style>
</head>
<body>
    <div id="status-indicator" title="Disconnected"></div>

    <div id="screen-panel" class="panel">
        <h2>Live Vision</h2>
        <img id="screen-img" src="" alt="Live Feed - Waiting for Agent...">
    </div>
    
    <div id="thought-panel" class="panel">
        <h2>Cognitive Stream</h2>
        <div id="thought-content">Waiting for thoughts...</div>
    </div>

    <div id="sidebar">
        <div class="panel sidebar-section">
            <h2>Active Memory</h2>
            <div class="scroll-area" id="memory-list"></div>
        </div>
        <div class="panel sidebar-section">
            <h2>Available Tools</h2>
            <div class="scroll-area" id="tool-list"></div>
        </div>
    </div>

    <script>
        const statusIndicator = document.getElementById('status-indicator');
        
        function updateState() {
            fetch('/api/state')
                .then(response => {
                    if (response.ok) {
                        statusIndicator.classList.add('connected');
                        statusIndicator.title = "Connected";
                        return response.json();
                    } else {
                        throw new Error("Network response was not ok");
                    }
                })
                .then(data => {
                    // Update Screen
                    if (data.screenshot) {
                        document.getElementById('screen-img').src = 'data:image/jpeg;base64,' + data.screenshot;
                    }
                    
                    // Update Thought
                    if (data.thought) {
                        const thoughtEl = document.getElementById('thought-content');
                        // Only update if changed to avoid unnecessary re-renders/scroll jumps (primitive check)
                        if (thoughtEl.getAttribute('data-last') !== data.thought) {
                             thoughtEl.textContent = data.thought;
                             thoughtEl.setAttribute('data-last', data.thought);
                             thoughtEl.scrollTop = thoughtEl.scrollHeight;
                        }
                    }

                    // Update Memories
                    // In a real app we'd diff this, but for now we rebuild
                    const memList = document.getElementById('memory-list');
                    if (data.memories) {
                         const fragment = document.createDocumentFragment();
                         const ul = document.createElement('ul');
                         
                         if (Object.keys(data.memories).length === 0) {
                             ul.innerHTML = '<li style="color: #52525b; font-style: italic;">No active memories</li>';
                         } else {
                            for (const [key, value] of Object.entries(data.memories)) {
                                const li = document.createElement('li');
                                li.innerHTML = `<span class="memory-key">${key}</span>${value}`;
                                ul.appendChild(li);
                            }
                         }
                         fragment.appendChild(ul);
                         
                         // Rebuilding innerHTML every second is inefficient but fine for this scale
                         // To prevent scroll jumping only update if needed - skipping complex diff for now
                         // A simple hash or stringified compare would enable conditional update
                         
                         memList.innerHTML = '';
                         memList.appendChild(fragment);
                    }

                    // Update Tools
                    const toolList = document.getElementById('tool-list');
                    if (data.tools) {
                        const fragment = document.createDocumentFragment();
                        
                        for (const [category, tools] of Object.entries(data.tools)) {
                            if (tools.length === 0) continue;
                            
                            const catDiv = document.createElement('div');
                            catDiv.className = 'tool-category';
                            catDiv.textContent = category;
                            fragment.appendChild(catDiv);
                            
                            const ul = document.createElement('ul');
                            tools.forEach(tool => {
                                const li = document.createElement('li');
                                li.className = 'tool-item';
                                li.innerHTML = `<span class="tool-name">${tool.name}</span>`;
                                li.title = tool.description;
                                ul.appendChild(li);
                            });
                            fragment.appendChild(ul);
                        }
                        
                        toolList.innerHTML = '';
                        toolList.appendChild(fragment);
                    }
                })
                .catch(err => {
                    console.error("Error fetching state:", err);
                    statusIndicator.classList.remove('connected');
                    statusIndicator.title = "Disconnected";
                });
        }

        setInterval(updateState, 1000);
        updateState();
    </script>
</body>
</html>
    """

def start_server():
    # Run uvicorn programmatically
    # uvicorn.run(app, host="0.0.0.0", port=8000)
    # Using Config and Server instance to avoid some signal handling issues in threads
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="error")
    server = uvicorn.Server(config)
    
    # We need to run this in a loop if we were async, but since we are threading a blocking call:
    server.run()

def start_dashboard_thread():
    thread = threading.Thread(target=start_server, daemon=True)
    thread.start()
    print("\n---------------------------------------------------------")
    print(" >>> DASHBOARD RUNNING AT: http://localhost:8000 <<<")
    print("---------------------------------------------------------\n")
