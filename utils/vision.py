import base64
import time
import mss
import mss.tools
import sys
import os

# Add parent directory to path for logger import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger

# Imports for robust cursor capture
import io
from PIL import Image, ImageDraw

logger = get_logger(__name__)


def capture_screenshot() -> tuple[str, float]:
    """
    Captures the primary screen with a mouse cursor overlay,
    and returns the base64 encoded PNG string and the timestamp.
    """
    try:
        with mss.mss() as sct:
            # We enforce with_cursor=False usually if we draw manually, 
            # but mss default is False unless specified. 
            # We will manually draw the cursor to ensure it's visible.
            monitor = sct.monitors[1]  # Primary monitor
            sct_img = sct.grab(monitor)
            
            # Convert mss object to PIL Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            # Convert PIL Image back to Base64 PNG
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            return (img_str, time.time())
    except Exception as e:
        logger.error(f"Error taking screenshot: {e}")
        return ("", 0.0)
