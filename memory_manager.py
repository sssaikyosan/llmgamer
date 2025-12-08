import json
from typing import Dict, Optional

class MemoryManager:
    def __init__(self):
        self.memories: Dict[str, str] = {}

    def add_memory(self, title: str, content: str) -> str:
        """Add a new memory."""
        self.memories[title] = content
        return f"Memory '{title}' added."

    def edit_memory(self, title: str, content: str) -> str:
        """Edit an existing memory."""
        if title not in self.memories:
            return f"Error: Memory with title '{title}' not found."
        self.memories[title] = content
        return f"Memory '{title}' updated."

    def delete_memory(self, title: str) -> str:
        """Delete a memory."""
        if title not in self.memories:
            return f"Error: Memory with title '{title}' not found."
        del self.memories[title]
        return f"Memory '{title}' deleted."
