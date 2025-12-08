import os
import re
import json
import time
from collections import deque
from config import Config
from typing import List, Dict, Any, Optional

class RateLimiter:
    def __init__(self, rpm: int, rpd: int):
        self.rpm = rpm
        self.rpd = rpd
        self.requests_min = deque()
        self.requests_day = deque()

    def wait_for_slot(self):
        current_time = time.time()
        
        # Clean up old timestamps
        while self.requests_min and current_time - self.requests_min[0] > 60:
            self.requests_min.popleft()
        while self.requests_day and current_time - self.requests_day[0] > 86400:
            self.requests_day.popleft()
            
        # Check limits
        if len(self.requests_min) >= self.rpm:
            sleep_time = 60 - (current_time - self.requests_min[0]) + 1
            if sleep_time > 0:
                print(f"Rate limit (RPM) reached. Sleeping for {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                # Re-check/Reset time after sleep
                self.wait_for_slot()
                return

        if len(self.requests_day) >= self.rpd:
            print("Rate limit (RPD) reached. Waiting...")
            time.sleep(60) 
            self.wait_for_slot()
            return
            
        # Add current request
        self.requests_min.append(time.time())
        self.requests_day.append(time.time())

class LLMClient:
    def __init__(self, provider: str = "gemini", model_name: str = "gemini-3-pro-preview"):
        self.provider = provider
        self.api_key = Config.API_KEY
        self.model_name = model_name
        
        # Rate Limiter
        self.rate_limiter = RateLimiter(Config.GEMINI_RPM, Config.GEMINI_RPD)
        
        if not self.api_key:
            print("WARNING: No API_KEY found.")
            
        if self.provider == "gemini":
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
            except ImportError:
                print("Error: google-generativeai package not installed.")
                self.model = None
            # Removed erroneous self.model = None line here
        elif self.provider == "lmstudio":
            self.base_url = Config.LMSTUDIO_BASE_URL
            print(f"LLM Client initialized for LM Studio at {self.base_url}")

    def _pil_to_base64(self, image) -> str:
        import io
        import base64
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    async def generate_response(self, prompt: str, images: List[Any] = [], messages: List[Dict] = None) -> Optional[Dict[str, Any]]:
        # Enforce rate limits before any request attempt
        if self.provider == "gemini":
            self.rate_limiter.wait_for_slot()

        if self.provider == "gemini" and self.model:
            try:
                if messages:
                    # Convert messages to Gemini history format
                    # Expected format for history: [{'role': 'user'|'model', 'parts': [...]}, ...]
                    history = []
                    for msg in messages:
                        role = "model" if msg["role"] == "assistant" else "user"
                        content = msg["content"]
                        parts = []
                        if isinstance(content, str):
                            parts.append(content)
                        elif isinstance(content, list):
                            # Handle mixed content (text + images) if stored in list
                            for item in content:
                                if isinstance(item, str):
                                    parts.append(item)
                                # Assuming PIL Image logic handles images separately or we need to process them here
                                # If content has PIL images, we need to pass them directly.
                                # Since we can't easily iterate and check types for everything without importing PIL, 
                                # rely on genai's flexible input handling usually.
                                else:
                                    parts.append(item)
                        history.append({"role": role, "parts": parts})
                    
                    chat = self.model.start_chat(history=history)
                    
                    # Current turn input
                    inputs = [prompt] + images
                    response = chat.send_message(inputs)
                    
                    # Handle safety blocks or empty responses gracefully
                    if not response.parts:
                        print(f"LLM Warning: No parts returned. Finish reason: {response.candidates[0].finish_reason}")
                        return None
                        
                    return self._parse_response(response.text)
                
                else:
                    # Legacy single turn mode
                    # Prepare inputs: [prompt, image1, image2, ...]
                    inputs = [prompt] + images
                    response = self.model.generate_content(inputs)
                    return self._parse_response(response.text)
            except Exception as e:
                print(f"LLM Error: {e}")
                import traceback
                traceback.print_exc()
                return None
        
        elif self.provider == "lmstudio":
            try:
                import urllib.request
                import json
                
                messages_payload = []
                
                # Add history if provided
                if messages:
                    for msg in messages:
                        role = msg["role"]
                        content = msg["content"]
                        
                        m_content = []
                        if isinstance(content, str):
                            m_content = content
                        elif isinstance(content, list):
                            text_parts = []
                            for item in content:
                                if isinstance(item, str):
                                    text_parts.append(item)
                            m_content = "\n".join(text_parts)
                        
                        messages_payload.append({"role": role, "content": m_content})

                # Current turn content
                content = [{"type": "text", "text": prompt}]
                
                # Process images for current turn
                for img in images:
                    base64_img = self._pil_to_base64(img)
                    content.append({
                        "type": "image_url", 
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
                    })
                
                messages_payload.append({"role": "user", "content": content})
                
                # Ensure model name is safe
                use_model = self.model_name if self.model_name else "local-model"

                payload = {
                    "model": use_model, 
                    "messages": messages_payload,
                    "stream": False
                }
                
                # Debug payload (without massive image data)
                debug_payload = payload.copy()
                debug_payload["messages"] = [{"role": "user", "content": "..."}] # Hide content for log
                print(f"Sending request to LM Studio ({self.base_url}). Model: {use_model}")
                
                headers = {"Content-Type": "application/json"}
                
                req = urllib.request.Request(
                    f"{self.base_url}/chat/completions",
                    data=json.dumps(payload).encode('utf-8'),
                    headers=headers
                )
                
                try:
                    with urllib.request.urlopen(req) as response:
                        result = json.loads(response.read().decode('utf-8'))
                        text_response = result['choices'][0]['message']['content']
                        return self._parse_response(text_response)
                except Exception as req_err:
                    print(f"LM Studio Request Error: {req_err}")
                    return None
                    
            except Exception as e:
                print(f"LLM Error (LM Studio): {e}")
                return None

        else:
            print(f"Provider {self.provider} not implemented or initialized.")
            return None

    def _parse_response(self, text: str) -> Optional[Dict[str, Any]]:
        # Extract <think> content
        thought = None
        think_match = re.search(r'<think>(.*?)</think>', text, flags=re.DOTALL)
        if think_match:
            thought = think_match.group(1).strip()

        # Remove <think> blocks for JSON parsing
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()
        
        try:
            data = json.loads(text)
            if thought:
                data["_thought"] = thought
            return data
        except json.JSONDecodeError as e:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                try:
                    data = json.loads(text[start:end+1])
                    if thought:
                        data["_thought"] = thought
                    return data
                except:
                    pass
            print(f"Failed to parse JSON: {text}\nError: {e}")
            return None
