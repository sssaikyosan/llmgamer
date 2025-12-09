
import json
import os
from datetime import datetime
from config import Config
from typing import List, Dict, Any, Optional
from logger import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    """LLM関連のエラーを示す例外クラス"""
    pass


class LLMClient:
    """
    LLMクライアント (Gemini専用)
    - google.generativeai のネイティブFunction Calling / Tool Useを使用
    """
    
    def __init__(self, provider: str = "gemini", model_name: str = "gemini-2.0-flash-exp", system_instruction: str = None):
        # provider引数は互換性のため残すが、Geminiのみサポート
        self.provider = "gemini"
        self.api_key = Config.API_KEY
        self.model_name = model_name
        self.system_instruction = system_instruction
        self.tools = []  # ツール定義を保持
        self.gemini_tool_mapping = {} # Gemini関数名 -> (server, name) のマッピング
        
        if not self.api_key:
            logger.warning("No API_KEY found.")
        
        self.genai = None
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.genai = genai
            logger.info(f"LLM Client initialized for Gemini model: {self.model_name}")
        except ImportError:
            logger.critical("google-generativeai package not installed.")
            logger.critical("Please run: pip install google-generativeai")
        except Exception as e:
            logger.critical(f"Failed to initialize Gemini: {e}")

    def set_tools(self, tools: List[Dict[str, Any]]):
        """
        ツール定義を設定する。
        tools: [{"server": "meta_manager", "name": "create_mcp_server", "description": "...", "inputSchema": {...}}, ...]
        """
        self.tools = tools
        logger.debug(f"Set {len(tools)} tools for LLM client")

    def _sanitize_schema(self, schema: Any) -> Any:
        """Geminiがサポートしていないフィールド（defaultなど）をスキーマから削除する"""
        if isinstance(schema, dict):
            return {k: self._sanitize_schema(v) for k, v in schema.items() if k != "default"}
        elif isinstance(schema, list):
            return [self._sanitize_schema(v) for v in schema]
        else:
            return schema

    def _convert_tools_for_gemini(self) -> List[Dict]:
        """ツール定義をGemini形式に変換する"""
        function_declarations = []
        # マッピングをリセット
        self.gemini_tool_mapping = {}
        
        for tool in self.tools:
            # server.tool_name 形式でnameを構成
            # Gemini naming rules: 
            # - Must start with a letter or an underscore.
            # - Must contain only letters, numbers, and underscores.
            # - Max 63 characters.
            
            # 不正な文字を置換して安全な名前を生成
            safe_server = tool['server'].replace(".", "_").replace("-", "_").replace(" ", "_")
            safe_tool = tool['name'].replace(".", "_").replace("-", "_").replace(" ", "_")
            
            # マッピングキーとなる一意の名前
            full_name = f"{safe_server}__{safe_tool}"
            
            # マッピングを保存 (Gemini function name -> {server, name})
            self.gemini_tool_mapping[full_name] = {
                "server": tool['server'],
                "name": tool['name']
            }
            
            # inputSchemaからparametersを構築
            # GeminiはSchema定義内の 'default' フィールドをサポートしていないため削除
            schema = self._sanitize_schema(tool.get("inputSchema", {}))
            
            func_decl = {
                "name": full_name,
                "description": f"[{tool['server']}] {tool.get('description', '')}",
                "parameters": schema
            }
            function_declarations.append(func_decl)
        
        return function_declarations

    async def generate_response(self, prompt: str, images: List[Any] = None, messages: List[Dict] = None) -> Dict[str, Any]:
        """LLMにリクエストを送信し、レスポンスを取得する（自動リトライ付き）。"""
        if images is None:
            images = []
        max_retries = 3
        import asyncio
        for attempt in range(max_retries):
            try:
                return await self._request_gemini(prompt, images, messages)
            except (LLMError, json.JSONDecodeError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed after {max_retries} attempts. Last error: {e}")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                await asyncio.sleep(1)
        return None

    async def _request_gemini(self, prompt: str, images: List[Any], messages: List[Dict] = None) -> Dict[str, Any]:
        """Gemini APIリクエスト（ネイティブFunction Calling使用）"""
        if not self.genai:
            raise LLMError("Gemini is not initialized.")
        
        try:
            # ツール定義を準備
            tools_config = None
            if self.tools:
                function_declarations = self._convert_tools_for_gemini()
                tools_config = [{"function_declarations": function_declarations}]
            
            # モデルを初期化（ツール付き）
            model_config = {}
            if self.system_instruction:
                model_config["system_instruction"] = self.system_instruction
            
            model = self.genai.GenerativeModel(
                self.model_name,
                tools=tools_config,
                **model_config
            )
            
            # 履歴を構築（AgentStateからGemini形式で渡される）
            history = []
            if messages:
                for msg in messages:
                    # AgentStateから来るメッセージは既にGemini形式（role + parts）であることを期待
                    if "parts" in msg:
                        history.append(msg)
                    else:
                        # 万が一、旧形式が渡された場合の最小限のフォールバック
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        
                        if role == "assistant":
                            role = "model"
                        elif role == "tool":
                             # ここでも tool -> user 変換を入れておく (二重の安全策)
                            role = "user"
                            if isinstance(content, str):
                                content = f"Tool Output: {content}"
                                
                        parts = [content] if isinstance(content, str) else content
                        history.append({"role": role, "parts": parts})
            
            # チャットセッション開始
            chat = model.start_chat(history=history)
            
            # 現在のターンの入力
            inputs = [prompt] + images
            response = chat.send_message(inputs)
            
            # レスポンスを処理
            if not response.candidates:
                raise LLMError("レスポンスにcandidatesがありません。")
            
            candidate = response.candidates[0]
            # コンテンツが空で終了理由も不明な場合のガード
            if not candidate.content or not candidate.content.parts:
                finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else "UNKNOWN"
                # 安全策: thoughtもtool_callもない場合を考慮
                pass 
            
            # 結果オブジェクト初期化
            result = {"thought": ""}
            
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    # テキストパート
                    if hasattr(part, 'text') and part.text:
                        result["thought"] = part.text
                        self._log_raw_response(part.text)
                    
                    # Function Callパート
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        
                        server_name = "unknown"
                        tool_name = fc.name
                        args = dict(fc.args) if fc.args else {}

                        # マッピングから正式名称を検索
                        if fc.name in self.gemini_tool_mapping:
                            mapped = self.gemini_tool_mapping[fc.name]
                            server_name = mapped["server"]
                            tool_name = mapped["name"]
                        else:
                            # フォールバック (マッピングにない場合や古い形式への対応)
                            if "__" in fc.name:
                                parts_list = fc.name.split("__", 1)
                                server_name = parts_list[0]
                                tool_name = parts_list[1]
                            elif "_" in fc.name:
                                 parts_list = fc.name.split("_", 1)
                                 server_name = parts_list[0]
                                 tool_name = parts_list[1]
                        
                        result["tool_call"] = {
                            "server": server_name,
                            "name": tool_name,
                            "arguments": args
                        }
                        
                        self._log_raw_response(f"Function Call: {fc.name}, Args: {fc.args}")
            
            return result
            
        except LLMError:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise LLMError(f"Gemini APIエラー: {e}")

    def _log_raw_response(self, content: str):
        """デバッグ用に生のレスポンスをファイルに保存する。"""
        try:
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"response_{timestamp}.txt"
            filepath = os.path.join(log_dir, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(str(content))
                
            # Log Rotation
            files = sorted([
                os.path.join(log_dir, f) for f in os.listdir(log_dir) 
                if f.startswith("response_") and f.endswith(".txt")
            ])
            
            if len(files) > Config.MAX_LOG_FILES:
                files_to_delete = files[:len(files) - Config.MAX_LOG_FILES]
                for f in files_to_delete:
                    try:
                        os.remove(f)
                    except OSError as e:
                        logger.warning(f"Failed to delete old log {f}: {e}")

        except Exception as e:
            logger.error(f"Failed to log raw response: {e}")
