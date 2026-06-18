"""
main.py — MCopy
Herramienta de presets de nodos Fusion para DaVinci Resolve.
MMarket Ecosystem
"""

import sys
import os

_IS_FROZEN  = getattr(sys, "frozen", False)
_BUNDLE_DIR = getattr(sys, "_MEIPASS", None)

if _IS_FROZEN:
    _SCRIPT_DIR = os.path.dirname(sys.executable)
    _BUNDLE_DIR = _BUNDLE_DIR or _SCRIPT_DIR
else:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR = _SCRIPT_DIR

import json
import sqlite3
import threading
import platform

from platform_compat import (
    get_appdata_dir, get_resolve_module_paths,
    clipboard_get_text, clipboard_set_text,
)

_OS = platform.system()

APPDATA       = get_appdata_dir()
DATA_DIR      = os.path.join(APPDATA, "MMarket", "Apps", "MCopy")
DB_FILE       = os.path.join(DATA_DIR, "presets.db")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
_UI_FILE      = os.path.join(_BUNDLE_DIR, "ui.html")

os.makedirs(DATA_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# BASE DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
_db_lock = threading.Lock()

def _get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    with _db_lock:
        conn = _get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS folders (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT    NOT NULL DEFAULT 'Nueva carpeta',
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
            """)
            conn.commit()
            # Migracion: agregar folder_id si no existe (instalaciones anteriores)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(presets)").fetchall()]
            if 'folder_id' not in cols:
                conn.execute("ALTER TABLE presets ADD COLUMN folder_id INTEGER")
                conn.commit()
        finally:
            conn.close()

_init_db()

# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
_DEFAULT_SETTINGS = {
    "theme": "mmarket", "accent": "#f5c842", "font": "barlow",
    "mode": "clipboard", "lang": "es",
    "window_w": 980, "window_h": 650,
    "folder_style": "tab",
    "sort_mode": "recent",
    "view": "folders",
    "active_folder_id": None,
}

def _load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        m = dict(_DEFAULT_SETTINGS)
        for k, v in data.items():
            if k in _DEFAULT_SETTINGS:
                m[k] = v
        return m
    except Exception:
        return dict(_DEFAULT_SETTINGS)

def _persist_settings(data):
    try:
        af = data.get("active_folder_id")
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
            "active_folder_id": int(af) if af is not None else None,
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(safe, f, indent=2)
        return True
    except Exception:
        return False

# ══════════════════════════════════════════════════════════════════════════════
# BACKEND
# ══════════════════════════════════════════════════════════════════════════════
from PySide6.QtCore    import QObject, Slot
from PySide6.QtWidgets import QApplication


class Backend(QObject):
    def __init__(self, window):
        super().__init__()
        self._win = window

    # ── Ventana ──────────────────────────────────────────────────────────────
    @Slot()
    def start_move(self):
        try:
            h = self._win.windowHandle()
            if h: h.startSystemMove()
        except Exception: pass

    @Slot()
    def minimize_window(self):
        try: self._win.showMinimized()
        except Exception: pass

    @Slot()
    def close_window(self):
        try: self._win.close()
        except Exception: pass

    # ── Settings ─────────────────────────────────────────────────────────────
    @Slot(result=str)
    def get_settings(self):
        return json.dumps(_load_settings())

    @Slot(str, result=str)
    def save_settings(self, data_json):
        try:
            ok = _persist_settings(json.loads(data_json))
            return json.dumps({"ok": ok})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Carpetas ──────────────────────────────────────────────────────────────
    @Slot(result=str)
    def get_folders(self):
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
                    unorg = conn.execute("SELECT COUNT(*) as n FROM presets WHERE folder_id IS NULL").fetchone()["n"]
                    return json.dumps({
                        "folders":     [dict(r) for r in rows],
                        "total_count": total,
                        "unorg_count": unorg,
                    })
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"error": str(e)})

    @Slot(str, result=str)
    def search_folders(self, query):
        try:
            q = query.strip()
            if not q:
                return self.get_folders()
            with _db_lock:
                conn = _get_conn()
                try:
                    pat = f"%{q}%"
                    rows = conn.execute(
                        "SELECT f.id, f.name, f.color, f.icon, f.style, f.pinned, f.sort_order,"
                        " COUNT(p.id) as preset_count"
                        " FROM folders f LEFT JOIN presets p ON p.folder_id = f.id"
                        " WHERE f.name LIKE ? GROUP BY f.id"
                        " ORDER BY f.pinned DESC, f.sort_order ASC, f.id ASC",
                        (pat,)
                    ).fetchall()
                    total = conn.execute("SELECT COUNT(*) as n FROM presets").fetchone()["n"]
                    unorg = conn.execute("SELECT COUNT(*) as n FROM presets WHERE folder_id IS NULL").fetchone()["n"]
                    return json.dumps({
                        "folders":     [dict(r) for r in rows],
                        "total_count": total,
                        "unorg_count": unorg,
                    })
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"error": str(e)})

    @Slot(str, result=str)
    def create_folder(self, data_json):
        try:
            d = json.loads(data_json)
            with _db_lock:
                conn = _get_conn()
                try:
                    cur = conn.execute(
                        "INSERT INTO folders (name, color, icon, style) VALUES (?, ?, ?, ?)",
                        (str(d.get("name", "Nueva carpeta"))[:80],
                         str(d.get("color", "#f5c842"))[:24],
                         str(d.get("icon",  "folder"))[:40],
                         str(d.get("style", "tab"))[:10])
                    )
                    conn.commit()
                    return json.dumps({"ok": True, "id": cur.lastrowid})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def update_folder(self, data_json):
        try:
            d   = json.loads(data_json)
            fid = int(d["id"])
            fields, vals = [], []
            for key, col, ml in [("name","name",80),("color","color",24),
                                  ("icon","icon",40),("style","style",10)]:
                if key in d:
                    fields.append(f"{col} = ?")
                    vals.append(str(d[key])[:ml])
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
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def delete_folder(self, folder_id_str):
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
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def duplicate_folder(self, folder_id_str):
        try:
            fid = int(folder_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    src = conn.execute(
                        "SELECT name,color,icon,style FROM folders WHERE id=?", (fid,)
                    ).fetchone()
                    if not src:
                        return json.dumps({"ok": False, "error": "Carpeta no encontrada"})
                    cur = conn.execute(
                        "INSERT INTO folders (name,color,icon,style) VALUES (?,?,?,?)",
                        (src["name"] + " (copia)", src["color"], src["icon"], src["style"])
                    )
                    nfid = cur.lastrowid
                    for p in conn.execute(
                        "SELECT name,description,fusion_data,source FROM presets WHERE folder_id=?", (fid,)
                    ).fetchall():
                        conn.execute(
                            "INSERT INTO presets (name,description,fusion_data,source,folder_id)"
                            " VALUES (?,?,?,?,?)",
                            (p["name"],p["description"],p["fusion_data"],p["source"],nfid)
                        )
                    conn.commit()
                    return json.dumps({"ok": True, "id": nfid})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def update_all_folders_style(self, style_str):
        """Cambia el estilo visual de todas las carpetas a la vez."""
        try:
            style = str(style_str).strip()[:10]
            if style not in ("tab", "solid"):
                return json.dumps({"ok": False, "error": "Estilo no válido"})
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute("UPDATE folders SET style = ?", (style,))
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Presets ───────────────────────────────────────────────────────────────
    @Slot(str, str, result=str)
    def get_folder_presets(self, folder_id_str, sort_mode):
        try:
            order = {"recent":"updated_at DESC","name_asc":"name ASC",
                     "name_desc":"name DESC","oldest":"created_at ASC"}.get(sort_mode,"updated_at DESC")
            with _db_lock:
                conn = _get_conn()
                try:
                    if folder_id_str == "all":
                        rows = conn.execute(
                            f"SELECT id,name,description,source,folder_id,created_at"
                            f" FROM presets ORDER BY {order}"
                        ).fetchall()
                    elif folder_id_str == "unorg":
                        rows = conn.execute(
                            f"SELECT id,name,description,source,folder_id,created_at"
                            f" FROM presets WHERE folder_id IS NULL ORDER BY {order}"
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            f"SELECT id,name,description,source,folder_id,created_at"
                            f" FROM presets WHERE folder_id=? ORDER BY {order}",
                            (int(folder_id_str),)
                        ).fetchall()
                    return json.dumps([dict(r) for r in rows])
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"error": str(e)})

    @Slot(str, str, str, result=str)
    def search_folder_presets(self, folder_id_str, query, sort_mode):
        try:
            q = query.strip()
            if not q:
                return self.get_folder_presets(folder_id_str, sort_mode)
            order = {"recent":"p.updated_at DESC","name_asc":"p.name ASC",
                     "name_desc":"p.name DESC","oldest":"p.created_at ASC"}.get(sort_mode,"p.updated_at DESC")

            def _san(s):
                for c in '"*():-+^\\': s = s.replace(c, " ")
                return s.strip()

            terms = [w for w in _san(q).split() if w]

            if folder_id_str == "all":
                fc, fp = "", []
            elif folder_id_str == "unorg":
                fc, fp = "AND p.folder_id IS NULL", []
            else:
                fc, fp = "AND p.folder_id = ?", [int(folder_id_str)]

            with _db_lock:
                conn = _get_conn()
                try:
                    if terms:
                        try:
                            fts = " ".join(w + "*" for w in terms)
                            rows = conn.execute(
                                f"SELECT p.id,p.name,p.description,p.source,p.folder_id,p.created_at"
                                f" FROM presets p WHERE p.id IN"
                                f" (SELECT rowid FROM presets_fts WHERE presets_fts MATCH ?)"
                                f" {fc} ORDER BY {order}",
                                [fts] + fp
                            ).fetchall()
                            return json.dumps([dict(r) for r in rows])
                        except Exception:
                            pass
                    pat = f"%{q}%"
                    rows = conn.execute(
                        f"SELECT id,name,description,source,folder_id,created_at FROM presets p"
                        f" WHERE (name LIKE ? OR description LIKE ?) {fc} ORDER BY {order}",
                        [pat, pat] + fp
                    ).fetchall()
                    return json.dumps([dict(r) for r in rows])
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"error": str(e)})

    @Slot(str, result=str)
    def save_preset(self, data_json):
        try:
            d    = json.loads(data_json)
            name = str(d.get("name", "")).strip()
            desc = str(d.get("description", "")).strip()
            fdat = str(d.get("fusion_data", "")).strip()
            src  = str(d.get("source", "clipboard"))
            fid  = d.get("folder_id")
            if not name: return json.dumps({"ok": False, "error": "El nombre es obligatorio"})
            if not fdat: return json.dumps({"ok": False, "error": "No hay datos de Fusion"})
            if fid is not None: fid = int(fid)
            with _db_lock:
                conn = _get_conn()
                try:
                    cur = conn.execute(
                        "INSERT INTO presets (name,description,fusion_data,source,folder_id)"
                        " VALUES (?,?,?,?,?)",
                        (name, desc, fdat, src, fid)
                    )
                    conn.commit()
                    return json.dumps({"ok": True, "id": cur.lastrowid})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def delete_preset(self, preset_id_str):
        try:
            pid = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute("DELETE FROM presets WHERE id=?", (pid,))
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, str, result=str)
    def move_preset_to_folder(self, preset_id_str, folder_id_str):
        try:
            pid = int(preset_id_str)
            fid = None if folder_id_str in ("null","unorg","all") else int(folder_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute(
                        "UPDATE presets SET folder_id=?,updated_at=datetime('now') WHERE id=?",
                        (fid, pid)
                    )
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, str, result=str)
    def move_all_to_folder(self, source_folder_id_str, target_folder_id_str):
        """Mueve todos los presets de una carpeta a otra."""
        try:
            fid = None if target_folder_id_str in ("null","unorg") else int(target_folder_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    if source_folder_id_str == "unorg":
                        conn.execute(
                            "UPDATE presets SET folder_id=?,updated_at=datetime('now')"
                            " WHERE folder_id IS NULL",
                            (fid,)
                        )
                    else:
                        conn.execute(
                            "UPDATE presets SET folder_id=?,updated_at=datetime('now')"
                            " WHERE folder_id=?",
                            (fid, int(source_folder_id_str))
                        )
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Nodos ─────────────────────────────────────────────────────────────────
    @Slot(result=str)
    def copy_nodes(self):
        try:
            text = clipboard_get_text()
            if not text or not text.strip():
                return json.dumps({"ok": False, "error": "Portapapeles vacío — Ctrl+C en Fusion primero"})
            return json.dumps({
                "ok": True, "data": text,
                "preview": text[:120].replace("\n", " "),
                "length": len(text),
            })
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def paste_nodes(self, preset_id_str):
        try:
            pid = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    row = conn.execute(
                        "SELECT fusion_data,name FROM presets WHERE id=?", (pid,)
                    ).fetchone()
                finally:
                    conn.close()
            if not row:
                return json.dumps({"ok": False, "error": "Preset no encontrado"})
            ok = clipboard_set_text(row["fusion_data"])
            if ok:
                return json.dumps({"ok": True, "msg": "Portapapeles listo — Ctrl+V en Fusion", "name": row["name"]})
            return json.dumps({"ok": False, "error": "No se pudo escribir en el portapapeles"})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def copy_text_to_clipboard(self, text):
        """Copia texto arbitrario al portapapeles del sistema (usado por el code modal)."""
        try:
            ok = clipboard_set_text(text)
            if ok:
                return json.dumps({"ok": True})
            return json.dumps({"ok": False, "error": "No se pudo escribir en el portapapeles"})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Código comprimido (share) ─────────────────────────────────────────────

    @Slot(str, result=str)
    def encode_preset(self, preset_id_str):
        """Comprime fusion_data en string MCOPY:... copiable."""
        try:
            import zlib, base64, struct
            pid = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    row = conn.execute(
                        "SELECT name, description, fusion_data FROM presets WHERE id=?", (pid,)
                    ).fetchone()
                finally:
                    conn.close()
            if not row:
                return json.dumps({"ok": False, "error": "Preset no encontrado"})

            payload = json.dumps({
                "n": row["name"],
                "d": row["description"],
                "f": row["fusion_data"],
            }, ensure_ascii=False, separators=(',', ':')).encode("utf-8")

            crc      = struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
            compressed = zlib.compress(crc + payload, level=9)
            code     = "MCOPY:" + base64.urlsafe_b64encode(compressed).decode("ascii")

            return json.dumps({"ok": True, "code": code, "chars": len(code)})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def decode_preset_code(self, code_str):
        """Decodifica un string MCOPY:... y devuelve los datos del preset."""
        try:
            import zlib, base64, struct
            code = code_str.strip()
            if not code.startswith("MCOPY:"):
                return json.dumps({"ok": False, "error": "Código inválido — debe empezar con MCOPY:"})
            b64   = code[6:]
            try:
                raw = zlib.decompress(base64.urlsafe_b64decode(b64))
            except Exception:
                return json.dumps({"ok": False, "error": "Código corrupto o inválido"})

            if len(raw) < 4:
                return json.dumps({"ok": False, "error": "Código demasiado corto"})

            crc_stored = struct.unpack(">I", raw[:4])[0]
            payload    = raw[4:]
            crc_calc   = zlib.crc32(payload) & 0xFFFFFFFF
            if crc_stored != crc_calc:
                return json.dumps({"ok": False, "error": "Checksum inválido — código dañado"})

            data = json.loads(payload.decode("utf-8"))
            return json.dumps({
                "ok":          True,
                "name":        data.get("n", "Preset importado"),
                "description": data.get("d", ""),
                "fusion_data": data.get("f", ""),
            })
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Import / Export ───────────────────────────────────────────────────────
    @Slot(str, result=str)
    def export_preset_data(self, preset_id_str):
        try:
            pid = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    r = conn.execute(
                        "SELECT name,description,fusion_data,source,created_at FROM presets WHERE id=?",
                        (pid,)
                    ).fetchone()
                    if not r: return json.dumps({"ok": False, "error": "Preset no encontrado"})
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
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def export_folder_data(self, folder_id_str):
        try:
            fid = int(folder_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    folder = conn.execute(
                        "SELECT name,color,icon,style FROM folders WHERE id=?", (fid,)
                    ).fetchone()
                    if not folder: return json.dumps({"ok": False, "error": "Carpeta no encontrada"})
                    presets = conn.execute(
                        "SELECT name,description,fusion_data,source FROM presets WHERE folder_id=?", (fid,)
                    ).fetchall()
                    payload = {
                        "version": 1, "type": "folder",
                        "name":    folder["name"],  "color": folder["color"],
                        "icon":    folder["icon"],  "style": folder["style"],
                        "presets": [dict(p) for p in presets],
                    }
                    return json.dumps({"ok": True, "data": json.dumps(payload, ensure_ascii=False, indent=2)})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, str, result=str)
    def save_export_file(self, filename, content):
        try:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(
                self._win, "Exportar",
                os.path.join(os.path.expanduser("~"), filename),
                "MCopy Files (*.mcopy)"
            )
            if not path: return json.dumps({"ok": False, "cancelled": True})
            if not path.endswith(".mcopy"): path += ".mcopy"
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(result=str)
    def open_import_dialog(self):
        try:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                self._win, "Importar .mcopy",
                os.path.expanduser("~"), "MCopy Files (*.mcopy)"
            )
            if not path: return json.dumps({"ok": False, "cancelled": True})
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps({"ok": True, "data": data})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, str, result=str)
    def import_mcopy(self, json_str, target_folder_id_str):
        try:
            d     = json.loads(json_str) if isinstance(json_str, str) else json_str
            dtype = d.get("type", "preset")
            if d.get("version", 1) != 1:
                return json.dumps({"ok": False, "error": "Version no soportada"})
            with _db_lock:
                conn = _get_conn()
                try:
                    if dtype == "preset":
                        fid = None if target_folder_id_str in ("null","unorg","all") else int(target_folder_id_str)
                        cur = conn.execute(
                            "INSERT INTO presets (name,description,fusion_data,source,folder_id)"
                            " VALUES (?,?,?,?,?)",
                            (d.get("name","Preset importado"), d.get("description",""),
                             d.get("fusion_data",""), d.get("source","clipboard"), fid)
                        )
                        conn.commit()
                        return json.dumps({"ok": True, "type": "preset", "id": cur.lastrowid})
                    elif dtype == "folder":
                        cur = conn.execute(
                            "INSERT INTO folders (name,color,icon,style) VALUES (?,?,?,?)",
                            (d.get("name","Carpeta importada"), d.get("color","#f5c842"),
                             d.get("icon","folder"), d.get("style","tab"))
                        )
                        nfid = cur.lastrowid
                        for p in d.get("presets", []):
                            conn.execute(
                                "INSERT INTO presets (name,description,fusion_data,source,folder_id)"
                                " VALUES (?,?,?,?,?)",
                                (p.get("name",""), p.get("description",""),
                                 p.get("fusion_data",""), p.get("source","clipboard"), nfid)
                            )
                        conn.commit()
                        return json.dumps({"ok": True, "type": "folder", "id": nfid})
                    return json.dumps({"ok": False, "error": "Tipo no reconocido"})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
from PySide6.QtWidgets          import QMainWindow, QSizeGrip
from PySide6.QtWebEngineWidgets  import QWebEngineView
from PySide6.QtWebEngineCore     import QWebEngineScript, QWebEngineSettings
from PySide6.QtWebChannel        import QWebChannel
from PySide6.QtCore              import Qt, QUrl, QTimer
from PySide6.QtGui               import QIcon


class MCopyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MCopy")
        self.setMinimumSize(820, 560)
        _s = _load_settings()
        self.resize(
            max(820, int(_s.get("window_w", 980))),
            max(560, int(_s.get("window_h", 650))),
        )
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)

        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        self._channel = QWebChannel()
        self._backend = Backend(self)
        self._channel.registerObject("backend", self._backend)
        self._view.page().setWebChannel(self._channel)

        # GPU + aceleracion WebEngine
        _ws = self._view.page().settings()
        _ws.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        _ws.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)

        # Inyectar qwebchannel.js (fix Qt 6.7+)
        script = QWebEngineScript()
        script.setSourceUrl(QUrl("qrc:/qtwebchannel/qwebchannel.js"))
        script.setName("mcopy-qwebchannel")
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        self._view.page().scripts().insert(script)

        # SizeGrip para redimensionar
        self._grip = QSizeGrip(self)
        self._grip.resize(14, 14)
        self._grip.setStyleSheet("background: transparent;")
        self._grip.raise_()

        if os.path.isfile(_UI_FILE):
            self._view.setUrl(QUrl.fromLocalFile(_UI_FILE))
        else:
            self._view.setHtml(
                "<body style='background:#0a0a0a;color:#e05c5c;font-family:monospace;padding:24px'>"
                "<h2>ui.html no encontrado</h2><p>" + _UI_FILE + "</p></body>"
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grip.move(self.width() - 15, self.height() - 15)
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._save_size)
        self._resize_timer.start(700)

    def _save_size(self):
        try:
            s = _load_settings()
            s["window_w"] = self.width()
            s["window_h"] = self.height()
            _persist_settings(s)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
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
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    window = MCopyWindow()
    window.show()
    sys.exit(app.exec())
