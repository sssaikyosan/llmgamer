from typing import Dict, Union, Any

class MemoryManager:
    def __init__(self):
        # Format: {title: {"content": str, "accuracy": int}}
        self.memories: Dict[str, Dict[str, Any]] = {}

    def set_memory(self, title: str, content: str, accuracy: int = -1) -> str:
        """Add or update a memory with accuracy rating (0-100)."""
        if not title or not isinstance(title, str):
            return "Error: title is required and must be a non-empty string."
        if content is None:
            return "Error: content is required."
        
        # Normalize accuracy
        if accuracy < 0:
            accuracy = 0 # Default if not provided
        if accuracy > 100:
            accuracy = 100

        action = "updated" if title in self.memories else "added"
        self.memories[title] = {
            "content": content,
            "accuracy": accuracy
        }
        return f"Memory '{title}' {action} (Accuracy: {accuracy}%)."

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
        for title, data in self.memories.items():
            # Handle legacy format if any remains (though unlikely with restart)
            if isinstance(data, str):
                lines.append(f"- {title}: {data} (Accuracy: Unknown)")
            else:
                acc = data.get("accuracy", 0)
                content = data.get("content", "")
                lines.append(f"- {title}: {content} (Accuracy: {acc}%)")
            
        return "\n".join(lines)

