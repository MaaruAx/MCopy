"""
main.py - MCopy
Fusion node preset tool for DaVinci Resolve.
MMarket Ecosystem
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

_IS_FROZEN = getattr(sys, "frozen", False)
_MEIPASS = getattr(sys, "_MEIPASS", None)

if _IS_FROZEN:
    _BUNDLE_DIR = Path(_MEIPASS) if _MEIPASS else Path(sys.executable).parent
else:
    _BUNDLE_DIR = Path(__file__).resolve().parent

import json
import logging
import re
import sqlite3
import threading
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

from platform_compat import (
    get_appdata_dir,
    clipboard_get_text,
    clipboard_set_text,
    capture_selected_nodes,
    paste_fusion_data,
    os_label,
)

DATA_DIR = get_appdata_dir() / "MMarket" / "Apps" / "MCopy"
DB_FILE = DATA_DIR / "presets.db"
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_DIR = DATA_DIR / "logs"
_UI_FILE = _BUNDLE_DIR / "ui.html"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════
def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_DIR / "mcopy.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


_setup_logging()
logger = logging.getLogger("mcopy.main")
logger.info("MCopy starting up on %s", os_label())


# ══════════════════════════════════════════════════════════════════════════════
# ERROR CODES
#
# Every value returned to the UI (error or success message) must be either
# plain data or one of these machine-readable codes -- never hardcoded
# Spanish text. The frontend's i18n system (ui.html) maps each code to the
# user's selected language. Codes stay in English because they are code,
# not interface text.
# ══════════════════════════════════════════════════════════════════════════════
class ErrorCode:
    NAME_REQUIRED = "NAME_REQUIRED"
    FUSION_DATA_REQUIRED = "FUSION_DATA_REQUIRED"
    PRESET_NOT_FOUND = "PRESET_NOT_FOUND"
    FOLDER_NOT_FOUND = "FOLDER_NOT_FOUND"
    INVALID_STYLE = "INVALID_STYLE"
    CLIPBOARD_EMPTY = "CLIPBOARD_EMPTY"
    CLIPBOARD_WRITE_FAILED = "CLIPBOARD_WRITE_FAILED"
    INVALID_CODE_FORMAT = "INVALID_CODE_FORMAT"
    INVALID_CODE_CORRUPT = "INVALID_CODE_CORRUPT"
    INVALID_CODE_TOO_SHORT = "INVALID_CODE_TOO_SHORT"
    INVALID_CODE_CHECKSUM = "INVALID_CODE_CHECKSUM"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    UNKNOWN_TYPE = "UNKNOWN_TYPE"
    SCRIPTING_MODULE_NOT_FOUND = "SCRIPTING_MODULE_NOT_FOUND"
    SCRIPTING_NOT_CONNECTED = "SCRIPTING_NOT_CONNECTED"
    SCRIPTING_NO_COMP = "SCRIPTING_NO_COMP"
    SCRIPTING_NO_SELECTION = "SCRIPTING_NO_SELECTION"
    SCRIPTING_CAPTURE_FAILED = "SCRIPTING_CAPTURE_FAILED"
    SCRIPTING_INVALID_DATA = "SCRIPTING_INVALID_DATA"
    SCRIPTING_PASTE_FAILED = "SCRIPTING_PASTE_FAILED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


def _err(code: str, detail: Optional[str] = None) -> str:
    """Builds a standard {ok:false, error:CODE} JSON payload."""
    payload: dict[str, Any] = {"ok": False, "error": code}
    if detail:
        payload["detail"] = detail
    return json.dumps(payload)


_TOOL_HEADER_RE = re.compile(r"([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\{")


def _parse_node_summary(fusion_data: str) -> list[dict[str, str]]:
    """Extracts {name, type} pairs for the top-level tools in a captured
    Fusion settings string -- e.g. 'Transform1 = Transform {...}' inside the
    outer 'Tools = {...}' block. Tracks brace depth so nested constructors
    (Inputs, OperatorInfo, connected nodes, etc.) are never mistaken for
    top-level tools, and skips over quoted string content so a stray brace
    inside an expression, comment, or path doesn't throw the count off."""
    nodes: list[dict[str, str]] = []
    match = re.search(r"Tools\s*=\s*\{", fusion_data)
    if not match:
        return nodes

    i = match.end()
    n = len(fusion_data)
    depth = 1  # already inside Tools' opening brace
    in_string: Optional[str] = None  # the quote character we're currently inside, if any

    while i < n and depth > 0:
        ch = fusion_data[i]

        if in_string:
            if ch == "\\":
                i += 2  # skip the escaped character along with the backslash
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue

        if ch == '"' or ch == "'":
            in_string = ch
            i += 1
            continue

        if depth == 1:
            header = _TOOL_HEADER_RE.match(fusion_data, i)
            if header:
                nodes.append({"name": header.group(1), "type": header.group(2)})
                i = header.end() - 1  # land exactly on the '{' for normal depth handling
                continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1

    return nodes


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════
_SCHEMA_VERSION = 3
_db_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Versioned schema migrations using SQLite's own PRAGMA user_version,
    instead of ad-hoc 'does this column exist' checks scattered around.
    To add a future migration: bump _SCHEMA_VERSION and add an
    `if current < N:` block below."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]

    if current < 1:
        current = 1  # base schema, stamped for fresh installs

    if current < 2:
        # v2: presets gained folder_id (folder/collection system, v1.2.0).
        columns = [row[1] for row in conn.execute("PRAGMA table_info(presets)").fetchall()]
        if "folder_id" not in columns:
            conn.execute("ALTER TABLE presets ADD COLUMN folder_id INTEGER")
        current = 2

    if current < 3:
        # v3: presets gained their own icon, shown in the preset list.
        columns = [row[1] for row in conn.execute("PRAGMA table_info(presets)").fetchall()]
        if "icon" not in columns:
            conn.execute("ALTER TABLE presets ADD COLUMN icon TEXT NOT NULL DEFAULT 'box'")
        current = 3

    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
    conn.commit()


