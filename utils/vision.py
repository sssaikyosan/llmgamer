import base64
import time
import mss
import mss.tools
import sys
import os

# Add parent directory to path for logger import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger

logger = get_logger(__name__)


def capture_screenshot() -> tuple[str, float]:
    """
    Captures the primary screen with a mouse cursor overlay,
    and returns the base64 encoded PNG string and the timestamp.
    """
    try:
        with mss.mss(with_cursor=True) as sct:
            monitor = sct.monitors[1]  # Primary monitor
            sct_img = sct.grab(monitor)
            
            png_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
            img_str = base64.b64encode(png_bytes).decode('utf-8')
            
            return (img_str, time.time())
    except Exception as e:
        logger.error(f"Error taking screenshot: {e}")
        return ("", 0.0)
