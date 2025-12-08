from typing import Dict

class MemoryManager:
    def __init__(self):
        self.memories: Dict[str, str] = {}

    def set_memory(self, title: str, content: str) -> str:
        """Add or update a memory."""
        action = "updated" if title in self.memories else "added"
        self.memories[title] = content
        return f"Memory '{title}' {action}."

    def delete_memory(self, title: str) -> str:
        """Delete a memory."""
        if title not in self.memories:
            return f"Error: Memory with title '{title}' not found."
        del self.memories[title]
        return f"Memory '{title}' deleted."
