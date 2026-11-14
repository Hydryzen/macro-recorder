# Macro Recorder

A lightweight keyboard and mouse macro recorder and player for Windows, built with Python and Tkinter.

## Features

- Record keyboard and mouse actions.
- Replay recorded macros.
- Edit recorded events, including timing, coordinates, and keys.
- Save and load macros using JSON files.
- Emergency stop to interrupt playback.
- Support for multiple monitors and display scaling.

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

Recorded macros are saved as JSON files in the current working directory.
