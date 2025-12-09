from typing import Dict

class MemoryManager:
    def __init__(self):
        # Format: {title: {"content": str, "category": str}}
        self.memories: Dict[str, Dict[str, str]] = {}

    def set_memory(self, title: str, content: str, category: str = "Global") -> str:
        """Add or update a memory with a category."""
        if not title or not isinstance(title, str):
            return "Error: title is required and must be a non-empty string."
        if content is None:
            return "Error: content is required."
        
        valid_categories = ["Global", "Engineering", "Operation"]
        if category not in valid_categories:
            return f"Error: Invalid category '{category}'. Must be one of {valid_categories}."

        action = "updated" if title in self.memories else "added"
        self.memories[title] = {"content": content, "category": category}
        return f"Memory '{title}' ({category}) {action}."

    def delete_memory(self, title: str) -> str:
        """Delete a memory."""
        if not title or not isinstance(title, str):
            return "Error: title is required and must be a non-empty string."
        if title not in self.memories:
            return f"Error: Memory with title '{title}' not found."
        del self.memories[title]
        return f"Memory '{title}' deleted."
        
    def get_memories_string(self, categories: list[str] = None) -> str:
        """Get formatted memory string filtered by categories."""
        if not self.memories:
            return "(No active memories)"
            
        lines = []
        for title, data in self.memories.items():
            if categories is None or data["category"] in categories:
                lines.append(f"- [{data['category']}] {title}: {data['content']}")
        
        if not lines:
            return "(No relevant memories found)"
            
        return "\n".join(lines)

