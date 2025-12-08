import os
from dotenv import load_dotenv

# Load environment variables once
load_dotenv()

class Config:
    """Centralized configuration for the application."""
    
    # Core Settings
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
    API_KEY = os.getenv("API_KEY")
    GEMINI_RPM = int(os.getenv("GEMINI_RPM", "10"))
    GEMINI_RPD = int(os.getenv("GEMINI_RPD", "250"))
    MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))
    
    # Service Specific Settings
    LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    
    # Model Selection Logic
    _GEMINI_MODEL_DEFAULT = "gemini-3-pro-preview" # Updated to a more standard recent default or user's preference
    _GEMINI_MODEL = os.getenv("GEMINI_MODEL", _GEMINI_MODEL_DEFAULT)
    _LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")
    
    # Resolve MODEL_NAME statically for easy access
    if LLM_PROVIDER == "gemini":
        MODEL_NAME = _GEMINI_MODEL
    elif LLM_PROVIDER == "lmstudio":
        MODEL_NAME = _LM_STUDIO_MODEL
    else:
        # Fallback for unknown providers
        MODEL_NAME = _GEMINI_MODEL
    
    # MCP サーバーで使用可能なライブラリリスト
    # 標準ライブラリ (time, re, json, ctypes等) は常に使用可能
    # 以下はサードパーティライブラリ
    ALLOWED_LIBRARIES = [
        # === 画面キャプチャ ===
        "mss",           # 高速スクリーンキャプチャ
        
        # === 入力操作 ===
        "pyautogui",     # マウス・キーボード操作
        "pydirectinput", # DirectInput操作（ゲーム向け）
        
        # === 画像処理 ===
        "pillow",        # 画像処理 (PIL)
        "cv2",           # OpenCV（テンプレートマッチング等）
        "numpy",         # 数値計算（cv2と併用）
        
        # === OCR ===
        "easyocr",       # OCR文字認識
        
        # === ウィンドウ・システム ===
        "pygetwindow",   # ウィンドウ操作
        "psutil",        # システム情報・プロセス監視
        "pyperclip",     # クリップボード操作
        
        # === Windows専用 ===
        "pywin32",       # Windows API (win32gui, win32api等)
    ]
