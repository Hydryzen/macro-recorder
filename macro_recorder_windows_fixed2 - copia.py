import ctypes
import json
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
from pathlib import Path
from pynput import keyboard, mouse

# ---------- Windows SendInput ----------
user32 = ctypes.WinDLL("user32", use_last_error=True)
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


# Mantiene coherentes las coordenadas de pynput, Tkinter y Win32
# en pantallas con escalado DPI (125 %, 150 %, etc.).
def enable_dpi_awareness():
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # Per-monitor V2
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


enable_dpi_awareness()

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR)]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", INPUT_UNION)]


def send(inp):
    item = INPUT()
    item.type = inp[0]
    if inp[0] == INPUT_MOUSE:
        item.mi = inp[1]
    else:
        item.ki = inp[1]
    if user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


# Nombres de teclas especiales usados por pynput -> Virtual-Key de Windows.
VK = {
    "Key.backspace": 0x08, "Key.tab": 0x09, "Key.enter": 0x0D,
    "Key.shift": 0x10, "Key.shift_l": 0x10, "Key.shift_r": 0x10,
    "Key.ctrl": 0x11, "Key.ctrl_l": 0x11, "Key.ctrl_r": 0x11,
    "Key.alt": 0x12, "Key.alt_l": 0x12, "Key.alt_r": 0x12,
    "Key.alt_gr": 0xA5, "Key.pause": 0x13, "Key.caps_lock": 0x14,
    "Key.esc": 0x1B, "Key.space": 0x20, "Key.page_up": 0x21,
    "Key.page_down": 0x22, "Key.end": 0x23, "Key.home": 0x24,
    "Key.left": 0x25, "Key.up": 0x26, "Key.right": 0x27,
    "Key.down": 0x28, "Key.insert": 0x2D, "Key.delete": 0x2E,
    "Key.cmd": 0x5B, "Key.cmd_r": 0x5C, "Key.print_screen": 0x2C,
    "Key.num_lock": 0x90, "Key.scroll_lock": 0x91,
}
for n in range(1, 13):
    VK[f"Key.f{n}"] = 0x6F + n


def key_vk(name):
    if name.startswith("vk:"):
        return int(name[3:]), False
    if name in VK:
        return VK[name], False
    if len(name) == 1:
        value = user32.VkKeyScanW(ord(name))
        if value == -1:
            raise ValueError(f"Tecla no compatible: {name!r}")
        # VkKeyScanW codifica Shift/Ctrl/Alt en el byte alto.
        return value & 0xFF, bool((value >> 8) & 1)
    raise ValueError(f"Tecla no reconocida: {name}")


def key_event(name, down):
    vk, needs_shift = key_vk(name)

    if needs_shift:
        key_event("Key.shift", down)

    flags = 0 if down else KEYEVENTF_KEYUP
    send((INPUT_KEYBOARD, KEYBDINPUT(vk, 0, flags, 0, 0)))


def mouse_event(flags, x=0, y=0, data=0):
    send((INPUT_MOUSE, MOUSEINPUT(x, y, data, flags, 0, 0)))


# Métricas del escritorio virtual: contemplan monitores secundarios
# y coordenadas negativas cuando están a la izquierda o encima del principal.
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def screen_point(x, y):
    left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    if width <= 1 or height <= 1:
        raise RuntimeError("No se pudieron obtener las dimensiones de pantalla.")

    nx = round((x - left) * 65535 / (width - 1))
    ny = round((y - top) * 65535 / (height - 1))
    return max(0, min(65535, nx)), max(0, min(65535, ny))


def move_to_recorded_position(x, y):
    nx, ny = screen_point(x, y)
    mouse_event(
        MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
        nx, ny
    )


