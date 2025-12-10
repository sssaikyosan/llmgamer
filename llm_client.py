"""
LLM Client (Factory Pattern)
Provides a unified interface for multiple LLM providers.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from config import Config
from logger import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    """LLM関連のエラーを示す例外クラス"""
    pass


class LLMClient:
    """
    LLMクライアント (ファクトリーパターン)
    - プロバイダーに応じて適切な実装を使用
    - Gemini (デフォルト) または Claude をサポート
    """
    
    def __init__(
        self,
        provider: str = None,
        model_name: str = None,
        system_instruction: str = None
    ):
        """
        Args:
            provider: "gemini" or "claude" (default: Config.LLM_PROVIDER)
            model_name: モデル名 (default: Config.get_model_name())
            system_instruction: システムプロンプト
        """
        self.provider_name = provider or Config.LLM_PROVIDER
        self.model_name = model_name or Config.get_model_name()
        self.system_instruction = system_instruction
        
        # プロバイダーインスタンスを作成
        self._provider = self._create_provider()
        
        # 後方互換性のため
        self.tools = []
        self.gemini_tool_mapping = {}  # Gemini固有（後方互換用）
    
    def _create_provider(self):
        """プロバイダーを選択・初期化"""
        if self.provider_name == "claude":
            from providers.claude import ClaudeProvider
            api_key = Config.CLAUDE_API_KEY
            if not api_key:
                logger.warning("CLAUDE_API_KEY not found. Please set it in .env file.")
            return ClaudeProvider(
                api_key=api_key or "",
                model_name=self.model_name,
                system_instruction=self.system_instruction
            )
        else:  # Default: Gemini
            from providers.gemini import GeminiProvider
            api_key = Config.GEMINI_API_KEY
            if not api_key:
                logger.warning("GEMINI_API_KEY (or API_KEY) not found. Please set it in .env file.")
            return GeminiProvider(
                api_key=api_key or "",
                model_name=self.model_name,
                system_instruction=self.system_instruction
            )
    
    def set_tools(self, tools: List[Dict[str, Any]]):
        """
        ツール定義を設定
        tools: [{"server": "...", "name": "...", "description": "...", "inputSchema": {...}}, ...]
        """
        self.tools = tools  # 後方互換用
        self._provider.set_tools(tools)
        
        # 後方互換: gemini_tool_mappingを同期
        if hasattr(self._provider, 'tool_mapping'):
            self.gemini_tool_mapping = self._provider.tool_mapping
        
        logger.debug(f"Set {len(tools)} tools for LLM client (provider: {self.provider_name})")
    
    async def generate_response(
        self,
        prompt: str,
        images: List[Any] = None,
        messages: List[Dict] = None,
        system_instruction: str = None
    ) -> Dict[str, Any]:
        """
        LLMにリクエストを送信し、レスポンスを取得する（自動リトライ付き）
        
        Args:
            prompt: 現在のターンのプロンプト
            images: PIL.Imageのリスト
            messages: 内部形式のメッセージ履歴
            system_instruction: システムプロンプト (オプション)
        
        Returns:
            {
                "thought": str,  # テキスト応答
                "tool_call": {   # オプション
                    "id": str,       # プロバイダーが発行したID
                    "server": str,
                    "name": str,
                    "arguments": dict
                }
            }
        """
        if images is None:
            images = []
        
        # リトライ設定: API制限（1分）などを考慮し、回数と待機時間を増加
        max_retries = 5
        import asyncio
        import random
        
        for attempt in range(max_retries):
            try:
                return await self._provider.generate_response(
                    prompt, images, messages, system_instruction
                )
            except Exception as e:
                is_last_attempt = (attempt == max_retries - 1)
                
                if is_last_attempt:
                    logger.error(f"Failed after {max_retries} attempts. Last error: {e}")
                    raise LLMError(str(e))

                # エラー内容からレートリミットかどうかを判定
                error_msg = str(e).lower()
                is_rate_limit = any(x in error_msg for x in ["429", "resource exhausted", "quota", "limit", "overloaded"])
                
                if is_rate_limit:
                    # レートリミット時は長めに待機 (例: 30s, 60s, 70s...)
                    # 1分制限を確実にクリアするため、後半は60秒以上待つ
                    base_delay = 30 * (2 ** attempt)
                    delay = min(base_delay, 70) 
                else:
                    # その他のエラーは通常のバックオフ (2s, 4s, 8s, 16s...)
                    base_delay = 2 * (2 ** attempt)
                    delay = min(base_delay, 30)
                
                # ジッターを追加して分散
                jitter = random.uniform(0.1, 1.0)
                final_delay = delay + jitter
                
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed (RateLimit={is_rate_limit}): {e}. Retrying in {final_delay:.1f}s...")
                await asyncio.sleep(final_delay)
        
        return None
    
    def convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict]:
        """
        プロバイダー固有形式に変換
        (agent_state.py から呼び出し用)
        """
        return self._provider.convert_messages(messages)


# === 後方互換性のためのヘルパー関数 ===

def _proto_to_native(obj):
    """Convert proto objects (MapComposite, RepeatedComposite) to native Python types."""
    if hasattr(obj, 'items'):
        return {k: _proto_to_native(v) for k, v in obj.items()}
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
        return [_proto_to_native(item) for item in obj]
    else:
        return obj
