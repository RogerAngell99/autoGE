import json
import time
import math
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pynput import mouse, keyboard
import logging
import os
from datetime import datetime
import configparser
import random
from collections import deque
import pygetwindow as gw

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EventSimulator:
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.current_event_index: int = 0
        self.is_simulating: bool = False
        self.mouse_controller: Optional[mouse.Controller] = None
        self.keyboard_controller: Optional[keyboard.Controller] = None
        self.config = self._load_config()
        
        # Movement tracking
        self.last_position: Optional[Tuple[int, int]] = None
        self.last_time: Optional[float] = None
        
        # Screen information
        self.screen_width = 0
        self.screen_height = 0
        self._initialize_screen_info()
        
        # Window focus tracking
        self.game_window_title = self.config.get('Window', 'game_title', fallback='RuneLite')
        self.last_focus_check = 0
        self.focus_check_interval = 0.1  # Check focus every 100ms
        
        # Hotkey tracking
        self.hotkey_listener: Optional[keyboard.Listener] = None
        
        # Pattern management
        self.patterns_dir = os.path.abspath(self.config.get('Paths', 'patterns_directory'))
        self.suggested_actions_file = os.path.abspath(self.config.get('Paths', 'suggested_actions'))
        self.last_action_check = 0
        self.action_check_interval = 0.1  # Check for new actions every 100ms
        self.pattern_cache = {}  # Cache for loaded patterns
        logger.info(f"Using absolute patterns directory: {self.patterns_dir}")

        # Initialize with most recent action
        self.current_action = self._get_most_recent_action()
        if self.current_action:
            self._load_pattern_for_action(self.current_action)

    def _initialize_screen_info(self) -> None:
        """Initialize screen information for movement scaling."""
        try:
            import pyautogui
            self.screen_width, self.screen_height = pyautogui.size()
        except Exception as e:
            logger.error(f"Failed to get screen size: {str(e)}")
            self.screen_width = 1920  # Default fallback
            self.screen_height = 1080

    def _load_config(self) -> configparser.ConfigParser:
        """Load configuration from config.ini."""
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.ini')
        config.read(config_path)
        return config

    def load_recording(self, filepath: str) -> bool:
        """Load a recording file and prepare it for simulation."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                self.events = data['events']
                self.current_event_index = 0
                logger.info(f"Loaded recording with {len(self.events)} events")
                return True
        except Exception as e:
            logger.error(f"Failed to load recording: {str(e)}")
            return False

    def _is_game_window_focused(self) -> bool:
        """Check if the game window is currently focused."""
        current_time = time.time()
        if current_time - self.last_focus_check < self.focus_check_interval:
            return True  # Return cached result if not enough time has passed
            
        self.last_focus_check = current_time
        try:
            active_window = gw.getActiveWindow()
            return active_window and self.game_window_title in active_window.title
        except Exception as e:
            logger.error(f"Error checking window focus: {str(e)}")
            return False

    def _simulate_mouse_move(self, event: Dict[str, Any]) -> None:
        """Simulate a mouse movement event with exact path replication."""
        if not self._is_game_window_focused():
            logger.warning("Game window not focused, skipping mouse movement")
            return
            
        if not self.mouse_controller:
            self.mouse_controller = mouse.Controller()
        
        # Get current position
        current_pos = self.mouse_controller.position
        target_pos = (event['x'], event['y'])
        
        # Calculate time to wait based on the event's time offset
        if self.last_time is not None:
            time_to_wait = (event['time_offset_ms'] - self.last_time) / 1000.0
            if time_to_wait > 0:
                time.sleep(time_to_wait)
        
        # If we have movement metrics, replicate the exact movement
        if 'movement_metrics' in event and event['movement_metrics']:
            metrics = event['movement_metrics']
            
            # Calculate number of steps based on distance and speed
            distance = metrics['distance']
            speed = metrics['speed']
            dt = metrics['dt']
            
            if distance > 0 and speed > 0:
                # Calculate number of steps to make movement smooth
                num_steps = max(1, int(distance / 2))  # One step every 2 pixels
                step_time = dt / num_steps
                
                # Move in small steps to replicate the exact path
                for i in range(num_steps):
                    # Calculate intermediate position
                    progress = (i + 1) / num_steps
                    dx = metrics['dx'] * progress
                    dy = metrics['dy'] * progress
                    
                    # Move to intermediate position
                    intermediate_pos = (
                        current_pos[0] + dx,
                        current_pos[1] + dy
                    )
                    self.mouse_controller.position = intermediate_pos
                    
                    # Wait for the exact time between steps
                    time.sleep(step_time)
        
        # Ensure we end up at the exact target position
        self.mouse_controller.position = target_pos
        self.last_position = target_pos
        self.last_time = event['time_offset_ms']

    def _simulate_mouse_click(self, event: Dict[str, Any]) -> None:
        """Simulate a mouse click event with precise timing."""
        if not self._is_game_window_focused():
            logger.warning("Game window not focused, skipping mouse click")
            return
            
        if not self.mouse_controller:
            self.mouse_controller = mouse.Controller()
        
        # Move to click position first
        self._simulate_mouse_move(event)
        
        # Get button from event
        button_str = event['button']
        button = mouse.Button.left if 'left' in button_str.lower() else mouse.Button.right
        
        if event['type'] == 'mouse_click_press':
            self.mouse_controller.press(button)
        else:  # mouse_click_release
            # Use exact recorded hold duration
            hold_duration = event.get('hold_duration_ms', 100) / 1000.0
            time.sleep(hold_duration)
            self.mouse_controller.release(button)

    def _simulate_key_press(self, event: Dict[str, Any]) -> None:
        """Simulate a keyboard press event with precise timing."""
        if not self._is_game_window_focused():
            logger.warning("Game window not focused, skipping key press")
            return
            
        if not self.keyboard_controller:
            self.keyboard_controller = keyboard.Controller()
        
        # Convert key string to Key object
        key_str = event['key']
        try:
            key = keyboard.Key[key_str]
        except KeyError:
            key = keyboard.KeyCode.from_char(key_str)
        
        if event['type'] == 'key_press':
            self.keyboard_controller.press(key)
        else:  # key_release
            # Use exact recorded hold duration
            hold_duration = event.get('hold_duration_ms', 100) / 1000.0
            time.sleep(hold_duration)
            self.keyboard_controller.release(key)

    def _simulate_pause(self, event: Dict[str, Any]) -> None:
        """Simulate a pause event with precise timing."""
        duration = event['duration_ms'] / 1000.0  # Convert to seconds
        time.sleep(duration)

    def start_simulation(self) -> None:
        """Start simulating the loaded recording with precise accuracy."""
        if not self.events:
            logger.warning("No events loaded for simulation")
            return
        
        if not self._is_game_window_focused():
            logger.warning("Game window not focused, cannot start simulation")
            return
            
        self.is_simulating = True
        self.current_event_index = 0
        self.mouse_controller = mouse.Controller()
        self.keyboard_controller = keyboard.Controller()
        self.last_time = None  # Reset last time at start
        
        logger.info("Starting simulation")
        
        try:
            while self.is_simulating and self.current_event_index < len(self.events):
                if not self._is_game_window_focused():
                    logger.warning("Game window lost focus, pausing simulation")
                    time.sleep(0.1)  # Wait a bit before checking again
                    continue
                    
                event = self.events[self.current_event_index]
                
                # Simulate based on event type
                if event['type'] == 'mouse_move':
                    self._simulate_mouse_move(event)
                elif event['type'] in ['mouse_click_press', 'mouse_click_release']:
                    self._simulate_mouse_click(event)
                elif event['type'] in ['key_press', 'key_release']:
                    self._simulate_key_press(event)
                elif event['type'] == 'pause':
                    self._simulate_pause(event)
                
                self.current_event_index += 1
                
        except Exception as e:
            logger.error(f"Error during simulation: {str(e)}")
        finally:
            self.is_simulating = False
            logger.info("Simulation stopped")

    def stop_simulation(self) -> None:
        """Stop the current simulation."""
        self.is_simulating = False
        logger.info("Stopped simulation")

    def _on_hotkey(self, key: keyboard.Key) -> None:
        """Handle hotkey presses."""
        if key == keyboard.Key.f2 and not self.is_simulating:
            logger.info("F2 pressed - Starting simulation")
            self.start_simulation()
        elif key == keyboard.Key.f3 and self.is_simulating:
            logger.info("F3 pressed - Stopping simulation")
            self.stop_simulation()

    def _parse_action(self, action_line: str) -> Tuple[str, Optional[int]]:
        """Parse an action line from suggested_actions.txt.
        Returns (action_type, box_id) where box_id is None for actions that don't need it."""
        try:
            # Remove timestamp if present
            if " - " in action_line:
                action_line = action_line.split(" - ")[1]
            
            # Remove trailing period if present
            action_line = action_line.rstrip('.')
            
            # Parse box_id if present
            box_id = None
            if '[' in action_line and ']' in action_line:
                action_type = action_line[:action_line.find('[')].strip()
                box_id = int(action_line[action_line.find('[')+1:action_line.find(']')])
            else:
                action_type = action_line.strip()
            
            return action_type, box_id
        except Exception as e:
            logger.error(f"Error parsing action line: {action_line} - {str(e)}")
            return None, None

    def _get_pattern_file(self, action_type: str, box_id: Optional[int] = None) -> Optional[str]:
        """Get the pattern file for a given action type and box ID."""
        try:
            # List all pattern files
            pattern_files = [f for f in os.listdir(self.patterns_dir) if f.endswith('.json')]
            logger.info(f"Found {len(pattern_files)} pattern files in {self.patterns_dir}")
            
            # Filter for matching action type
            matching_files = [f for f in pattern_files if f.startswith(f"{action_type}_")]
            logger.info(f"Found {len(matching_files)} files matching action type: {action_type}")
            
            if not matching_files:
                logger.warning(f"No pattern files found for action type: {action_type}")
                return None
                
            # Get the most recent file
            latest_file = max(matching_files, key=lambda x: os.path.getctime(os.path.join(self.patterns_dir, x)))
            filepath = os.path.join(self.patterns_dir, latest_file)
            logger.info(f"Selected pattern file: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error getting pattern file: {str(e)}")
            logger.error(f"Error details: {type(e).__name__}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _check_for_new_action(self) -> None:
        """Check if there's a new action to simulate."""
        current_time = time.time()
        if current_time - self.last_action_check < self.action_check_interval:
            return
            
        self.last_action_check = current_time
        
        try:
            if os.path.exists(self.suggested_actions_file):
                with open(self.suggested_actions_file, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        action_line = lines[0].strip()
                        action_type, box_id = self._parse_action(action_line)
                        
                        if action_type:
                            # Get pattern file
                            pattern_file = self._get_pattern_file(action_type, box_id)
                            
                            if pattern_file:
                                # Load and simulate the pattern
                                if self.load_recording(pattern_file):
                                    logger.info(f"Starting simulation for {action_type}" + 
                                              (f" in box {box_id}" if box_id is not None else "") +
                                              f" using pattern: {os.path.basename(pattern_file)}")
                                    self.start_simulation()
                                else:
                                    logger.error(f"Failed to load pattern for {action_type}")
                            else:
                                logger.error(f"No pattern found for {action_type}" + 
                                           (f" in box {box_id}" if box_id is not None else ""))
                            
                            # Remove the action from the file
                            with open(self.suggested_actions_file, 'w') as f:
                                f.writelines(lines[1:])
        except Exception as e:
            logger.error(f"Error checking for new actions: {str(e)}")

    def run(self) -> None:
        """Run the simulator with hotkey support."""
        logger.info("Simulator started. Press F2 to start simulation, F3 to stop.")
        
        # Start hotkey listener
        self.hotkey_listener = keyboard.Listener(on_press=self._on_hotkey)
        self.hotkey_listener.start()
        
        try:
            # Keep the main thread alive and check for new actions
            while True:
                if not self.is_simulating:
                    self._check_for_new_action()
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Simulator stopped by user")
        finally:
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            if self.is_simulating:
                self.stop_simulation()

    def _get_most_recent_action(self) -> Optional[str]:
        """Get the most recent action from the suggested_actions.txt file."""
        try:
            if os.path.exists(self.suggested_actions_file):
                with open(self.suggested_actions_file, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        action = lines[0].strip()
                        logger.info(f"Found most recent action: {action}")
                        return action
            logger.info("No actions found in suggested_actions.txt")
            return None
        except Exception as e:
            logger.error(f"Error reading suggested_actions.txt: {str(e)}")
            return None

    def _load_pattern_for_action(self, action: str) -> bool:
        """Load the pattern file for a given action."""
        try:
            action_type, box_id = self._parse_action(action)
            if action_type:
                pattern_file = self._get_pattern_file(action_type, box_id)
                if pattern_file:
                    return self.load_recording(pattern_file)
            return False
        except Exception as e:
            logger.error(f"Error loading pattern for action {action}: {str(e)}")
            return False

if __name__ == "__main__":
    # Run the simulator with hotkey support
    simulator = EventSimulator()
    simulator.run()
