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
try:
    import win32gui
    import win32api
except ImportError:
    win32gui = None
    win32api = None

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
            
            # Draw Cursor Manually
            if win32gui and win32api:
                try:
                    flags, hcursor, (x, y) = win32gui.GetCursorInfo()
                    
                    # Calculate relative position on the captured monitor
                    rel_x = x - monitor["left"]
                    rel_y = y - monitor["top"]
                    
                    # Check if cursor is within the monitor bounds
                    if 0 <= rel_x < img.width and 0 <= rel_y < img.height:
                        draw = ImageDraw.Draw(img)
                        
                        # Draw a cursor arrow for better visibility and realism
                        # Cursor shape points relative to (rel_x, rel_y)
                        # Standard pointer shape
                        cursor_points = [
                            (rel_x, rel_y),                # Tip
                            (rel_x, rel_y + 16),           # Bottom Left
                            (rel_x + 5, rel_y + 11),       # Stem indent
                            (rel_x + 11, rel_y + 11)       # Right wing
                        ]
                        
                        # Draw outline (Black for contrast)
                        draw.polygon(cursor_points, outline="black", fill="white")
                        
                        # Optional: Draw a secondary outline or larger shape if visibility is key
                        # But simple black arrow with white outline is standard and visible on any background
                except Exception as cursor_err:
                    # Just verify checking, don't spam logs for every frame
                    pass # Cursor might be unavailable or locked

            # Convert PIL Image back to Base64 PNG
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            return (img_str, time.time())
    except Exception as e:
        logger.error(f"Error taking screenshot: {e}")
        return ("", 0.0)
