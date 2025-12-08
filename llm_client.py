import os
import re
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LLMClient:
    def __init__(self, provider: str = "gemini", model_name: str = "gemini-3-pro-preview"):
        self.provider = provider
        self.api_key = os.getenv("API_KEY")
        self.model_name = model_name
        
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
        elif self.provider == "lmstudio":
            self.base_url = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
            print(f"LLM Client initialized for LM Studio at {self.base_url}")

    def _pil_to_base64(self, image) -> str:
        import io
        import base64
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    async def generate_response(self, prompt: str, images: List[Any] = [], messages: List[Dict] = None) -> Optional[Dict[str, Any]]:
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
                        
                        # Handle image content in history if needed, though LM Studio might not support history images well yet?
                        # For now, let's simplify and just pass text for history, or use the last image only.
                        # Actually standard OpenAI format supports content as list of dicts.
                        
                        m_content = []
                        if isinstance(content, str):
                            m_content = content
                        elif isinstance(content, list):
                            # Try to preserve structure if it's already list of text/image
                            # But we need to ensure images are serializable (base64 or url)
                            # AgentState stores images as PIL objects in memory messages, 
                            # so we need to convert them here if we want to send history images.
                            # For saving tokens/bandwidth, maybe we skip old images in history?
                            # Let's filter out images from history for now, unless it's critical.
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
        """Parse LLM response handling <think> tags and markdown code blocks."""
        # Simply remove <think> blocks
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except:
                    pass
            print(f"Failed to parse JSON: {text}\nError: {e}")
            return None
