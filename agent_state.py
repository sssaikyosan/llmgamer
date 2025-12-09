from typing import List, Dict, Any, Optional, Tuple
import datetime
import uuid
import json
from PIL import Image

class AgentState:
    def __init__(self, max_history: int = 10, max_screenshot_history: int = 3):
        self.messages: List[Dict[str, Any]] = []  # Structural chat history
        self.max_history = max_history
        self.variables: Dict[str, Any] = {}  # General purpose storage
        
        # スクリーンショット履歴管理
        self.max_screenshot_history = max_screenshot_history
        self.screenshot_history: List[Tuple[int, Image.Image]] = []  # [(turn_number, image), ...]
        self.turn_counter: int = 0

    def add_user_message(self, content: str):
        """ユーザーメッセージを追加"""
        self.messages.append({
            "role": "user",
            "content": content
        })
        self._trim_history()

    def add_assistant_message(self, thought: str, tool_call: Optional[Dict] = None):
        """
        アシスタントメッセージを追加（ネイティブFunction Calling形式）
        
        Args:
            thought: モデルの思考テキスト
            tool_call: ツール呼び出し情報 {"server": "...", "name": "...", "arguments": {...}}
        """
        message = {
            "role": "assistant",
            "content": thought if thought else ""
        }
        
        if tool_call:
            # OpenAI/Qwen互換形式でtool_callsを保存
            tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
            full_name = f"{tool_call.get('server', 'unknown')}.{tool_call.get('name', 'unknown')}"
            
            message["tool_calls"] = [{
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": full_name,
                    "arguments": json.dumps(tool_call.get("arguments", {}))
                }
            }]
            # IDを返却用に保持
            message["_tool_call_id"] = tool_call_id
        
        self.messages.append(message)
        self._trim_history()
        
        return message.get("_tool_call_id")

    def add_tool_result(self, tool_call_id: str, tool_name: str, result: str):
        """
        ツール実行結果を追加（ネイティブFunction Calling形式）
        
        Args:
            tool_call_id: ツール呼び出しID
            tool_name: ツール名
            result: 実行結果
        """
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result[:1000]  # 結果を制限
        })
        self._trim_history()

    def add_message(self, role: str, content: Any):
        """後方互換性のための汎用メッセージ追加"""
        serializable_content = content
        
        if isinstance(content, list):
            filtered_content = [item for item in content if isinstance(item, str)]
            serializable_content = filtered_content
        elif not isinstance(content, str):
            if hasattr(content, 'save'):  # PIL Image
                serializable_content = "[Image]"
            else:
                serializable_content = str(content)
                
        self.messages.append({"role": role, "content": serializable_content})
        self._trim_history()

    def _trim_history(self):
        """履歴を制限内に保つ"""
        # ターン数で制限（1ターン = user + assistant + tool）
        max_messages = self.max_history * 3
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    def get_messages_for_llm(self, provider: str = "gemini") -> List[Dict[str, Any]]:
        """
        LLMに送信するためのメッセージ履歴を取得 (Gemini専用)
        Note: provider引数は互換性のため残していますが、常にGemini形式を返します。
        """
        return self._convert_to_gemini_format()



    def _convert_to_gemini_format(self) -> List[Dict[str, Any]]:
        """Gemini形式に変換"""
        result = []
        for msg in self.messages:
            role = msg["role"]
            
            # Geminiは 'user' と 'model' のみサポート
            if role == "assistant":
                gemini_role = "model"
            elif role == "tool":
                # toolロールはuserとして扱う (Gemini API制約)
                gemini_role = "user"
            else:
                gemini_role = "user"
            
            parts = []
            
            # コンテンツをpartsに追加
            content = msg.get("content", "")
            
            # Toolの場合、分かりやすく修飾しても良いが、単純にcontentを入れる
            if role == "tool":
                name = msg.get("name", "unknown")
                # content = f"Tool[{name}] Output: {content}" # 必要なら修飾
            
            if content:
                parts.append(content)
            
            result.append({"role": gemini_role, "parts": parts})
        
        return result

    def get_current_time_str(self, timestamp: float = 0) -> str:
        if timestamp > 0:
            now = datetime.datetime.fromtimestamp(timestamp)
        else:
            now = datetime.datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")

    def add_screenshot(self, image: Image.Image) -> int:
        """
        スクリーンショットを履歴に追加し、ターン番号を返す。
        最大 max_screenshot_history ターン分を保持。
        """
        self.turn_counter += 1
        self.screenshot_history.append((self.turn_counter, image))
        
        # 古い履歴を削除
        while len(self.screenshot_history) > self.max_screenshot_history:
            self.screenshot_history.pop(0)
        
        return self.turn_counter

    def get_screenshot_history(self) -> List[Tuple[int, Image.Image]]:
        """
        スクリーンショット履歴を取得。
        戻り値: [(turn_number, image), ...] 古い順
        """
        return self.screenshot_history.copy()

    def get_screenshot_history_with_labels(self) -> List[Tuple[str, Image.Image]]:
        """
        ラベル付きでスクリーンショット履歴を取得。
        戻り値: [("Turn N", image), ...] 古い順
        """
        return [(f"Turn {turn}", img) for turn, img in self.screenshot_history]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state for saving."""
        return {
            "messages": self.messages,
            "variables": self.variables,
            "turn_counter": self.turn_counter
        }

    def from_dict(self, data: Dict[str, Any]):
        """Load state from dictionary."""
        self.messages = data.get("messages", [])
        self.variables = data.get("variables", {})
        self.turn_counter = data.get("turn_counter", 0)
        
        # スクリーンショット履歴はメモリ上のみ保持（ファイルには保存しない）
        # 後方互換性: 古い形式のhistoryがあれば無視
        # data.get("history", []) は使用しない
