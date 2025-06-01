import os
import sys
import configparser
import pytest

def test_python_version():
    """Test that Python version is 3.8 or higher."""
    assert sys.version_info >= (3, 8), "Python 3.8 or higher is required"

def test_required_packages():
    """Test that all required packages are installed."""
    import pynput
    import pyautogui
    import pygetwindow
    import numpy
    
    assert pynput.__version__ >= "1.7.6"
    assert pyautogui.__version__ >= "0.9.53"
    assert pygetwindow.__version__ >= "0.0.9"
    assert numpy.__version__ >= "1.21.0"

def test_config_file():
    """Test that config.ini exists and has required sections."""
    assert os.path.exists("config.ini"), "config.ini file not found"
    
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    required_sections = ["Paths", "Hotkeys", "Simulation", "Window", "Logging"]
    for section in required_sections:
        assert section in config.sections(), f"Missing section: {section}"

def test_directory_structure():
    """Test that required directories exist."""
    required_dirs = ["core", "utils", "patterns", "tests", "logs"]
    for dir_name in required_dirs:
        assert os.path.exists(dir_name), f"Missing directory: {dir_name}"

if __name__ == "__main__":
    pytest.main([__file__]) 