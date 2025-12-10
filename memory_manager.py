from typing import Dict

class MemoryManager:
    def __init__(self):
        # Simple format: {title: content}
        self.memories: Dict[str, str] = {}

    def set_memory(self, title: str, content: str) -> str:
        """Add or update a memory."""
        if not title or not isinstance(title, str):
            return "Error: title is required and must be a non-empty string."
        if content is None:
            return "Error: content is required."

        action = "updated" if title in self.memories else "added"
        self.memories[title] = content
        return f"Memory '{title}' {action}."

    def delete_memory(self, title: str) -> str:
        """Delete a memory."""
        if not title or not isinstance(title, str):
            return "Error: title is required and must be a non-empty string."
        if title not in self.memories:
            return f"Error: Memory with title '{title}' not found."
        del self.memories[title]
        return f"Memory '{title}' deleted."
        
    def get_memories_string(self) -> str:
        """Get formatted memory string."""
        if not self.memories:
            return "(No active memories)"
            
        lines = []
        for title, content in self.memories.items():
            lines.append(f"- {title}: {content}")
            
        return "\n".join(lines)

