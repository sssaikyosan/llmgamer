
import re
import json
from config import Config
from typing import List, Dict, Any, Optional
from logger import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    """LLM関連のエラーを示す例外クラス"""
    pass


class LLMClient:
    def __init__(self, provider: str = "gemini", model_name: str = "gemini-3-pro-preview", system_instruction: str = None):
        self.provider = provider
        self.api_key = Config.API_KEY
        self.model_name = model_name
        
        if not self.api_key:
            logger.warning("No API_KEY found.")
            
        if self.provider == "gemini":
            self.model = None
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                # Initialize with system_instruction if provided
                if system_instruction:
                    self.model = genai.GenerativeModel(self.model_name, system_instruction=system_instruction)
                else:
                    self.model = genai.GenerativeModel(self.model_name)
                logger.info(f"LLM Client initialized for Gemini model: {self.model_name}")
            except ImportError:
                logger.critical("google-generativeai package not installed.")
                logger.critical("Please run: pip install google-generativeai")
            except Exception as e:
                logger.critical(f"Failed to initialize Gemini model: {e}")
            
            if self.model is None:
                logger.warning("Gemini model is not available. LLM calls will fail.")
        elif self.provider == "lmstudio":
            self.base_url = Config.LMSTUDIO_BASE_URL
            logger.info(f"LLM Client initialized for LM Studio at {self.base_url}")

    def _pil_to_base64(self, image) -> str:
        import io
        import base64
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    async def generate_response(self, prompt: str, images: List[Any] = [], messages: List[Dict] = None) -> Dict[str, Any]:
        """LLMにリクエストを送信し、レスポンスを取得する（自動リトライ付き）。"""
        max_retries = 3
        import asyncio
        for attempt in range(max_retries):
            try:
                return await self._generate_response_impl(prompt, images, messages)
            except (LLMError, json.JSONDecodeError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed after {max_retries} attempts. Last error: {e}")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                await asyncio.sleep(1)
        return None

    async def _generate_response_impl(self, prompt: str, images: List[Any] = [], messages: List[Dict] = None) -> Dict[str, Any]:
        """LLMリクエストの実装部分。"""
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
                    
                    # Handle safety blocks or empty responses
                    if not response.parts:
                        finish_reason = response.candidates[0].finish_reason if response.candidates else "UNKNOWN"
                        raise LLMError(f"レスポンスが空です。終了理由: {finish_reason}")
                        
                    return self._parse_response(response.text)
                
                else:
                    # Legacy single turn mode
                    # Prepare inputs: [prompt, image1, image2, ...]
                    inputs = [prompt] + images
                    response = self.model.generate_content(inputs)
                    return self._parse_response(response.text)
            except LLMError:
                raise
            except Exception as e:
                import traceback
                traceback.print_exc()
                raise LLMError(f"Gemini APIエラー: {e}")
        
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
                logger.debug(f"Sending request to LM Studio ({self.base_url}). Model: {use_model}")
                
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
                    raise LLMError(f"LM Studio リクエストエラー: {req_err}")
                    
            except LLMError:
                raise
            except Exception as e:
                raise LLMError(f"LM Studio エラー: {e}")

        else:
            raise LLMError(f"プロバイダー '{self.provider}' は実装されていないか、初期化されていません。")

    def _parse_response(self, text: str) -> Dict[str, Any]:
        # Remove <think> blocks for JSON parsing
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()
        
        try:
            data = json.loads(text)
            return data
        except json.JSONDecodeError as e:
            # Try to find JSON object in text
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                try:
                    data = json.loads(text[start:end+1])
                    return data
                except json.JSONDecodeError:
                    pass
            
            # Fallback for non-JSON responses (e.g. plain text or code)
            logger.warning(f"JSON parse failed. Error: {e}")
            raise e
