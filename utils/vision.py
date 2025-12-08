import base64
import time
import io
import mss
import mss.tools
from PIL import Image, ImageDraw

def capture_screenshot() -> tuple[str, float]:
    """
    Captures the primary screen with a mouse cursor overlay,
    and returns the base64 encoded PNG string and the timestamp.
    """
    try:
        # Initialize mss with cursor capture enabled
        with mss.mss(with_cursor=True) as sct:
            # Primary monitor
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            
            # Create PIL Image from mss data
            # mss returns BGRA, convert to RGB for PIL
            # Note: We can also just use mss.tools.to_png if we don't need PIL manipulation
            # But let's keep PIL object creation if we want to add things later, 
            # or just go straight to bytes if efficient. 
            # Existing code used mss.tools.to_png effectively before I added PIL.
            
            # Efficient way (same as original):
            png_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
            img_str = base64.b64encode(png_bytes).decode('utf-8')
            
            return (img_str, time.time())
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return ("", 0.0)
