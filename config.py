import os
from dotenv import load_dotenv

# Load environment variables once
load_dotenv()

class Config:
    """Centralized configuration for the application."""
    
    # Core Settings
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
    API_KEY = os.getenv("API_KEY")

    MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))
    
    # Service Specific Settings
    LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    
    # Model Selection Logic
    _GEMINI_MODEL_DEFAULT = "gemini-3-pro-preview" # Updated to a more standard recent default or user's preference
    _GEMINI_MODEL = os.getenv("GEMINI_MODEL", _GEMINI_MODEL_DEFAULT)
    _LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")
    
    @classmethod
    def get_model_name(cls) -> str:
        """動的にモデル名を取得。LLM_PROVIDERに基づいて適切なモデルを返す。"""
        if cls.LLM_PROVIDER == "gemini":
            return cls._GEMINI_MODEL
        elif cls.LLM_PROVIDER == "lmstudio":
            return cls._LM_STUDIO_MODEL
        # Fallback for unknown providers
        return cls._GEMINI_MODEL
    
    # 後方互換性のためのプロパティ（非推奨）
    MODEL_NAME = _GEMINI_MODEL  # デフォルト値、get_model_name()の使用を推奨
    
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
    ]
