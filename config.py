import os
from dotenv import load_dotenv

# Load environment variables once
load_dotenv()

class Config:
    """Centralized configuration for the application."""
    
    # Core Settings
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
    API_KEY = os.getenv("API_KEY")
    
    # Service Specific Settings
    LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    
    # Model Selection Logic
    _GEMINI_MODEL_DEFAULT = "gemini-1.5-pro-002" # Updated to a more standard recent default or user's preference
    _GEMINI_MODEL = os.getenv("GEMINI_MODEL", _GEMINI_MODEL_DEFAULT)
    _LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")
    _GENERIC_MODEL = os.getenv("MODEL_NAME", _GEMINI_MODEL_DEFAULT)
    
    @property
    def MODEL_NAME(self):
        """Returns the appropriate model name based on the provider."""
        # Since this is a class property used as static config, we'll use a classmethod approach 
        # or just resolve it at class level if variables don't change at runtime.
        # For simplicity, let's resolve it at the class level.
        pass

    # Resolve MODEL_NAME statically for easy access
    if LLM_PROVIDER == "gemini":
        MODEL_NAME = _GEMINI_MODEL
    elif LLM_PROVIDER == "lmstudio":
        MODEL_NAME = _LM_STUDIO_MODEL
    else:
        MODEL_NAME = _GENERIC_MODEL
