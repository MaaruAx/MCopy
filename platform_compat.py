"""
platform_compat.py - MCopy
Cross-platform compatibility layer: clipboard access, app data paths,
and the DaVinci Resolve / Fusion scripting bridge (Scripting mode).
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("mcopy.platform")

# platform.system() returns the kernel name, not the marketing name -- on
# macOS this is literally the string "Darwin". Every internal comparison
# below has to keep checking for "Darwin" for that reason; _PLATFORM_LABELS
# only exists so logs and any user-facing text can say "macOS" instead.
_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

_PLATFORM_LABELS = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}


def os_label() -> str:
    """Human-readable platform name for logs/UI ('macOS', not 'Darwin')."""
    return _PLATFORM_LABELS.get(_OS, _OS)


_IS_WINDOWS = _OS == "Windows"
_IS_MACOS = _OS == "Darwin"
_IS_LINUX = _OS == "Linux"


# ══════════════════════════════════════════════════════════════════════════════
# App data directory
# ══════════════════════════════════════════════════════════════════════════════

def get_appdata_dir() -> Path:
    if _IS_WINDOWS:
        import os
        return Path(os.path.expandvars("%APPDATA%"))
    if _IS_MACOS:
        return Path.home() / "Library" / "Application Support"
    return Path.home() / ".local" / "share"


# ══════════════════════════════════════════════════════════════════════════════
# DaVinci Resolve scripting module paths
# ══════════════════════════════════════════════════════════════════════════════

def get_resolve_module_paths() -> list[Path]:
    """Candidate folders containing DaVinciResolveScript.py for this OS."""
    if _IS_WINDOWS:
        return [
            Path(r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"),
            Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting\Modules"),
        ]
    if _IS_MACOS:
        return [
            Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"),
            Path.home() / "Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        ]
    return [
        Path("/opt/resolve/Developer/Scripting/Modules"),
        Path("/opt/DaVinci_Resolve/Developer/Scripting/Modules"),
        Path.home() / ".local/share/DaVinciResolve/Developer/Scripting/Modules",
    ]


# ══════════════════════════════════════════════════════════════════════════════
# Clipboard - read text
# ══════════════════════════════════════════════════════════════════════════════

def clipboard_get_text() -> Optional[str]:
    """Reads the system clipboard as text. Returns None on any failure."""
    try:
        if _IS_WINDOWS:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return None
            finally:
                win32clipboard.CloseClipboard()

        if _IS_MACOS:
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return result.stdout if result.returncode == 0 else None

        # Linux: try xclip first, then xsel.
        for cmd in (
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                continue
        return None

    except Exception:
        logger.exception("clipboard_get_text failed")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Clipboard - write text
# ══════════════════════════════════════════════════════════════════════════════

def clipboard_set_text(text: str) -> bool:
    """Writes text to the system clipboard. Returns True on success."""
    try:
        if _IS_WINDOWS:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
                return True
            finally:
                win32clipboard.CloseClipboard()

        if _IS_MACOS:
            result = subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
            return result.returncode == 0

        for cmd in (
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ):
            try:
                result = subprocess.run(cmd, input=text, text=True, timeout=4)
                if result.returncode == 0:
                    return True
            except Exception:
                continue
        return False

    except Exception:
        logger.exception("clipboard_set_text failed")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# DaVinci Resolve / Fusion scripting bridge ("Scripting" mode)
#
# Validated manually against Resolve's own console before being wired in here:
# capture = comp.CopySettings(selection) -> dvr.writestring(table) -> str
# paste   = dvr.readstring(text) -> table -> comp.Paste(table) -> bool
# ══════════════════════════════════════════════════════════════════════════════

_dvr_module: Optional[Any] = None  # cached DaVinciResolveScript module


def _import_dvr_module() -> Optional[Any]:
    """Imports DaVinciResolveScript once and caches it. Returns None if the
    module can't be found -- this does NOT mean Resolve isn't running, only
    that we couldn't locate the Modules folder for this install."""
    global _dvr_module
    if _dvr_module is not None:
        return _dvr_module

    for path in get_resolve_module_paths():
        if path.is_dir():
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.append(path_str)

    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except Exception:
        logger.warning("DaVinciResolveScript module not found on %s", os_label())
        return None

    _dvr_module = dvr
    return dvr


def get_fusion_comp() -> tuple[Optional[Any], Optional[str]]:
    """Connects to a running Resolve instance and returns (comp, error_code).
    error_code is None on success."""
    dvr = _import_dvr_module()
    if dvr is None:
        return None, "SCRIPTING_MODULE_NOT_FOUND"

    try:
        resolve = dvr.scriptapp("Resolve")
    except Exception:
        logger.warning("dvr.scriptapp('Resolve') raised an exception")
        return None, "SCRIPTING_NOT_CONNECTED"

    if not resolve:
        return None, "SCRIPTING_NOT_CONNECTED"

    try:
        fusion = resolve.Fusion()
        comp = fusion.GetCurrentComp() if fusion else None
    except Exception:
        logger.warning("resolve.Fusion()/GetCurrentComp() raised an exception")
        return None, "SCRIPTING_NOT_CONNECTED"

    if not comp:
        return None, "SCRIPTING_NO_COMP"

    return comp, None


def capture_selected_nodes() -> tuple[Optional[str], Optional[str]]:
    """Captures the currently selected Fusion nodes via the scripting API,
    bypassing the system clipboard entirely. Returns (text, error_code)."""
    comp, error = get_fusion_comp()
    if error:
        return None, error

    try:
        selected = comp.GetToolList(True)
        if not selected:
            return None, "SCRIPTING_NO_SELECTION"

        settings_table = comp.CopySettings(selected)
        text = _dvr_module.writestring(settings_table)
        if not text:
            return None, "SCRIPTING_CAPTURE_FAILED"
        return text, None
    except Exception:
        logger.exception("capture_selected_nodes failed")
        return None, "SCRIPTING_CAPTURE_FAILED"


def paste_fusion_data(text: str) -> tuple[bool, Optional[str]]:
    """Pastes captured node data directly into the active comp via the
    scripting API. Returns (ok, error_code)."""
    comp, error = get_fusion_comp()
    if error:
        return False, error

    try:
        settings_table = _dvr_module.readstring(text)
        if not settings_table:
            return False, "SCRIPTING_INVALID_DATA"
        ok = bool(comp.Paste(settings_table))
        return ok, (None if ok else "SCRIPTING_PASTE_FAILED")
    except Exception:
        logger.exception("paste_fusion_data failed")
        return False, "SCRIPTING_PASTE_FAILED"
