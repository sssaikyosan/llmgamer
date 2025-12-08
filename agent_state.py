from typing import List, Dict, Any
import datetime

class AgentState:
    def __init__(self, max_history: int = 10):
        # NOTE: self.history は現在未使用。チェックポイント互換性のため保持。
        # 将来のバージョンで削除予定。
        self.history: List[str] = []  # DEPRECATED
        self.messages: List[Dict[str, Any]] = []  # Structural chat history
        self.max_history = max_history
        self.variables: Dict[str, Any] = {}  # General purpose storage for agent variables

    def add_history(self, action_result: str):
        """Adds an action result to the text history.
        
        DEPRECATED: This method is not currently used. Kept for checkpoint compatibility.
        """
        self.history.append(action_result)

    def add_message(self, role: str, content: Any):
        """Adds a message to the structured chat history."""
        # For memory efficiency, we do not store Image objects in the persistent message history.
        # We only store the text content. The 'current' image is passed separately during the turn.
        
        serializable_content = content
        
        # If content has images (list format), filter them out for storage
        if isinstance(content, list):
            filtered_content = []
            for item in content:
                if isinstance(item, str):
                    filtered_content.append(item)
                # Ignore image objects
            serializable_content = filtered_content
        elif not isinstance(content, str):
            # If it's a raw image object or non-serializable, convert to string placeholder or ignore
            if hasattr(content, 'save'): # Duck typing for PIL Image
                serializable_content = "[Image]"
            else:
                serializable_content = str(content)
                
        self.messages.append({"role": role, "content": serializable_content})

    def get_history_string(self) -> str:
        """Returns the formatted history string for the prompt.
        
        DEPRECATED: This method is not currently used. Kept for checkpoint compatibility.
        """
        recent_history = self.history[-self.max_history:]
        if not recent_history:
            return "(No history yet)"
        return "\n".join([f"- {h}" for h in recent_history])

    def get_current_time_str(self, timestamp: float = 0) -> str:
        if timestamp > 0:
            now = datetime.datetime.fromtimestamp(timestamp)
        else:
            now = datetime.datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state for saving."""
        return {
            "history": self.history,
            "messages": self.messages,
            "variables": self.variables
        }

    def from_dict(self, data: Dict[str, Any]):
        """Load state from dictionary."""
        self.history = data.get("history", [])
        self.messages = data.get("messages", [])
        self.variables = data.get("variables", {})

