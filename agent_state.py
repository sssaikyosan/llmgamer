from typing import List, Dict, Any, Optional
import datetime
import base64
import io
from PIL import Image

class AgentState:
    def __init__(self, max_history: int = 10, max_screenshots: int = 3):
        self.history: List[str] = []
        self.screenshot_history: List[Dict[str, Any]] = [] # Stores {"time": str, "img": PIL.Image}
        self.messages: List[Dict[str, Any]] = [] # Structrual chat history [{"role": "user", "content": ...}]
        self.max_history = max_history
        self.max_screenshots = max_screenshots

    def add_history(self, action_result: str):
        """Adds an action result to the text history."""
        self.history.append(action_result)
        # Keep history limited if you want, though currently only retrieval is limited
        # internal storage can grow or we can limit it strictly here:
        # if len(self.history) > 100: self.history.pop(0)

    def add_message(self, role: str, content: Any):
        """Adds a message to the structured chat history."""
        self.messages.append({"role": role, "content": content})


    def get_history_string(self) -> str:
        """Returns the formatted history string for the prompt."""
        recent_history = self.history[-self.max_history:]
        if not recent_history:
            return "(No history yet)"
        return "\n".join([f"- {h}" for h in recent_history])

    def add_screenshot(self, screenshot_base64: str, timestamp: float) -> Optional[Image.Image]:
        """
        Decodes base64 screenshot, adds it to history with timestamp, 
        and returns the PIL Image object.
        """
        if not screenshot_base64:
            return None

        try:
            image_data = base64.b64decode(screenshot_base64)
            img = Image.open(io.BytesIO(image_data))
            
            if timestamp > 0:
                now = datetime.datetime.fromtimestamp(timestamp)
            else:
                now = datetime.datetime.now()
            
            current_timestamp_str = now.strftime("%H:%M:%S")
            
            self.screenshot_history.append({"time": current_timestamp_str, "img": img})
            
            # Maintain max size
            if len(self.screenshot_history) > self.max_screenshots:
                self.screenshot_history.pop(0)
                
            return img
        except Exception as e:
            print(f"Error adding screenshot to state: {e}")
            return None

    def get_latest_images_for_gemini(self) -> List[Image.Image]:
        """Returns the list of PIL images for the API call."""
        return [item["img"] for item in self.screenshot_history]

    def get_visual_history_log(self) -> str:
        """Returns the formatted string describing the visual history."""
        if not self.screenshot_history:
            return "(No visual history available)"
        
        return "\n".join(
            [f"   - Image {i}: Captured at {item['time']} {'(CURRENT)' if i == len(self.screenshot_history)-1 else ''}" 
             for i, item in enumerate(self.screenshot_history)]
        )

    def get_current_time_str(self, timestamp: float = 0) -> str:
        if timestamp > 0:
            now = datetime.datetime.fromtimestamp(timestamp)
        else:
            now = datetime.datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")
