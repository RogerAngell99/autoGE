import pygetwindow as gw
import time
import logging
from typing import Optional, List
import configparser
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config() -> configparser.ConfigParser:
    """Load configuration from config.ini."""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
    config.read(config_path)
    return config

def find_runelite_window() -> Optional[gw.Window]:
    """
    Find the RuneLite window by searching for windows containing 'RuneLite' in their title.
    Returns the first matching window or None if not found.
    """
    config = load_config()
    game_title = config.get('Window', 'game_title')
    timeout = config.getint('Window', 'window_search_timeout')
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Get all windows
            windows = gw.getAllWindows()
            
            # Filter windows containing 'RuneLite' in their title
            runelite_windows = [w for w in windows if game_title.lower() in w.title.lower()]
            
            if runelite_windows:
                logger.info(f"Found RuneLite window: {runelite_windows[0].title}")
                return runelite_windows[0]
            
            logger.debug("RuneLite window not found, retrying...")
            time.sleep(0.5)  # Wait before retrying
            
        except Exception as e:
            logger.error(f"Error while searching for RuneLite window: {str(e)}")
            return None
    
    logger.warning(f"RuneLite window not found after {timeout} seconds")
    return None

def activate_runelite_window() -> bool:
    """
    Find and activate the RuneLite window.
    Returns True if successful, False otherwise.
    """
    window = find_runelite_window()
    if window:
        try:
            window.activate()
            logger.info("Successfully activated RuneLite window")
            return True
        except Exception as e:
            logger.error(f"Failed to activate RuneLite window: {str(e)}")
            return False
    return False

def get_window_position() -> Optional[tuple]:
    """
    Get the position and size of the RuneLite window.
    Returns a tuple of (left, top, width, height) or None if window not found.
    """
    window = find_runelite_window()
    if window:
        return (window.left, window.top, window.width, window.height)
    return None

def is_window_active() -> bool:
    """
    Check if the RuneLite window is currently active.
    Returns True if active, False otherwise.
    """
    window = find_runelite_window()
    if window:
        return window.isActive
    return False

def get_all_runelite_windows() -> List[gw.Window]:
    """
    Get all windows containing 'RuneLite' in their title.
    Returns a list of matching windows.
    """
    config = load_config()
    game_title = config.get('Window', 'game_title')
    
    try:
        windows = gw.getAllWindows()
        return [w for w in windows if game_title.lower() in w.title.lower()]
    except Exception as e:
        logger.error(f"Error while getting RuneLite windows: {str(e)}")
        return []

if __name__ == "__main__":
    # Test the window detection
    window = find_runelite_window()
    if window:
        print(f"Found RuneLite window: {window.title}")
        print(f"Position: {window.left}, {window.top}")
        print(f"Size: {window.width}x{window.height}")
    else:
        print("RuneLite window not found")
