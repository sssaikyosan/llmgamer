from typing import List, Dict, Any, Optional, Tuple
import datetime
import uuid
import json
import base64
import io
from PIL import Image

class AgentState:
    def __init__(self, max_history: int = 10, max_screenshot_history: int = 3):
        # 役割ごとの独立した履歴管理
        # key: role name (e.g. "Operator", "MemorySaver"), value: list of messages
        self.role_histories: Dict[str, List[Dict[str, Any]]] = {
            "MemorySaver": [],
            "ToolCreator": [],
            "ResourceCleaner": [],
            "Operator": [],
            "General": [] # fallback
        }
        self.max_history = max_history # 各役割ごとの最大保持数
        
        self.variables: Dict[str, Any] = {}
        
        # スクリーンショット履歴
        self.max_screenshot_history = max_screenshot_history
        self.screenshot_history: List[Tuple[int, Image.Image]] = []
        self.turn_counter: int = 0

        # 全体履歴 (MemorySaver参照用、時系列の全イベント)
        self.global_history: List[Dict[str, Any]] = []
        self.max_global_history = max_history * 4

    def _add_to_role_history(self, role_name: str, message: Dict[str, Any]):
        """指定された役割の履歴にメッセージを追加"""
        target_list = self.role_histories.get(role_name, self.role_histories["General"])
        target_list.append(message)
        
        # Trim role history
        if len(target_list) > self.max_history * 3: # 1 turn approx 3 messages
            target_list.pop(0)

    def _add_to_global_history(self, message: Dict[str, Any]):
        """全体履歴に追加"""
        self.global_history.append(message)
        if len(self.global_history) > self.max_global_history * 3:
            self.global_history.pop(0)

    def add_user_message(self, content: str):
        """ユーザーメッセージを追加 (現在は使用頻度低、General扱い)"""
        msg = {"role": "user", "content": content}
        self._add_to_role_history("General", msg)
        self._add_to_global_history(msg)

    def add_assistant_message(self, thought: str, tool_call: Optional[Dict] = None, agent_role: str = "General"):
        """アシスタントの思考・行動を記録"""
        message = {
            "role": "assistant",
            "agent_role": agent_role,
            "content": thought if thought else ""
        }
        
        if tool_call:
            # プロバイダーが発行したIDがあればそれを使用（Claude）
            # なければ自前で生成（Gemini）
            tool_call_id = tool_call.get('id') or f"call_{uuid.uuid4().hex[:8]}"
            full_name = f"{tool_call.get('server', 'unknown')}.{tool_call.get('name', 'unknown')}"
            
            message["tool_calls"] = [{
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": full_name,  # strict name for internal storage
                    "arguments": json.dumps(tool_call.get("arguments", {}))
                }
            }]
            message["_tool_call_id"] = tool_call_id
        
        # 1. その役割の個別履歴に追加
        self._add_to_role_history(agent_role, message)
        
        # 2. 全体履歴に追加
        self._add_to_global_history(message)
        
        return message.get("_tool_call_id")

    def add_tool_result(self, tool_call_id: str, tool_name: str, result: str, agent_role: str = "General"):
        """ツール実行結果を記録"""
        message = {
            "role": "tool",
            "agent_role": agent_role,
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result[:1000]
        }
        
        # 1. その役割の個別履歴に追加
        self._add_to_role_history(agent_role, message)
        
        # 2. 全体履歴に追加
        self._add_to_global_history(message)

    def add_message(self, role: str, content: Any):
        """互換用"""
        serializable_content = str(content)
        msg = {"role": role, "content": serializable_content}
        self._add_to_role_history("General", msg)
        self._add_to_global_history(msg)

    def get_messages_for_llm(self, role_filter: Optional[str] = None, use_global: bool = False) -> List[Dict[str, Any]]:
        """
        LLM用履歴取得
        Args:
            role_filter: 取得したい役割名 (e.g. "Operator")
            use_global: Trueの場合、role_filterを無視して全体履歴を返す (MemorySaver用)
        """
        source_messages = []
        if use_global:
            source_messages = self.global_history
        elif role_filter:
            source_messages = self.role_histories.get(role_filter, [])
        else:
            source_messages = self.global_history # default fallback

        result = self._convert_to_gemini_format(source_messages)
        
        # 履歴がfunction_callで終わっている場合（不完全なペア）を削除
        # Gemini APIはfunction_callの後にfunction_responseが必須
        while result:
            last_msg = result[-1]
            has_function_call = False
            for part in last_msg.get("parts", []):
                if isinstance(part, dict) and "function_call" in part:
                    has_function_call = True
                    break
            if has_function_call:
                result.pop()  # 不完全なfunction_callを削除
            else:
                break
        
        return result

    def _convert_to_gemini_format(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Gemini形式に変換"""
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
            
            # tool roleの場合はfunction_responseとして処理するため、ここではcontentを追加しない
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
        # スクリーンショットをBase64エンコードして保存
        screenshot_data = []
        for turn_num, img in self.screenshot_history:
            try:
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                screenshot_data.append({
                    "turn": turn_num,
                    "image_base64": img_base64
                })
            except Exception:
                pass  # 保存できない画像はスキップ
        
        return {
            "role_histories": self.role_histories,
            "global_history": self.global_history,
            "variables": self.variables,
            "turn_counter": self.turn_counter,
            "screenshot_history": screenshot_data
        }

    def from_dict(self, data: Dict[str, Any]):
        """Load state from dictionary."""
        if "role_histories" in data:
            self.role_histories = data["role_histories"]
        if "global_history" in data:
            self.global_history = data["global_history"]
        self.variables = data.get("variables", {})
        self.turn_counter = data.get("turn_counter", 0)
        
        # スクリーンショット履歴を復元
        self.screenshot_history = []
        screenshot_data = data.get("screenshot_history", [])
        for item in screenshot_data:
            try:
                turn_num = item.get("turn", 0)
                img_base64 = item.get("image_base64", "")
                if img_base64:
                    img_bytes = base64.b64decode(img_base64)
                    img = Image.open(io.BytesIO(img_bytes))
                    self.screenshot_history.append((turn_num, img))
            except Exception:
                pass  # 復元できない画像はスキップ
