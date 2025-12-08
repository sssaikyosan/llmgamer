import base64
import time
import io
import mss
import mss.tools
from PIL import Image, ImageDraw



def capture_screenshot() -> tuple[str, float]:
    """
    Captures the primary screen without any overlay,
    and returns the base64 encoded PNG string and the timestamp.
    """
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            png_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
            img_str = base64.b64encode(png_bytes).decode('utf-8')
            return (img_str, time.time())
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return ("", 0.0)
