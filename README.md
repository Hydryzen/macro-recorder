# Macro Recorder

A lightweight keyboard and mouse macro recorder and player for Windows, built with Python and Tkinter.

## Features

- Record keyboard and mouse actions.
- Replay recorded macros with accurate event timing.
- Configure a specific number of playback repetitions.
- Run macros in an infinite loop.
- Edit recorded events, including timing, coordinates, buttons, and keys.
- Duplicate and delete recorded events.
- Save and load macros using JSON files.
- Emergency stop using a global keyboard shortcut.
- Support for multiple monitors and different display scaling settings.
- Minimize the main application window before playback.

## Requirements

- Windows
- Python 3.10 or later
- `pynput`

## Installation

Clone the repository:

```bash
git clone https://github.com/Hydryzen/macro-recorder.git
cd macro-recorder
```

Install the required dependency:

```bash
pip install pynput
```

## Usage

Run the application:

```bash
python main.py
```

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `F1` | Start recording |
| `F2` | Stop recording |
| `Ctrl + Alt + Esc` | Emergency stop playback |

### Playback options

- **Specified repetitions:** Set how many times a macro should be executed.
- **Infinite loop:** Repeat the macro continuously until the emergency stop shortcut is pressed.

### Macro editor

The built-in editor allows you to:

- Modify individual events.
- Adjust event timing.
- Change mouse coordinates and keyboard inputs.
- Duplicate or delete events.
- Save changes or create a separate JSON file.

Recorded macros are saved as JSON files in the current working directory.