def _init_db() -> None:
    with _db_lock:
        conn = _get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS folders (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT    NOT NULL DEFAULT 'New folder',
                    color      TEXT    NOT NULL DEFAULT '#f5c842',
                    icon       TEXT    NOT NULL DEFAULT 'folder',
                    style      TEXT    NOT NULL DEFAULT 'tab',
                    pinned     INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT    DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS presets (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    NOT NULL,
                    description TEXT    DEFAULT '',
                    fusion_data TEXT    NOT NULL,
                    source      TEXT    DEFAULT 'clipboard',
                    folder_id   INTEGER,
                    icon        TEXT    NOT NULL DEFAULT 'box',
                    created_at  TEXT    DEFAULT (datetime('now')),
                    updated_at  TEXT    DEFAULT (datetime('now'))
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS presets_fts USING fts5(
                    name, description, content='presets', content_rowid='id'
                );

                CREATE TRIGGER IF NOT EXISTS presets_ai AFTER INSERT ON presets BEGIN
                    INSERT INTO presets_fts(rowid, name, description)
                    VALUES (new.id, new.name, new.description);
                END;
                CREATE TRIGGER IF NOT EXISTS presets_ad AFTER DELETE ON presets BEGIN
                    INSERT INTO presets_fts(presets_fts, rowid, name, description)
                    VALUES ('delete', old.id, old.name, old.description);
                END;
                CREATE TRIGGER IF NOT EXISTS presets_au AFTER UPDATE ON presets BEGIN
                    INSERT INTO presets_fts(presets_fts, rowid, name, description)
                    VALUES ('delete', old.id, old.name, old.description);
                    INSERT INTO presets_fts(rowid, name, description)
                    VALUES (new.id, new.name, new.description);
                END;

                CREATE INDEX IF NOT EXISTS idx_presets_folder_id  ON presets(folder_id);
                CREATE INDEX IF NOT EXISTS idx_presets_updated_at ON presets(updated_at);
                CREATE INDEX IF NOT EXISTS idx_presets_created_at ON presets(created_at);
                CREATE INDEX IF NOT EXISTS idx_folders_sort        ON folders(pinned, sort_order);
            """)
            conn.commit()
            _run_migrations(conn)
        except Exception:
            logger.exception("Database initialization failed")
            raise
        finally:
            conn.close()


_init_db()


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
_DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "mmarket", "accent": "#f5c842", "font": "barlow",
    "mode": "clipboard", "lang": "en",
    "window_w": 980, "window_h": 650,
    "folder_style": "tab",
    "sort_mode": "recent",
    "view": "folders",
    "active_folder_id": None,
}

# Native Qt file-dialog titles aren't part of the HTML UI, so they can't go
# through the JS i18n system -- they get their own tiny table here instead
# of being hardcoded in one language.
_DIALOG_LABELS: dict[str, dict[str, str]] = {
    "es": {"export": "Exportar", "import": "Importar .mcopy"},
    "en": {"export": "Export", "import": "Import .mcopy"},
    "de": {"export": "Exportieren", "import": ".mcopy importieren"},
    "hi": {"export": "निर्यात करें", "import": ".mcopy आयात करें"},
}


def _load_settings() -> dict[str, Any]:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(_DEFAULT_SETTINGS)
        for key, value in data.items():
            if key in _DEFAULT_SETTINGS:
                merged[key] = value
        return merged
    except Exception:
        return dict(_DEFAULT_SETTINGS)


def _persist_settings(data: dict[str, Any]) -> bool:
    try:
        active_folder_id = data.get("active_folder_id")
        safe = {
            "theme":            str(data.get("theme",         "mmarket"))[:24],
            "accent":           str(data.get("accent",        "#f5c842"))[:24],
            "font":             str(data.get("font",           "barlow"))[:24],
            "mode":             str(data.get("mode",        "clipboard"))[:24],
            "lang":             str(data.get("lang",             "es"))[:8],
            "window_w":         max(820, min(3840, int(data.get("window_w",  980)))),
            "window_h":         max(560, min(2160, int(data.get("window_h",  650)))),
            "folder_style":     str(data.get("folder_style",     "tab"))[:10],
            "sort_mode":        str(data.get("sort_mode",     "recent"))[:20],
            "view":             str(data.get("view",         "folders"))[:20],
            "active_folder_id": int(active_folder_id) if active_folder_id is not None else None,
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(safe, f, indent=2)
        return True
    except Exception:
        logger.exception("Failed to persist settings")
        return False


def _dialog_label(key: str) -> str:
    lang = _load_settings().get("lang", "en")
    table = _DIALOG_LABELS.get(lang, _DIALOG_LABELS["en"])
    return table.get(key, key)


# ══════════════════════════════════════════════════════════════════════════════
# BACKEND
# ══════════════════════════════════════════════════════════════════════════════
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication


class Backend(QObject):
    def __init__(self, window: "MCopyWindow") -> None:
        super().__init__()
        self._win = window

    # ── Window ───────────────────────────────────────────────────────────────
    @Slot()
    def start_move(self) -> None:
        try:
            handle = self._win.windowHandle()
            if handle:
                handle.startSystemMove()
        except Exception:
            logger.exception("start_move failed")

    @Slot()
    def minimize_window(self) -> None:
        try:
            self._win.showMinimized()
        except Exception:
            logger.exception("minimize_window failed")

    @Slot(result=str)
    def toggle_maximize_window(self) -> str:
        """Toggles between maximized and normal window state. Returns the
        resulting state so the UI can swap the maximize/restore icon."""
        try:
            if self._win.isMaximized():
                self._win.showNormal()
                maximized = False
            else:
                self._win.showMaximized()
                maximized = True
            return json.dumps({"ok": True, "maximized": maximized})
        except Exception as e:
            logger.exception("toggle_maximize_window failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(result=str)
    def is_window_maximized(self) -> str:
        try:
            return json.dumps({"ok": True, "maximized": self._win.isMaximized()})
        except Exception as e:
            logger.exception("is_window_maximized failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot()
    def close_window(self) -> None:
        try:
            self._win.close()
        except Exception:
            logger.exception("close_window failed")

    # ── Settings ─────────────────────────────────────────────────────────────
    @Slot(result=str)
    def get_settings(self) -> str:
        return json.dumps(_load_settings())

    @Slot(str, result=str)
    def save_settings(self, data_json: str) -> str:
        try:
            ok = _persist_settings(json.loads(data_json))
            return json.dumps({"ok": ok})
        except Exception as e:
            logger.exception("save_settings failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    # ── Folders ──────────────────────────────────────────────────────────────
    @Slot(result=str)
    def get_folders(self) -> str:
        try:
            with _db_lock:
                conn = _get_conn()
                try:
                    rows = conn.execute(
                        "SELECT f.id, f.name, f.color, f.icon, f.style, f.pinned, f.sort_order,"
                        " COUNT(p.id) as preset_count"
                        " FROM folders f LEFT JOIN presets p ON p.folder_id = f.id"
                        " GROUP BY f.id ORDER BY f.pinned DESC, f.sort_order ASC, f.id ASC"
                    ).fetchall()
                    total = conn.execute("SELECT COUNT(*) as n FROM presets").fetchone()["n"]
                    unorg = conn.execute(
                        "SELECT COUNT(*) as n FROM presets WHERE folder_id IS NULL"
                    ).fetchone()["n"]
                    return json.dumps({
                        "folders":     [dict(r) for r in rows],
                        "total_count": total,
                        "unorg_count": unorg,
                    })
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("get_folders failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def search_folders(self, query: str) -> str:
        try:
            q = query.strip()
            if not q:
                return self.get_folders()
            with _db_lock:
                conn = _get_conn()
                try:
                    pattern = f"%{q}%"
                    rows = conn.execute(
                        "SELECT f.id, f.name, f.color, f.icon, f.style, f.pinned, f.sort_order,"
                        " COUNT(p.id) as preset_count"
                        " FROM folders f LEFT JOIN presets p ON p.folder_id = f.id"
                        " WHERE f.name LIKE ? GROUP BY f.id"
                        " ORDER BY f.pinned DESC, f.sort_order ASC, f.id ASC",
                        (pattern,)
                    ).fetchall()
                    total = conn.execute("SELECT COUNT(*) as n FROM presets").fetchone()["n"]
                    unorg = conn.execute(
                        "SELECT COUNT(*) as n FROM presets WHERE folder_id IS NULL"
                    ).fetchone()["n"]
                    return json.dumps({
                        "folders":     [dict(r) for r in rows],
                        "total_count": total,
                        "unorg_count": unorg,
                    })
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("search_folders failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def create_folder(self, data_json: str) -> str:
        try:
            d = json.loads(data_json)
            with _db_lock:
                conn = _get_conn()
                try:
                    cur = conn.execute(
                        "INSERT INTO folders (name, color, icon, style) VALUES (?, ?, ?, ?)",
                        (str(d.get("name", "New folder"))[:80],
                         str(d.get("color", "#f5c842"))[:24],
                         str(d.get("icon",  "folder"))[:40],
                         str(d.get("style", "tab"))[:10])
                    )
                    conn.commit()
                    return json.dumps({"ok": True, "id": cur.lastrowid})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("create_folder failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def update_folder(self, data_json: str) -> str:
        try:
            d = json.loads(data_json)
            fid = int(d["id"])
            fields: list[str] = []
            vals: list[Any] = []
            for key, col, max_len in [
                ("name", "name", 80), ("color", "color", 24),
                ("icon", "icon", 40), ("style", "style", 10),
            ]:
                if key in d:
                    fields.append(f"{col} = ?")
                    vals.append(str(d[key])[:max_len])
            if "pinned" in d:
                fields.append("pinned = ?")
                vals.append(1 if d["pinned"] else 0)
            if not fields:
                return json.dumps({"ok": True})
            vals.append(fid)
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute(f"UPDATE folders SET {', '.join(fields)} WHERE id = ?", vals)
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("update_folder failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def delete_folder(self, folder_id_str: str) -> str:
        try:
            fid = int(folder_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute("UPDATE presets SET folder_id = NULL WHERE folder_id = ?", (fid,))
                    conn.execute("DELETE FROM folders WHERE id = ?", (fid,))
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("delete_folder failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def duplicate_folder(self, folder_id_str: str) -> str:
        try:
            fid = int(folder_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    src = conn.execute(
                        "SELECT name, color, icon, style FROM folders WHERE id = ?", (fid,)
                    ).fetchone()
                    if not src:
                        return _err(ErrorCode.FOLDER_NOT_FOUND)
                    cur = conn.execute(
                        "INSERT INTO folders (name, color, icon, style) VALUES (?, ?, ?, ?)",
                        (src["name"] + " (copy)", src["color"], src["icon"], src["style"])
                    )
                    new_fid = cur.lastrowid
                    for p in conn.execute(
                        "SELECT name, description, fusion_data, source FROM presets WHERE folder_id = ?",
                        (fid,)
                    ).fetchall():
                        conn.execute(
                            "INSERT INTO presets (name, description, fusion_data, source, folder_id)"
                            " VALUES (?, ?, ?, ?, ?)",
                            (p["name"], p["description"], p["fusion_data"], p["source"], new_fid)
                        )
                    conn.commit()
                    return json.dumps({"ok": True, "id": new_fid})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("duplicate_folder failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def update_all_folders_style(self, style_str: str) -> str:
        """Changes the visual style of every folder at once."""
        try:
            style = str(style_str).strip()[:10]
            if style not in ("tab", "solid"):
                return _err(ErrorCode.INVALID_STYLE)
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute("UPDATE folders SET style = ?", (style,))
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("update_all_folders_style failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    # ── Presets ──────────────────────────────────────────────────────────────
    @Slot(str, str, result=str)
    def get_folder_presets(self, folder_id_str: str, sort_mode: str) -> str:
        try:
            order = {
                "recent": "updated_at DESC", "name_asc": "name ASC",
                "name_desc": "name DESC", "oldest": "created_at ASC",
            }.get(sort_mode, "updated_at DESC")
            with _db_lock:
                conn = _get_conn()
                try:
                    if folder_id_str == "all":
                        rows = conn.execute(
                            f"SELECT id, name, description, source, folder_id, icon, created_at"
                            f" FROM presets ORDER BY {order}"
                        ).fetchall()
                    elif folder_id_str == "unorg":
                        rows = conn.execute(
                            f"SELECT id, name, description, source, folder_id, icon, created_at"
                            f" FROM presets WHERE folder_id IS NULL ORDER BY {order}"
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            f"SELECT id, name, description, source, folder_id, icon, created_at"
                            f" FROM presets WHERE folder_id = ? ORDER BY {order}",
                            (int(folder_id_str),)
                        ).fetchall()
                    return json.dumps([dict(r) for r in rows])
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("get_folder_presets failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, str, str, result=str)
    def search_folder_presets(self, folder_id_str: str, query: str, sort_mode: str) -> str:
        try:
            q = query.strip()
            if not q:
                return self.get_folder_presets(folder_id_str, sort_mode)
            order = {
                "recent": "p.updated_at DESC", "name_asc": "p.name ASC",
                "name_desc": "p.name DESC", "oldest": "p.created_at ASC",
            }.get(sort_mode, "p.updated_at DESC")

            def _sanitize_fts_query(s: str) -> str:
                for c in '"*():-+^\\':
                    s = s.replace(c, " ")
                return s.strip()

            terms = [w for w in _sanitize_fts_query(q).split() if w]

            if folder_id_str == "all":
                folder_clause, folder_params = "", []
            elif folder_id_str == "unorg":
                folder_clause, folder_params = "AND p.folder_id IS NULL", []
            else:
                folder_clause, folder_params = "AND p.folder_id = ?", [int(folder_id_str)]

            with _db_lock:
                conn = _get_conn()
                try:
                    if terms:
                        try:
                            fts_query = " ".join(w + "*" for w in terms)
                            rows = conn.execute(
                                f"SELECT p.id, p.name, p.description, p.source, p.folder_id, p.icon, p.created_at"
                                f" FROM presets p WHERE p.id IN"
                                f" (SELECT rowid FROM presets_fts WHERE presets_fts MATCH ?)"
                                f" {folder_clause} ORDER BY {order}",
                                [fts_query] + folder_params
                            ).fetchall()
                            return json.dumps([dict(r) for r in rows])
                        except Exception:
                            pass  # fall through to LIKE-based search below
                    pattern = f"%{q}%"
                    rows = conn.execute(
                        f"SELECT id, name, description, source, folder_id, icon, created_at FROM presets p"
                        f" WHERE (name LIKE ? OR description LIKE ?) {folder_clause} ORDER BY {order}",
                        [pattern, pattern] + folder_params
                    ).fetchall()
                    return json.dumps([dict(r) for r in rows])
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("search_folder_presets failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def save_preset(self, data_json: str) -> str:
        try:
            d = json.loads(data_json)
            name = str(d.get("name", "")).strip()
            description = str(d.get("description", "")).strip()
            fusion_data = str(d.get("fusion_data", "")).strip()
            source = str(d.get("source", "clipboard"))
            folder_id = d.get("folder_id")
            if not name:
                return _err(ErrorCode.NAME_REQUIRED)
            if not fusion_data:
                return _err(ErrorCode.FUSION_DATA_REQUIRED)
            if folder_id is not None:
                folder_id = int(folder_id)
            with _db_lock:
                conn = _get_conn()
                try:
                    cur = conn.execute(
                        "INSERT INTO presets (name, description, fusion_data, source, folder_id)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (name, description, fusion_data, source, folder_id)
                    )
                    conn.commit()
                    return json.dumps({"ok": True, "id": cur.lastrowid})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("save_preset failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def delete_preset(self, preset_id_str: str) -> str:
        try:
            pid = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute("DELETE FROM presets WHERE id = ?", (pid,))
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("delete_preset failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, str, result=str)
    def move_preset_to_folder(self, preset_id_str: str, folder_id_str: str) -> str:
        try:
            pid = int(preset_id_str)
            fid = None if folder_id_str in ("null", "unorg", "all") else int(folder_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute(
                        "UPDATE presets SET folder_id = ?, updated_at = datetime('now') WHERE id = ?",
                        (fid, pid)
                    )
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("move_preset_to_folder failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, str, result=str)
    def move_all_to_folder(self, source_folder_id_str: str, target_folder_id_str: str) -> str:
        """Moves every preset from one folder to another."""
        try:
            fid = None if target_folder_id_str in ("null", "unorg") else int(target_folder_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    if source_folder_id_str == "unorg":
                        conn.execute(
                            "UPDATE presets SET folder_id = ?, updated_at = datetime('now')"
                            " WHERE folder_id IS NULL",
                            (fid,)
                        )
                    else:
                        conn.execute(
                            "UPDATE presets SET folder_id = ?, updated_at = datetime('now')"
                            " WHERE folder_id = ?",
                            (fid, int(source_folder_id_str))
                        )
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("move_all_to_folder failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def update_preset(self, data_json: str) -> str:
        """Partial update for a preset: name, description, and/or icon."""
        try:
            d = json.loads(data_json)
            pid = int(d["id"])
            fields: list[str] = []
            vals: list[Any] = []
            if "name" in d:
                name = str(d["name"]).strip()
                if not name:
                    return _err(ErrorCode.NAME_REQUIRED)
                fields.append("name = ?")
                vals.append(name[:80])
            if "description" in d:
                fields.append("description = ?")
                vals.append(str(d["description"]).strip()[:300])
            if "icon" in d:
                fields.append("icon = ?")
                vals.append(str(d["icon"])[:40])
            if not fields:
                return json.dumps({"ok": True})
            fields.append("updated_at = datetime('now')")
            vals.append(pid)
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute(f"UPDATE presets SET {', '.join(fields)} WHERE id = ?", vals)
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("update_preset failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def get_preset_nodes(self, preset_id_str: str) -> str:
        """Lightweight {name, type} summary of the nodes a preset contains,
        for display in the UI without sending the full raw fusion_data."""
        try:
            pid = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    row = conn.execute(
                        "SELECT fusion_data FROM presets WHERE id = ?", (pid,)
                    ).fetchone()
                finally:
                    conn.close()
            if not row:
                return _err(ErrorCode.PRESET_NOT_FOUND)
            nodes = _parse_node_summary(row["fusion_data"])
            return json.dumps({"ok": True, "nodes": nodes})
        except Exception as e:
            logger.exception("get_preset_nodes failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    # ── Nodes (clipboard or Fusion scripting bridge) ────────────────────────
    @Slot(result=str)
    def copy_nodes(self) -> str:
        """Captures the currently selected/copied Fusion nodes. Uses the
        scripting bridge when settings.mode == 'scripting', otherwise reads
        the system clipboard the way earlier versions always did."""
        try:
            mode = _load_settings().get("mode", "clipboard")

            if mode == "scripting":
                text, error = capture_selected_nodes()
                if error:
                    return _err(error)
            else:
                text = clipboard_get_text()
                if not text or not text.strip():
                    return _err(ErrorCode.CLIPBOARD_EMPTY)

            return json.dumps({
                "ok": True, "data": text, "via": mode,
                "preview": text[:120].replace("\n", " "),
                "length": len(text),
            })
        except Exception as e:
            logger.exception("copy_nodes failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def paste_nodes(self, preset_id_str: str) -> str:
        try:
            pid = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    row = conn.execute(
                        "SELECT fusion_data, name FROM presets WHERE id = ?", (pid,)
                    ).fetchone()
                finally:
                    conn.close()
            if not row:
                return _err(ErrorCode.PRESET_NOT_FOUND)

            mode = _load_settings().get("mode", "clipboard")

            if mode == "scripting":
                ok, error = paste_fusion_data(row["fusion_data"])
                if not ok:
                    return _err(error or ErrorCode.SCRIPTING_PASTE_FAILED)
                return json.dumps({"ok": True, "name": row["name"], "via": "scripting"})

            ok = clipboard_set_text(row["fusion_data"])
            if not ok:
                return _err(ErrorCode.CLIPBOARD_WRITE_FAILED)
            return json.dumps({"ok": True, "name": row["name"], "via": "clipboard"})
        except Exception as e:
            logger.exception("paste_nodes failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def copy_text_to_clipboard(self, text: str) -> str:
        """Copies arbitrary text to the system clipboard (used by the share-code modal)."""
        try:
            ok = clipboard_set_text(text)
            if ok:
                return json.dumps({"ok": True})
            return _err(ErrorCode.CLIPBOARD_WRITE_FAILED)
        except Exception as e:
            logger.exception("copy_text_to_clipboard failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(result=str)
    def read_clipboard_text(self) -> str:
        """Reads the raw system clipboard text. Used by the global Ctrl+V
        shortcut to detect a pasted MCOPY: code anywhere in the UI -- this
        always reads the literal clipboard, independent of the
        clipboard/scripting capture mode setting."""
        try:
            text = clipboard_get_text()
            return json.dumps({"ok": True, "text": text or ""})
        except Exception as e:
            logger.exception("read_clipboard_text failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    # ── Shareable code (MCOPY:...) ───────────────────────────────────────────
    @Slot(str, result=str)
    def encode_preset(self, preset_id_str: str) -> str:
        """Compresses fusion_data into a copyable MCOPY:... string."""
        try:
            import zlib, base64, struct
            pid = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    row = conn.execute(
                        "SELECT name, description, fusion_data FROM presets WHERE id = ?", (pid,)
                    ).fetchone()
                finally:
                    conn.close()
            if not row:
                return _err(ErrorCode.PRESET_NOT_FOUND)

            payload = json.dumps({
                "n": row["name"],
                "d": row["description"],
                "f": row["fusion_data"],
            }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

            crc = struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
            compressed = zlib.compress(crc + payload, level=9)
            code = "MCOPY:" + base64.urlsafe_b64encode(compressed).decode("ascii")

            return json.dumps({"ok": True, "code": code, "chars": len(code)})
        except Exception as e:
            logger.exception("encode_preset failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def decode_preset_code(self, code_str: str) -> str:
        """Decodes an MCOPY:... string back into preset data."""
        try:
            import zlib, base64, struct
            code = code_str.strip()
            if not code.startswith("MCOPY:"):
                return _err(ErrorCode.INVALID_CODE_FORMAT)

            b64 = code[6:]
            try:
                raw = zlib.decompress(base64.urlsafe_b64decode(b64))
            except Exception:
                return _err(ErrorCode.INVALID_CODE_CORRUPT)

            if len(raw) < 4:
                return _err(ErrorCode.INVALID_CODE_TOO_SHORT)

            crc_stored = struct.unpack(">I", raw[:4])[0]
            payload = raw[4:]
            crc_calculated = zlib.crc32(payload) & 0xFFFFFFFF
            if crc_stored != crc_calculated:
                return _err(ErrorCode.INVALID_CODE_CHECKSUM)

            data = json.loads(payload.decode("utf-8"))
            return json.dumps({
                "ok":          True,
                "name":        data.get("n", "Imported preset"),
                "description": data.get("d", ""),
                "fusion_data": data.get("f", ""),
            })
        except Exception as e:
            logger.exception("decode_preset_code failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    # ── Import / Export ──────────────────────────────────────────────────────
    @Slot(str, result=str)
    def export_preset_data(self, preset_id_str: str) -> str:
        try:
            pid = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    r = conn.execute(
                        "SELECT name, description, fusion_data, source, created_at"
                        " FROM presets WHERE id = ?",
                        (pid,)
                    ).fetchone()
                    if not r:
                        return _err(ErrorCode.PRESET_NOT_FOUND)
                    payload = {
                        "version": 1, "type": "preset",
                        "name": r["name"], "description": r["description"],
                        "fusion_data": r["fusion_data"], "source": r["source"],
                        "created_at": r["created_at"],
                    }
                    return json.dumps({"ok": True, "data": json.dumps(payload, ensure_ascii=False, indent=2)})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("export_preset_data failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, result=str)
    def export_folder_data(self, folder_id_str: str) -> str:
        try:
            fid = int(folder_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    folder = conn.execute(
                        "SELECT name, color, icon, style FROM folders WHERE id = ?", (fid,)
                    ).fetchone()
                    if not folder:
                        return _err(ErrorCode.FOLDER_NOT_FOUND)
                    presets = conn.execute(
                        "SELECT name, description, fusion_data, source FROM presets WHERE folder_id = ?",
                        (fid,)
                    ).fetchall()
                    payload = {
                        "version": 1, "type": "folder",
                        "name": folder["name"], "color": folder["color"],
                        "icon": folder["icon"], "style": folder["style"],
                        "presets": [dict(p) for p in presets],
                    }
                    return json.dumps({"ok": True, "data": json.dumps(payload, ensure_ascii=False, indent=2)})
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("export_folder_data failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, str, result=str)
    def save_export_file(self, filename: str, content: str) -> str:
        try:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(
                self._win, _dialog_label("export"),
                str(Path.home() / filename),
                "MCopy Files (*.mcopy)"
            )
            if not path:
                return json.dumps({"ok": False, "cancelled": True})
            if not path.endswith(".mcopy"):
                path += ".mcopy"
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return json.dumps({"ok": True})
        except Exception as e:
            logger.exception("save_export_file failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(result=str)
    def open_import_dialog(self) -> str:
        try:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                self._win, _dialog_label("import"),
                str(Path.home()), "MCopy Files (*.mcopy)"
            )
            if not path:
                return json.dumps({"ok": False, "cancelled": True})
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps({"ok": True, "data": data})
        except Exception as e:
            logger.exception("open_import_dialog failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))

    @Slot(str, str, result=str)
    def import_mcopy(self, json_str: str, target_folder_id_str: str) -> str:
        try:
            d = json.loads(json_str) if isinstance(json_str, str) else json_str
            dtype = d.get("type", "preset")
            if d.get("version", 1) != 1:
                return _err(ErrorCode.UNSUPPORTED_VERSION)
            with _db_lock:
                conn = _get_conn()
                try:
                    if dtype == "preset":
                        fid = None if target_folder_id_str in ("null", "unorg", "all") else int(target_folder_id_str)
                        cur = conn.execute(
                            "INSERT INTO presets (name, description, fusion_data, source, folder_id)"
                            " VALUES (?, ?, ?, ?, ?)",
                            (d.get("name", "Imported preset"), d.get("description", ""),
                             d.get("fusion_data", ""), d.get("source", "clipboard"), fid)
                        )
                        conn.commit()
                        return json.dumps({"ok": True, "type": "preset", "id": cur.lastrowid})

                    if dtype == "folder":
                        cur = conn.execute(
                            "INSERT INTO folders (name, color, icon, style) VALUES (?, ?, ?, ?)",
                            (d.get("name", "Imported folder"), d.get("color", "#f5c842"),
                             d.get("icon", "folder"), d.get("style", "tab"))
                        )
                        new_fid = cur.lastrowid
                        for p in d.get("presets", []):
                            conn.execute(
                                "INSERT INTO presets (name, description, fusion_data, source, folder_id)"
                                " VALUES (?, ?, ?, ?, ?)",
                                (p.get("name", ""), p.get("description", ""),
                                 p.get("fusion_data", ""), p.get("source", "clipboard"), new_fid)
                            )
                        conn.commit()
                        return json.dumps({"ok": True, "type": "folder", "id": new_fid})

                    return _err(ErrorCode.UNKNOWN_TYPE)
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("import_mcopy failed")
            return _err(ErrorCode.UNKNOWN_ERROR, str(e))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════
from PySide6.QtWidgets import QMainWindow, QSizeGrip
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QIcon


class MCopyWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MCopy")
        self.setMinimumSize(820, 560)
        settings = _load_settings()
        self.resize(
            max(820, int(settings.get("window_w", 980))),
            max(560, int(settings.get("window_h", 650))),
        )
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        self._channel = QWebChannel()
        self._backend = Backend(self)
        self._channel.registerObject("backend", self._backend)
        self._view.page().setWebChannel(self._channel)

        # GPU acceleration for the WebEngine view.
        web_settings = self._view.page().settings()
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        web_settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)

        # Inject qwebchannel.js manually (Qt 6.7+ blocks qrc:// from file:// pages).
        script = QWebEngineScript()
        script.setSourceUrl(QUrl("qrc:/qtwebchannel/qwebchannel.js"))
        script.setName("mcopy-qwebchannel")
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        self._view.page().scripts().insert(script)

        # Custom resize grip for the frameless window.
        self._grip = QSizeGrip(self)
        self._grip.resize(14, 14)
        self._grip.setStyleSheet("background: transparent;")
        self._grip.raise_()

        self._resize_timer: Optional[QTimer] = None

        if _UI_FILE.is_file():
            self._view.setUrl(QUrl.fromLocalFile(str(_UI_FILE)))
        else:
            self._view.setHtml(
                "<body style='background:#0a0a0a;color:#e05c5c;font-family:monospace;padding:24px'>"
                f"<h2>ui.html not found</h2><p>{_UI_FILE}</p></body>"
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._grip.move(self.width() - 15, self.height() - 15)
        if self._resize_timer is None:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._save_size)
        self._resize_timer.start(700)

    def _save_size(self) -> None:
        try:
            settings = _load_settings()
            settings["window_w"] = self.width()
            settings["window_h"] = self.height()
            _persist_settings(settings)
        except Exception:
            logger.exception("Failed to persist window size")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--enable-gpu-rasterization --enable-zero-copy "
        "--ignore-gpu-blocklist --enable-oop-rasterization",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("MCopy")
    app.setOrganizationName("MMarket")
    app.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    window = MCopyWindow()
    window.show()
    sys.exit(app.exec())
