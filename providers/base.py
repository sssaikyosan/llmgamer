"""
LLM Provider Base Class
Abstract base class for all LLM providers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from logger import get_logger

logger = get_logger(__name__)


class LLMProviderBase(ABC):
    """LLMプロバイダーの基底クラス"""
    
    def __init__(self, api_key: str, model_name: str, system_instruction: str = None):
        self.api_key = api_key
        self.model_name = model_name
        self.system_instruction = system_instruction
        self.tools = []
        self.tool_mapping = {}  # provider_tool_name -> {server, name}
    
    @abstractmethod
    def set_tools(self, tools: List[Dict[str, Any]]) -> None:
        """ツール定義を設定"""
        pass
    
    @abstractmethod
    async def generate_response(
        self,
        prompt: str,
        images: List[Any] = None,
        messages: List[Dict] = None,
        system_instruction: str = None
    ) -> Dict[str, Any]:
        """
        LLMにリクエストを送信
        
        Args:
            prompt: 現在のターンのプロンプト
            images: PIL.Imageのリスト
            messages: 内部形式のメッセージ履歴
            system_instruction: システムプロンプト (オプション、__init__のものを上書き)
        
        Returns:
            {
                "thought": str,  # テキスト応答
                "tool_call": {   # オプション (ツール呼び出しがある場合)
                    "id": str,       # プロバイダーが発行したID (Claude用)
                    "server": str,
                    "name": str,
                    "arguments": dict
                }
            }
        """
        pass
    
    @abstractmethod
    def convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict]:
        """内部形式からプロバイダー固有形式に変換"""
        pass
    
    def _sanitize_schema(self, schema: Any, uppercase_type: bool = False) -> Any:
        """
        共通: スキーマのサニタイズ処理
        
        Args:
            schema: 入力スキーマ
            uppercase_type: Trueの場合、typeを大文字に変換 (Gemini用)
        """
        if isinstance(schema, dict):
            # 共通でサポートされているスキーマフィールド
            valid_keys = {
                "type", "format", "description", "nullable", "enum", 
                "properties", "required", "items"
            }
            new_schema = {}
            for k, v in schema.items():
                if k == "properties":
                    # propertiesの中身は {prop_name: prop_schema} 
                    new_schema[k] = {
                        prop_name: self._sanitize_schema(prop_schema, uppercase_type)
                        for prop_name, prop_schema in v.items()
                    }
                elif k == "type" and isinstance(v, str) and uppercase_type:
                    # Geminiは大文字のtypeを期待
                    new_schema[k] = v.upper()
                elif k in valid_keys:
                    new_schema[k] = self._sanitize_schema(v, uppercase_type)
            return new_schema
        elif isinstance(schema, list):
            return [self._sanitize_schema(v, uppercase_type) for v in schema]
        return schema
    
    def _create_safe_tool_name(self, server: str, tool_name: str) -> str:
        """サーバー名とツール名から安全な名前を生成"""
        safe_server = server.replace(".", "_").replace("-", "_").replace(" ", "_")
        safe_tool = tool_name.replace(".", "_").replace("-", "_").replace(" ", "_")
        return f"{safe_server}__{safe_tool}"
    
    def _parse_tool_name(self, full_name: str) -> tuple:
        """
        安全な名前からサーバー名とツール名を解析
        
        Returns:
            (server_name, tool_name)
        """
        if full_name in self.tool_mapping:
            mapped = self.tool_mapping[full_name]
            return mapped["server"], mapped["name"]
        
        # フォールバック: __ で分割
        if "__" in full_name:
            parts = full_name.split("__", 1)
            return parts[0], parts[1]
        elif "_" in full_name:
            parts = full_name.split("_", 1)
            return parts[0], parts[1]
        
        return "unknown", full_name
