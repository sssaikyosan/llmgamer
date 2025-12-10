"""
Claude LLM Provider
Anthropic Claude API implementation.
"""

import json
import base64
import io
from typing import List, Dict, Any, Optional
from PIL import Image

from .base import LLMProviderBase
from logger import get_logger

logger = get_logger(__name__)


class ClaudeProvider(LLMProviderBase):
    """
    Anthropic Claude API プロバイダー
    - anthropic パッケージを使用
    - Native Tool Use をサポート
    """
    
    def __init__(self, api_key: str, model_name: str, system_instruction: str = None):
        super().__init__(api_key, model_name, system_instruction)
        
        self.client = None
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
            logger.info(f"Claude Provider initialized: {model_name}")
        except ImportError:
            logger.critical("anthropic package not installed.")
            logger.critical("Please run: pip install anthropic")
        except Exception as e:
            logger.critical(f"Failed to initialize Claude: {e}")
    
    def set_tools(self, tools: List[Dict[str, Any]]) -> None:
        """ツール定義を設定"""
        self.tools = tools
        self.tool_mapping = {}
        logger.debug(f"Set {len(tools)} tools for Claude")
    
    def _convert_tools_for_claude(self) -> List[Dict]:
        """内部ツール形式をClaude形式に変換"""
        claude_tools = []
        self.tool_mapping = {}
        
        for tool in self.tools:
            # 安全な名前を生成
            full_name = self._create_safe_tool_name(tool['server'], tool['name'])
            
            # マッピングを保存
            self.tool_mapping[full_name] = {
                "server": tool['server'],
                "name": tool['name']
            }
            
            # スキーマをサニタイズ (Claudeは小文字のtypeでOK)
            schema = self._sanitize_schema(tool.get("inputSchema", {}), uppercase_type=False)
            
            # 空のスキーマを処理
            if not schema or (isinstance(schema, dict) and not schema.get("properties")):
                schema = {"type": "object", "properties": {}}
            
            # Claude用ツール定義
            claude_tool = {
                "name": full_name,
                "description": f"[{tool['server']}] {tool.get('description', '')}",
                "input_schema": schema
            }
            claude_tools.append(claude_tool)
        
        return claude_tools
    
    def _convert_image_to_claude(self, image: Image.Image) -> Dict:
        """PIL ImageをClaude形式に変換"""
        buffer = io.BytesIO()
        
        # 画像フォーマットを判定
        img_format = image.format if image.format else 'PNG'
        if img_format.upper() == 'JPEG':
            media_type = "image/jpeg"
        elif img_format.upper() == 'GIF':
            media_type = "image/gif"
        elif img_format.upper() == 'WEBP':
            media_type = "image/webp"
        else:
            img_format = 'PNG'
            media_type = "image/png"
        
        # RGBAの場合、PNGで保存（JPEGは透過に対応していない）
        if image.mode == 'RGBA' and img_format.upper() == 'JPEG':
            img_format = 'PNG'
            media_type = "image/png"
        
        image.save(buffer, format=img_format)
        image_data = base64.standard_b64encode(buffer.getvalue()).decode('utf-8')
        
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data
            }
        }
    
    def convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict]:
        """内部形式からClaude形式に変換"""
        result = []
        
        for msg in messages:
            role = msg["role"]
            
            # Claude uses "assistant" instead of "model"
            if role == "assistant":
                claude_role = "assistant"
            elif role == "tool":
                claude_role = "user"  # tool results go in user messages
            else:
                claude_role = "user"
            
            content = []
            text_content = msg.get("content", "")
            
            # テキストコンテンツ (tool以外)
            if text_content and role != "tool":
                content.append({"type": "text", "text": text_content})
            
            # ツール呼び出し (復元)
            if role == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    if "function" in tc:
                        func = tc["function"]
                        full_name = func["name"]
                        claude_name = full_name.replace(".", "__")
                        try:
                            args = json.loads(func["arguments"])
                        except:
                            args = {}
                        
                        content.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": claude_name,
                            "input": args
                        })
            
            # ツール結果 (復元)
            if role == "tool":
                content.append({
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", "unknown"),
                    "content": text_content
                })
            
            if content:
                result.append({"role": claude_role, "content": content})
        
        # Claude: 連続する同じロールのメッセージをマージ
        merged = self._merge_consecutive_roles(result)
        
        return merged
    
    def _merge_consecutive_roles(self, messages: List[Dict]) -> List[Dict]:
        """連続する同じロールのメッセージをマージ"""
        if not messages:
            return messages
        
        merged = []
        for msg in messages:
            if merged and merged[-1]["role"] == msg["role"]:
                # 同じロールなのでcontentを統合
                merged[-1]["content"].extend(msg["content"])
            else:
                # 新しいメッセージを追加
                merged.append({
                    "role": msg["role"],
                    "content": msg["content"].copy() if isinstance(msg["content"], list) else msg["content"]
                })
        
        return merged
    
    async def generate_response(
        self,
        prompt: str,
        images: List[Any] = None,
        messages: List[Dict] = None,
        system_instruction: str = None
    ) -> Dict[str, Any]:
        """Claude APIリクエスト"""
        if not self.client:
            raise Exception("Claude client is not initialized")
        
        if images is None:
            images = []
        
        try:
            # ツール定義を準備
            tools_config = self._convert_tools_for_claude() if self.tools else None
            
            # システムプロンプト
            system = system_instruction or self.system_instruction or ""
            
            # 履歴を変換
            history = self.convert_messages(messages) if messages else []
            
            # 不完全なツール呼び出しを削除
            history = self._remove_incomplete_tool_calls(history)
            
            # 現在のプロンプトを構築
            current_content = []
            
            # 画像を追加
            for img in images:
                if isinstance(img, Image.Image):
                    current_content.append(self._convert_image_to_claude(img))
            
            # テキストを追加
            current_content.append({"type": "text", "text": prompt})
            
            # 履歴の最後がuserなら統合、そうでなければ新規追加
            if history and history[-1]["role"] == "user":
                history[-1]["content"].extend(current_content)
            else:
                history.append({"role": "user", "content": current_content})
            
            # 最初のメッセージがuserでない場合の対処
            if history and history[0]["role"] != "user":
                # 先頭に空のuserメッセージを追加
                history.insert(0, {"role": "user", "content": [{"type": "text", "text": "(system started)"}]})
            
            # API呼び出し
            kwargs = {
                "model": self.model_name,
                "max_tokens": 4096,
                "messages": history
            }
            if system:
                kwargs["system"] = system
            if tools_config:
                kwargs["tools"] = tools_config
            
            logger.debug(f"=== Claude Request Debug ===")
            logger.debug(f"Model: {self.model_name}")
            logger.debug(f"Messages count: {len(history)}")
            logger.debug(f"Tools count: {len(tools_config) if tools_config else 0}")
            for i, h in enumerate(history):
                role = h.get('role', 'unknown')
                content_summary = []
                for c in h.get('content', []):
                    if isinstance(c, dict):
                        content_summary.append(c.get('type', 'unknown'))
                    else:
                        content_summary.append('text')
                logger.debug(f"  [{i}] role={role}, content=[{', '.join(content_summary)}]")
            
            response = self.client.messages.create(**kwargs)
            
            # レスポンス解析
            result = {"thought": ""}
            
            for block in response.content:
                if block.type == "text":
                    result["thought"] = block.text
                
                elif block.type == "tool_use":
                    # ツール呼び出しを解析
                    server_name, original_tool_name = self._parse_tool_name(block.name)
                    
                    result["tool_call"] = {
                        "id": block.id,  # Claude固有: tool_use_idとして保存
                        "server": server_name,
                        "name": original_tool_name,
                        "arguments": block.input if hasattr(block, 'input') else {}
                    }
            
            return result
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise Exception(f"Claude APIエラー: {e}")
    
    def _remove_incomplete_tool_calls(self, messages: List[Dict]) -> List[Dict]:
        """不完全なツール呼び出し（結果がないもの）を削除"""
        if not messages:
            return messages
        
        # 最後のメッセージがassistantでtool_useを含む場合、削除
        while messages:
            last_msg = messages[-1]
            if last_msg["role"] == "assistant":
                has_tool_use = any(
                    isinstance(c, dict) and c.get("type") == "tool_use"
                    for c in last_msg.get("content", [])
                )
                if has_tool_use:
                    messages.pop()
                    continue
            break
        
        return messages