class MacroRecorder:
    def __init__(self, status):
        self.status = status
        self.events = []
        self.recording = False
        self.playing = False
        self.stop = threading.Event()
        self.started = 0
        self.mouse_listener = None
        self.key_listener = None
        self.last_move = None
        self.last_saved_path = None
        self.held_keys = set()
        self.held_buttons = set()

    def add(self, event):
        if self.recording:
            event["time"] = (time.perf_counter_ns() - self.started) / 1e9
            self.events.append(event)

    def start_recording(self):
        if self.recording or self.playing:
            return
        self.events = []
        self.started = time.perf_counter_ns()
        self.last_move = None
        self.recording = True
        self.mouse_listener = mouse.Listener(
            on_move=self.on_move, on_click=self.on_click, on_scroll=self.on_scroll)
        self.key_listener = keyboard.Listener(
            on_press=lambda k: self.on_key(k, True),
            on_release=lambda k: self.on_key(k, False))
        self.mouse_listener.start()
        self.key_listener.start()
        self.status("Grabando...")

    def on_move(self, x, y):
        # Descarta únicamente coordenadas repetidas; no impone un umbral de píxeles.
        point = (int(x), int(y))
        if point != self.last_move:
            self.last_move = point
            self.add({"type": "move", "x": point[0], "y": point[1]})

    def on_click(self, x, y, button, pressed):
        self.add({"type": "click", "x": int(x), "y": int(y),
                  "button": str(button).split(".")[-1], "pressed": pressed})

    def on_scroll(self, x, y, dx, dy):
        self.add({"type": "scroll", "x": int(x), "y": int(y),
                  "dx": int(dx), "dy": int(dy)})

    def on_key(self, key, down):
        if down and key == keyboard.Key.f2:
            self.stop_recording()
            return

        if isinstance(key, keyboard.KeyCode) and key.vk is not None:
            name = f"vk:{key.vk}"
        else:
            name = str(key)

        self.add({"type": "key_down" if down else "key_up", "key": name})

    def stop_recording(self):
        if not self.recording:
            return

        self.recording = False

        for listener in (self.mouse_listener, self.key_listener):
            if listener:
                listener.stop()

        if self.events:
            name = f"macro_{datetime.now():%Y%m%d_%H%M%S}.json"
            path = Path(name).resolve()

            path.write_text(
                json.dumps(self.events, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

            self.last_saved_path = str(path)
            self.status(
                f"Guardada: {path.name} ({len(self.events)} eventos)"
            )
        else:
            self.status("No se registraron eventos")

    def play(self, filename):
        if self.recording or self.playing:
            return

        try:
            events = json.loads(Path(filename).read_text(encoding="utf-8"))
        except Exception as exc:
            self.status(f"Error al leer macro: {exc}")
            return

        if not events:
            self.status("La macro está vacía")
            return

        self.playing = True
        self.stop.clear()
        self.status("Reproduciendo...")

        def worker():
            try:
                start = time.perf_counter()
                last_x = last_y = None

                for event in events:
                    if self.stop.is_set():
                        break

                    target = float(event.get("time", 0))
                    remaining = target - (time.perf_counter() - start)
                    if remaining > 0:
                        if self.stop.wait(remaining):
                            break

                    kind = event.get("type")

                    if kind == "move":
                        last_x, last_y = event["x"], event["y"]
                        move_to_recorded_position(last_x, last_y)

                    elif kind == "click":
                        last_x, last_y = event["x"], event["y"]
                        move_to_recorded_position(last_x, last_y)
                        button = event.get("button", "left")
                        pressed = event.get("pressed", True)
                        if button == "left":
                            flag = MOUSEEVENTF_LEFTDOWN if pressed else MOUSEEVENTF_LEFTUP
                        elif button == "right":
                            flag = MOUSEEVENTF_RIGHTDOWN if pressed else MOUSEEVENTF_RIGHTUP
                        else:
                            flag = MOUSEEVENTF_MIDDLEDOWN if pressed else MOUSEEVENTF_MIDDLEUP
                        mouse_event(flag)

                        if pressed:
                            up_flag = {
                                "left": MOUSEEVENTF_LEFTUP,
                                "right": MOUSEEVENTF_RIGHTUP,
                                "middle": MOUSEEVENTF_MIDDLEUP
                            }[button]
                            self.held_buttons.add((button, up_flag))
                        else:
                            self.held_buttons.discard((
                                button,
                                {
                                    "left": MOUSEEVENTF_LEFTUP,
                                    "right": MOUSEEVENTF_RIGHTUP,
                                    "middle": MOUSEEVENTF_MIDDLEUP
                                }[button]
                            ))

                    elif kind == "scroll":
                        last_x, last_y = event["x"], event["y"]
                        move_to_recorded_position(last_x, last_y)
                        dy = int(event.get("dy", 0))
                        dx = int(event.get("dx", 0))
                        if dy:
                            mouse_event(MOUSEEVENTF_WHEEL, data=dy * 120)
                        if dx:
                            mouse_event(MOUSEEVENTF_HWHEEL, data=dx * 120)

                    elif kind == "key_down":
                        key = event["key"]
                        key_event(key, True)
                        self.held_keys.add(key)

                    elif kind == "key_up":
                        key = event["key"]
                        key_event(key, False)
                        self.held_keys.discard(key)

            except Exception as exc:
                self.status(f"Error en reproducción: {exc}")
            finally:
                self.playing = False
                if not self.stop.is_set():
                    self.status("Reproducción finalizada")

        threading.Thread(target=worker, daemon=True).start()


    def emergency_stop(self):
        self.stop.set()

        for key in self.held_keys.copy():
            try:
                key_event(key, False)
            except Exception:
                pass

        for _, up_flag in self.held_buttons.copy():
            try:
                mouse_event(up_flag)
            except Exception:
                pass

        self.held_keys.clear()
        self.held_buttons.clear()
        self.status("Detenido")

class MacroEditor:
    def __init__(self, parent, filename):
        self.parent = parent
        self.path = Path(filename)
        self.events = json.loads(
            self.path.read_text(encoding="utf-8")
        )

        self.window = tk.Toplevel(parent)
        self.window.title("Editor de macros")
        self.window.geometry("850x480")
        self.window.minsize(700, 350)

        self.build_interface()
        self.refresh()

    def build_interface(self):
        tk.Label(
            self.window,
            text="Editor de eventos de la macro",
            font=("Arial", 13, "bold")
        ).pack(pady=10)

        frame = tk.Frame(self.window)
        frame.pack(fill="both", expand=True, padx=10)

        columns = ("number", "time", "type", "details")

        self.table = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            selectmode="browse"
        )

        self.table.heading("number", text="#")
        self.table.heading("time", text="Tiempo")
        self.table.heading("type", text="Acción")
        self.table.heading("details", text="Detalles")

        self.table.column("number", width=45)
        self.table.column("time", width=100)
        self.table.column("type", width=110)
        self.table.column("details", width=500)

        scrollbar = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=self.table.yview
        )

        self.table.configure(yscrollcommand=scrollbar.set)

        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.table.bind(
            "<Double-1>",
            lambda event: self.edit_event()
        )

        buttons = tk.Frame(self.window)
        buttons.pack(fill="x", padx=10, pady=10)

        tk.Button(
            buttons,
            text="Editar evento",
            command=self.edit_event
        ).pack(side="left", padx=3)

        tk.Button(
            buttons,
            text="Eliminar",
            command=self.delete_event
        ).pack(side="left", padx=3)

        tk.Button(
            buttons,
            text="Duplicar",
            command=self.duplicate_event
        ).pack(side="left", padx=3)

        tk.Button(
            buttons,
            text="- 0.1 s",
            command=lambda: self.adjust_time(-0.1)
        ).pack(side="left", padx=3)

        tk.Button(
            buttons,
            text="+ 0.1 s",
            command=lambda: self.adjust_time(0.1)
        ).pack(side="left", padx=3)

        bottom = tk.Frame(self.window)
        bottom.pack(fill="x", padx=10, pady=5)

        tk.Button(
            bottom,
            text="Guardar",
            command=self.save
        ).pack(side="right", padx=3)

        tk.Button(
            bottom,
            text="Guardar como...",
            command=self.save_as
        ).pack(side="right", padx=3)

        tk.Button(
            bottom,
            text="Guardar y reproducir",
            command=self.save_and_play
        ).pack(side="right", padx=3)

    def details(self, event):
        kind = event.get("type", "?")

        if kind == "move":
            return f"X={event.get('x')} Y={event.get('y')}"

        if kind == "click":
            return (
                f"{event.get('button')} | "
                f"Presionado={event.get('pressed')} | "
                f"X={event.get('x')} Y={event.get('y')}"
            )

        if kind == "scroll":
            return (
                f"X={event.get('x')} Y={event.get('y')} | "
                f"DX={event.get('dx')} DY={event.get('dy')}"
            )

        if kind.startswith("key_"):
            return f"Tecla={event.get('key')}"

        return str(event)

    def refresh(self, selected=None):
        for item in self.table.get_children():
            self.table.delete(item)

        for i, event in enumerate(self.events):
            self.table.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    i + 1,
                    f"{float(event.get('time', 0)):.4f}",
                    event.get("type", "?"),
                    self.details(event)
                )
            )

        if selected is not None and 0 <= selected < len(self.events):
            self.table.selection_set(str(selected))
            self.table.see(str(selected))

    def selected(self):
        selection = self.table.selection()
        return int(selection[0]) if selection else None

    def edit_event(self):
        index = self.selected()

        if index is None:
            messagebox.showinfo("Editor", "Selecciona un evento.")
            return

        event = self.events[index]

        dialog = tk.Toplevel(self.window)
        dialog.title("Editar evento")
        dialog.transient(self.window)
        dialog.grab_set()
        dialog.resizable(False, False)

        fields = ["time"]

        if event["type"] in ("move", "click", "scroll"):
            fields += ["x", "y"]

        if event["type"] == "click":
            fields += ["button", "pressed"]

        if event["type"] == "scroll":
            fields += ["dx", "dy"]

        if event["type"].startswith("key_"):
            fields += ["key"]

        variables = {}

        for row, field in enumerate(fields):
            tk.Label(
                dialog,
                text=field
            ).grid(row=row, column=0, padx=10, pady=5)

            value = event.get(field, "")

            if isinstance(value, bool):
                value = str(value).lower()

            var = tk.StringVar(value=str(value))
            variables[field] = var

            tk.Entry(
                dialog,
                textvariable=var,
                width=30
            ).grid(row=row, column=1, padx=10, pady=5)

        def apply():
            updated = dict(event)

            try:
                for field, var in variables.items():
                    value = var.get().strip()

                    if field == "time":
                        value = float(value)
                        if value < 0:
                            raise ValueError("El tiempo no puede ser negativo.")

                    elif field in ("x", "y", "dx", "dy"):
                        value = int(value)

                    elif field == "pressed":
                        if value.lower() not in ("true", "false"):
                            raise ValueError("Usa true o false.")
                        value = value.lower() == "true"

                    elif field == "button":
                        value = value.lower()
                        if value not in ("left", "right", "middle"):
                            raise ValueError("Botón no válido.")

                    elif field == "key":
                        if not value:
                            raise ValueError("La tecla no puede estar vacía.")

                    updated[field] = value

            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=dialog)
                return

            self.events[index] = updated
            self.sort_events()
            dialog.destroy()
            self.refresh()

        tk.Button(
            dialog,
            text="Aplicar cambios",
            command=apply
        ).grid(row=len(fields), column=0, columnspan=2, pady=10)

    def sort_events(self):
        self.events = [
            event for _, event in sorted(
                enumerate(self.events),
                key=lambda pair: (
                    float(pair[1].get("time", 0)),
                    pair[0]
                )
            )
        ]

    def delete_event(self):
        index = self.selected()

        if index is None:
            return

        if messagebox.askyesno(
            "Eliminar",
            "¿Quieres eliminar este evento?"
        ):
            del self.events[index]
            self.refresh()

    def duplicate_event(self):
        index = self.selected()

        if index is None:
            return

        duplicate = dict(self.events[index])
        duplicate["time"] = float(
            duplicate.get("time", 0)
        ) + 0.05

        self.events.insert(index + 1, duplicate)
        self.sort_events()
        self.refresh()

    def adjust_time(self, amount):
        index = self.selected()

        if index is None:
            return

        event = dict(self.events[index])

        event["time"] = max(
            0,
            float(event.get("time", 0)) + amount
        )

        self.events[index] = event
        self.sort_events()
        self.refresh()

    def save(self):
        try:
            self.sort_events()

            self.path.write_text(
                json.dumps(
                    self.events,
                    indent=2,
                    ensure_ascii=False
                ),
                encoding="utf-8"
            )

            return True

        except Exception as exc:
            messagebox.showerror(
                "Error al guardar",
                str(exc)
            )
            return False

    def save_as(self):
        filename = filedialog.asksaveasfilename(
            parent=self.window,
            defaultextension=".json",
            filetypes=[("Macros JSON", "*.json")]
        )

        if filename:
            old_path = self.path
            self.path = Path(filename)

            if self.save():
                self.window.title(
                    f"Editor de macros - {self.path.name}"
                )
            else:
                self.path = old_path

    def save_and_play(self):
        if self.save():
            self.parent.recorder.play(str(self.path))


