import os
from dotenv import load_dotenv

# Load environment variables once
load_dotenv()

class Config:
    """Centralized configuration for the application."""
    
    # === LLM Provider Selection ===
    # Supported: "gemini", "claude"
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
    
    # === API Keys (Provider-specific) ===
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

    MAX_HISTORY = int(os.getenv("MAX_HISTORY", "5"))
    MAX_LOG_FILES = int(os.getenv("MAX_LOG_FILES", "100"))
    
    # Language Settings
    AI_LANGUAGE = os.getenv("AI_LANGUAGE", "English")
    
    # === Model Selection ===
    # Gemini Models
    _GEMINI_MODEL_DEFAULT = "gemini-2.0-flash-exp"
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", _GEMINI_MODEL_DEFAULT)
    
    # Claude Models
    _CLAUDE_MODEL_DEFAULT = "claude-sonnet-4-20250514"
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", _CLAUDE_MODEL_DEFAULT)
    
    @classmethod
    def get_model_name(cls) -> str:
        """動的にモデル名を取得。現在のプロバイダーに応じたモデルを返す。"""
        if cls.LLM_PROVIDER == "claude":
            return cls.CLAUDE_MODEL
        return cls.GEMINI_MODEL
    
    @classmethod
    def get_api_key(cls) -> str:
        """動的にAPIキーを取得。現在のプロバイダーに応じたキーを返す。"""
        if cls.LLM_PROVIDER == "claude":
            return cls.CLAUDE_API_KEY
        return cls.GEMINI_API_KEY
    
    # MCP サーバーで使用可能なライブラリリスト
    # 標準ライブラリ (time, re, json, ctypes等) は常に使用可能
    # 以下はサードパーティライブラリ (pip名: import名)
    ALLOWED_LIBRARIES = [
        # === 画面キャプチャ ===
        "mss",           # 高速スクリーンキャプチャ (import mss)
        
        # === 入力操作 ===
        "pyautogui",     # マウス・キーボード操作 (import pyautogui)
        "pydirectinput", # DirectInput操作（ゲーム向け） (import pydirectinput)
        
        # === 画像処理 ===
        "pillow",        # 画像処理 (pip: pillow → import PIL)
        "cv2",           # OpenCV (pip: opencv-python → import cv2)
        "numpy",         # 数値計算 (import numpy)
        
        # === OCR ===
        "easyocr",       # OCR文字認識 (import easyocr)
        
        # === ウィンドウ・システム ===
        "pygetwindow",   # ウィンドウ操作 (import pygetwindow)
        "psutil",        # システム情報・プロセス監視 (import psutil)
        "pyperclip",     # クリップボード操作 (import pyperclip)
        
        # === Windows専用 ===
        "pywin32",       # Windows API (pip: pywin32 → import win32gui, win32api, etc.)
        
        # === 文字列処理 ===
        "thefuzz",       # ファジーマッチング (import thefuzz)
        
        # === MCP Helper ===
        "fastmcp",       # FastMCP framework
    ]
