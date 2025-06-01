# RuneScape Grand Exchange Automation

A framework for recording and simulating user interactions in RuneScape's Grand Exchange interface. This project captures human-generated input patterns and replicates them in a manner that emulates natural human behavior.

## Features

- Record mouse movements, clicks, and keyboard inputs
- Simulate recorded actions with human-like variations
- Hotkey controls for pause/resume functionality
- Window targeting and focus management
- Configurable timing and movement patterns
- Extensible pattern storage and analysis

## Prerequisites

- Python 3.8 or higher
- RuneScape client installed
- Windows operating system

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/runescape_ge_automation.git
cd runescape_ge_automation
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
.\venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure the application:
   - Copy `config.ini.example` to `config.ini`
   - Update the paths and settings in `config.ini` to match your system

## Usage

1. Start the application:
```bash
python main.py
```

2. Control the application:
   - Use `<Control>+<Alt>+P` to pause/resume recording or simulation
   - Add commands to `suggested_actions.txt` to trigger recording or simulation

3. Recording a new pattern:
   - Add a new command to `suggested_actions.txt`
   - The application will enter recording mode
   - Perform the desired actions
   - Press `<Control>+<Alt>+P` to stop recording

4. Simulating a pattern:
   - Add a command to `suggested_actions.txt` that matches a recorded pattern
   - The application will automatically simulate the recorded actions

## Project Structure

```
runescape_ge_automation/
├── main.py              # Main application entry point
├── config.ini           # Configuration settings
├── core/               # Core functionality
│   ├── command_parser.py
│   ├── recorder.py
│   ├── simulator.py
│   ├── state_manager.py
│   └── hotkey_manager.py
├── patterns/           # Stored action patterns
├── utils/             # Utility functions
│   └── window_utils.py
├── tests/             # Test files
└── requirements.txt    # Project dependencies
```

## Development

1. Set up development environment:
```bash
pip install -r requirements-dev.txt
```

2. Run tests:
```bash
python -m pytest tests/
```

3. Code style:
```bash
black .
flake8
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for educational purposes only. Use at your own risk and in accordance with RuneScape's terms of service.