class App:
    def __init__(self, root):
        self.root = root

        root.title("Macro Recorder - Windows")
        root.geometry("450x400")
        root.minsize(450, 400)

        self.label = tk.StringVar(value="Listo")
        self.recorder = MacroRecorder(self.set_status)

        tk.Label(
            root,
            textvariable=self.label,
            wraplength=390
        ).pack(pady=12)

        tk.Button(
            root,
            text="Iniciar grabación (F1)",
            command=self.recorder.start_recording
        ).pack(fill="x", padx=25, pady=4)

        tk.Button(
            root,
            text="Detener grabación (F2)",
            command=self.recorder.stop_recording
        ).pack(fill="x", padx=25, pady=4)

        tk.Button(
            root,
            text="Editar última grabación",
            command=self.edit_last
        ).pack(fill="x", padx=25, pady=4)

        tk.Button(
            root,
            text="Abrir macro para editar",
            command=self.open_editor
        ).pack(fill="x", padx=25, pady=4)

        tk.Button(
            root,
            text="Reproducir macro",
            command=self.open_macro
        ).pack(fill="x", padx=25, pady=4)

        tk.Button(
            root,
            text="Detener reproducción",
            command=self.recorder.emergency_stop
        ).pack(fill="x", padx=25, pady=4)

        root.bind(
            "<F1>",
            lambda event: self.recorder.start_recording()
        )

        root.bind(
            "<F2>",
            lambda event: self.recorder.stop_recording()
        )

        root.protocol("WM_DELETE_WINDOW", self.close)

    def set_status(self, message):
        self.root.after(0, self.label.set, message)

    def edit_last(self):
        path = self.recorder.last_saved_path

        if not path or not Path(path).exists():
            messagebox.showinfo(
                "Editor",
                "Primero debes realizar una grabación."
            )
            return

        MacroEditor(self.root, path)

    def open_editor(self):
        path = filedialog.askopenfilename(
            filetypes=[("Macros JSON", "*.json")]
        )

        if path:
            try:
                MacroEditor(self.root, path)
            except Exception as exc:
                messagebox.showerror("Error al abrir macro", str(exc))

    def open_macro(self):
        path = filedialog.askopenfilename(
            filetypes=[("Macros JSON", "*.json")]
        )

        if path:
            self.recorder.play(path)

    def close(self):
        self.recorder.emergency_stop()
        self.root.destroy()


if __name__ == "__main__":
    App(tk.Tk()).root.mainloop()