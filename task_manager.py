from typing import List, Optional
from dataclasses import dataclass, field

@dataclass
class SubTask:
    id: int
    description: str
    status: str = "pending"  # pending, completed

class TaskManager:
    def __init__(self, main_task: str):
        self.main_task = main_task
        self.sub_tasks: List[SubTask] = []
        self.completed_history: List[str] = []
        self._id_counter = 1

    def add_subtask(self, description: str) -> str:
        """Add a new sub-task to the list."""
        task = SubTask(id=self._id_counter, description=description)
        self.sub_tasks.append(task)
        self._id_counter += 1
        return f"Added subtask #{task.id}: {description}"

    def complete_subtask(self, task_id: int) -> str:
        """Mark a sub-task as completed and move it to history."""
        for i, task in enumerate(self.sub_tasks):
            if task.id == task_id:
                self.completed_history.append(f"Completed subtask: {task.description}")
                self.sub_tasks.pop(i)
                return f"Completed subtask #{task_id}."
        return f"Subtask #{task_id} not found."

    def update_main_task(self, new_task: str) -> str:
        """Update the main goal."""
        old_task = self.main_task
        self.completed_history.append(f"Finished Main Goal: {old_task}")
        self.main_task = new_task
        # Optionally clear subtasks when main task changes? 
        # For now, let's keep them unless explicitly cleared, but usually a new main task implies new subtasks.
        return f"Updated main task to: {new_task}"

    def get_context_string(self) -> str:
        """Generate a summary string for the LLM context."""
        summary = f"MAIN GOAL: {self.main_task}\n"
        
        if self.sub_tasks:
            summary += "CURRENT SUB-TASKS:\n"
            for t in self.sub_tasks:
                summary += f"  [ID: {t.id}] {t.description}\n"
        else:
            summary += "CURRENT SUB-TASKS: (None - You can add subtasks to break down the goal)\n"
            
        if self.completed_history:
            summary += "RECENT HISTORY:\n"
            for h in self.completed_history[-5:]:  # Show last 5 events
                summary += f"  - {h}\n"
                
        return summary
    
    def to_dict(self) -> dict:
        return {
            "main_task": self.main_task,
            "sub_tasks": [{"id": t.id, "description": t.description, "status": t.status} for t in self.sub_tasks],
            "completed_history": self.completed_history,
            "id_counter": self._id_counter
        }

    def from_dict(self, data: dict):
        self.main_task = data.get("main_task", self.main_task)
        self.completed_history = data.get("completed_history", [])
        self._id_counter = data.get("id_counter", 1)
        
        self.sub_tasks = []
        for t_data in data.get("sub_tasks", []):
            self.sub_tasks.append(SubTask(
                id=t_data["id"],
                description=t_data["description"], 
                status=t_data.get("status", "pending")
            ))
