"""
Gemini LLM Provider
Google Generative AI (Gemini) implementation.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from .base import LLMProviderBase
from logger import get_logger

logger = get_logger(__name__)


def _proto_to_native(obj):
    """Convert proto objects (MapComposite, RepeatedComposite) to native Python types."""
    if hasattr(obj, 'items'):  # dict-like (MapComposite)
        return {k: _proto_to_native(v) for k, v in obj.items()}
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):  # list-like (RepeatedComposite)
        return [_proto_to_native(item) for item in obj]
    else:
        return obj


class GeminiProvider(LLMProviderBase):
    """
    Google Gemini API プロバイダー
    - google.generativeai のネイティブFunction Calling を使用
    """
    
    def __init__(self, api_key: str, model_name: str, system_instruction: str = None):
        super().__init__(api_key, model_name, system_instruction)
        
        self.genai = None
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.genai = genai
            logger.info(f"Gemini Provider initialized: {model_name}")
        except ImportError:
            logger.critical("google-generativeai package not installed.")
            logger.critical("Please run: pip install google-generativeai")
        except Exception as e:
            logger.critical(f"Failed to initialize Gemini: {e}")

    def set_tools(self, tools: List[Dict[str, Any]]) -> None:
        """ツール定義を設定"""
        self.tools = tools
        self.tool_mapping = {}
        logger.debug(f"Set {len(tools)} tools for Gemini")

    def _convert_tools_for_gemini(self) -> List[Dict]:
        """ツール定義をGemini形式に変換"""
        function_declarations = []
        self.tool_mapping = {}
        
        for tool in self.tools:
            # 安全な名前を生成
            full_name = self._create_safe_tool_name(tool['server'], tool['name'])
            
            # マッピングを保存
            self.tool_mapping[full_name] = {
                "server": tool['server'],
                "name": tool['name']
            }
            
            # スキーマをサニタイズ (Geminiは大文字のtypeを期待)
            schema = self._sanitize_schema(tool.get("inputSchema", {}), uppercase_type=True)
            
            # 整合性チェック: requiredに含まれるキーがpropertiesに存在することを確認
            if isinstance(schema, dict) and "properties" in schema:
                if "required" in schema and isinstance(schema["required"], list):
                    original_required = schema["required"]
                    valid_required = [
                        k for k in original_required 
                        if k in schema["properties"]
                    ]
                    if len(valid_required) != len(original_required):
                        logger.warning(f"Tool {full_name}: Filtered required fields from {original_required} to {valid_required}")
                    
                    schema["required"] = valid_required
                    
                # 空のrequiredリストは削除
                if "required" in schema and not schema["required"]:
                    del schema["required"]

            # propertiesがない場合、requiredも削除
            if isinstance(schema, dict) and "properties" not in schema and "required" in schema:
                del schema["required"]
            
            # 空のpropertiesを持つスキーマの処理
            # Geminiはパラメータなし関数を受け付けない場合があるので対処
            if isinstance(schema, dict):
                props = schema.get("properties", {})
                if not props:
                    # ダミーパラメータを追加
                    schema["properties"] = {
                        "_placeholder": {
                            "type": "STRING",
                            "description": "Optional placeholder parameter (can be ignored)"
                        }
                    }
                    if "required" in schema:
                        del schema["required"]

            func_decl = {
                "name": full_name,
                "description": f"[{tool['server']}] {tool.get('description', '')}",
                "parameters": schema
            }
            function_declarations.append(func_decl)
        
        return function_declarations

    def convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict]:
        """内部形式からGemini形式に変換"""
        result = []
        for msg in messages:
            role = msg["role"]
            
            # Gemini mapping
            if role == "assistant":
                gemini_role = "model"
            elif role == "tool":
                gemini_role = "user"
            else:
                gemini_role = "user"
            
            parts = []
            content = msg.get("content", "")
            
            # tool roleの場合はfunction_responseとして処理するため、contentを追加しない
            if content and role != "tool":
                parts.append(content)
            
            # Tool Call restoration
            if role == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    if "function" in tc:
                        func = tc["function"]
                        full_name = func["name"]
                        gemini_name = full_name.replace(".", "__") if "." in full_name else full_name
                        try:
                            args = json.loads(func["arguments"])
                        except:
                            args = {}
                        parts.append({
                           "function_call": {
                               "name": gemini_name,
                               "args": args
                           }
                        })

            # Tool Response restoration
            if role == "tool":
                full_name = msg.get("name", "unknown")
                gemini_name = full_name.replace(".", "__") if "." in full_name else full_name
                parts.append({
                   "function_response": {
                       "name": gemini_name,
                       "response": {"result": content} 
                   }
                })

            if parts:
                result.append({"role": gemini_role, "parts": parts})
        
        return result

    async def generate_response(
        self,
        prompt: str,
        images: List[Any] = None,
        messages: List[Dict] = None,
        system_instruction: str = None
    ) -> Dict[str, Any]:
        """Gemini APIリクエスト"""
        if not self.genai:
            raise Exception("Gemini is not initialized.")
        
        if images is None:
            images = []
        
        try:
            # ツール定義を準備
            tools_config = None
            if self.tools:
                function_declarations = self._convert_tools_for_gemini()
                tools_config = [{"function_declarations": function_declarations}]
                logger.debug(f"tools_config: {json.dumps(tools_config, indent=2, default=str)}")
            
            # モデルを初期化
            model_config = {}
            
            # システムプロンプト
            active_instruction = system_instruction if system_instruction else self.system_instruction
            if active_instruction:
                model_config["system_instruction"] = active_instruction
            
            model = self.genai.GenerativeModel(
                self.model_name,
                tools=tools_config,
                **model_config
            )
            
            # 履歴を構築
            history = []
            if messages:
                history = self.convert_messages(messages)
            
            # 履歴がfunction_callで終わっている場合（不完全なペア）を削除
            while history:
                last_msg = history[-1]
                has_function_call = False
                for part in last_msg.get("parts", []):
                    if isinstance(part, dict) and "function_call" in part:
                        has_function_call = True
                        break
                if has_function_call:
                    history.pop()
                else:
                    break
            
            # チャットセッション開始
            chat = model.start_chat(history=history)
            
            # デバッグログ
            logger.debug(f"=== Gemini Request Debug ===")
            logger.debug(f"History length: {len(history)}")
            for i, h in enumerate(history):
                role = h.get('role', 'unknown')
                parts_summary = []
                for p in h.get('parts', []):
                    if isinstance(p, str):
                        parts_summary.append(f"text({len(p)} chars)")
                    elif isinstance(p, dict):
                        if 'function_call' in p:
                            parts_summary.append(f"function_call({p['function_call'].get('name', 'unknown')})")
                        elif 'function_response' in p:
                            parts_summary.append(f"function_response({p['function_response'].get('name', 'unknown')})")
                        else:
                            parts_summary.append(f"dict({list(p.keys())})")
                    else:
                        parts_summary.append(f"other({type(p).__name__})")
                logger.debug(f"  [{i}] role={role}, parts=[{', '.join(parts_summary)}]")
            
            # 現在のターンの入力
            inputs = [prompt] + images
            response = chat.send_message(inputs)
            
            # レスポンスを処理
            if not response.candidates:
                raise Exception("レスポンスにcandidatesがありません。")
            
            candidate = response.candidates[0]
            
            # 結果オブジェクト初期化
            result = {"thought": ""}
            
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    # テキストパート
                    if hasattr(part, 'text') and part.text:
                        result["thought"] = part.text
                    
                    # Function Callパート
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        
                        server_name, tool_name = self._parse_tool_name(fc.name)
                        args = _proto_to_native(fc.args) if fc.args else {}
                        
                        result["tool_call"] = {
                            "id": None,  # Gemini は明示的なIDを発行しない
                            "server": server_name,
                            "name": tool_name,
                            "arguments": args
                        }
            
            return result
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise Exception(f"Gemini APIエラー: {e}")
