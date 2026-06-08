"""
platform_compat.py — MCopy
Capa de compatibilidad multiplataforma para clipboard de texto y rutas.
"""

import os
import sys
import platform
import subprocess

_OS = platform.system()   # "Windows" | "Darwin" | "Linux"


# ══════════════════════════════════════════════════════════════════════════════
# Directorios
# ══════════════════════════════════════════════════════════════════════════════

def get_appdata_dir() -> str:
    if _OS == "Windows":
        return os.path.expandvars("%APPDATA%")
    elif _OS == "Darwin":
        return os.path.expanduser("~/Library/Application Support")
    else:
        return os.path.expanduser("~/.local/share")


# ══════════════════════════════════════════════════════════════════════════════
# Rutas de DaVinci Resolve
# ══════════════════════════════════════════════════════════════════════════════

def get_resolve_module_paths() -> list:
    if _OS == "Windows":
        return [
            r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
            r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting\Modules",
        ]
    elif _OS == "Darwin":
        return [
            "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
            os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"),
        ]
    else:
        return [
            "/opt/resolve/Developer/Scripting/Modules",
            "/opt/DaVinci_Resolve/Developer/Scripting/Modules",
            os.path.expanduser("~/.local/share/DaVinciResolve/Developer/Scripting/Modules"),
        ]


# ══════════════════════════════════════════════════════════════════════════════
# Portapapeles — leer texto
# ══════════════════════════════════════════════════════════════════════════════

def clipboard_get_text():
    """Lee el portapapeles como texto. Devuelve str o None si falla."""
    try:
        if _OS == "Windows":
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                        return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    return None
                finally:
                    win32clipboard.CloseClipboard()
            except ImportError:
                # Fallback via tkinter si pywin32 no está instalado
                try:
                    import tkinter as tk
                    root = tk.Tk()
                    root.withdraw()
                    text = root.clipboard_get()
                    root.destroy()
                    return text
                except Exception:
                    return None

        elif _OS == "Darwin":
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return r.stdout if r.returncode == 0 else None

        else:  # Linux
            for cmd in [
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"],
            ]:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
                    if r.returncode == 0:
                        return r.stdout
                except Exception:
                    continue
            return None

    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Portapapeles — escribir texto
# ══════════════════════════════════════════════════════════════════════════════

def clipboard_set_text(text: str) -> bool:
    """Escribe texto en el portapapeles. Devuelve True si tuvo éxito."""
    try:
        if _OS == "Windows":
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
                    return True
                finally:
                    win32clipboard.CloseClipboard()
            except ImportError:
                try:
                    import tkinter as tk
                    root = tk.Tk()
                    root.withdraw()
                    root.clipboard_clear()
                    root.clipboard_append(text)
                    root.update()
                    # Mantener el root vivo brevemente para que el clipboard persista
                    root.after(8000, root.destroy)
                    root.mainloop()
                    return True
                except Exception:
                    return False

        elif _OS == "Darwin":
            r = subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
            return r.returncode == 0

        else:  # Linux
            for cmd in [
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ]:
                try:
                    r = subprocess.run(cmd, input=text, text=True, timeout=4)
                    if r.returncode == 0:
                        return True
                except Exception:
                    continue
            return False

    except Exception:
        return False
