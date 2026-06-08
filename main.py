"""
main.py — MCopy
Herramienta de presets de nodos Fusion para DaVinci Resolve.
MMarket Ecosystem — https://mmarket.dev
"""

import sys
import os

# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 0 — Rutas base (frozen vs desarrollo)
# ══════════════════════════════════════════════════════════════════════════════
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
    get_appdata_dir,
    get_resolve_module_paths,
    clipboard_get_text,
    clipboard_set_text,
)

# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 1 — Constantes
# ══════════════════════════════════════════════════════════════════════════════
_OS = platform.system()

APPDATA       = get_appdata_dir()
DATA_DIR      = os.path.join(APPDATA, "MMarket", "Apps", "MCopy")
DB_FILE       = os.path.join(DATA_DIR, "presets.db")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
_UI_FILE      = os.path.join(_BUNDLE_DIR, "ui.html")

os.makedirs(DATA_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 2 — Base de datos SQLite con FTS5
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
                CREATE TABLE IF NOT EXISTS presets (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    NOT NULL,
                    description TEXT    DEFAULT '',
                    fusion_data TEXT    NOT NULL,
                    source      TEXT    DEFAULT 'clipboard',
                    created_at  TEXT    DEFAULT (datetime('now')),
                    updated_at  TEXT    DEFAULT (datetime('now'))
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS presets_fts USING fts5(
                    name, description,
                    content='presets',
                    content_rowid='id'
                );

                CREATE TRIGGER IF NOT EXISTS presets_ai
                AFTER INSERT ON presets BEGIN
                    INSERT INTO presets_fts(rowid, name, description)
                    VALUES (new.id, new.name, new.description);
                END;

                CREATE TRIGGER IF NOT EXISTS presets_ad
                AFTER DELETE ON presets BEGIN
                    INSERT INTO presets_fts(presets_fts, rowid, name, description)
                    VALUES ('delete', old.id, old.name, old.description);
                END;

                CREATE TRIGGER IF NOT EXISTS presets_au
                AFTER UPDATE ON presets BEGIN
                    INSERT INTO presets_fts(presets_fts, rowid, name, description)
                    VALUES ('delete', old.id, old.name, old.description);
                    INSERT INTO presets_fts(rowid, name, description)
                    VALUES (new.id, new.name, new.description);
                END;
            """)
            conn.commit()
        finally:
            conn.close()


_init_db()

# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 3 — Settings
# ══════════════════════════════════════════════════════════════════════════════
_DEFAULT_SETTINGS = {
    "theme":  "mmarket",
    "accent": "#f5c842",
    "font":   "barlow",
    "mode":   "clipboard",
    "lang":   "es",
}


def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(_DEFAULT_SETTINGS)
        merged.update({k: v for k, v in data.items() if k in _DEFAULT_SETTINGS})
        return merged
    except Exception:
        return dict(_DEFAULT_SETTINGS)


def _persist_settings(data: dict) -> bool:
    try:
        safe = {
            "theme":  str(data.get("theme",  "mmarket"))[:24],
            "accent": str(data.get("accent", "#f5c842"))[:24],
            "font":   str(data.get("font",   "barlow"))[:24],
            "mode":   str(data.get("mode",   "clipboard"))[:24],
            "lang":   str(data.get("lang",   "es"))[:8],
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(safe, f, indent=2)
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 4 — Resolve scripting (Pro — stub para futura implementación)
# ══════════════════════════════════════════════════════════════════════════════
def _try_get_resolve():
    """Intenta conectarse a DaVinci Resolve vía scripting API."""
    for path in get_resolve_module_paths():
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    try:
        import DaVinciResolveScript as dvr
        resolve = dvr.scriptapp("Resolve")
        if not resolve:
            return None, None
        pm   = resolve.GetProjectManager()
        proj = pm.GetCurrentProject() if pm else None
        if not proj:
            return resolve, None
        fusion = proj.GetCurrentTimeline()
        return resolve, fusion
    except Exception:
        return None, None


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 5 — Backend QObject
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
            if h:
                h.startSystemMove()
        except Exception:
            pass

    @Slot()
    def minimize_window(self):
        try:
            self._win.showMinimized()
        except Exception:
            pass

    @Slot()
    def close_window(self):
        try:
            self._win.close()
        except Exception:
            pass

    # ── Settings ─────────────────────────────────────────────────────────────

    @Slot(result=str)
    def get_settings(self):
        return json.dumps(_load_settings())

    @Slot(str, result=str)
    def save_settings(self, data_json):
        try:
            data = json.loads(data_json)
            ok   = _persist_settings(data)
            return json.dumps({"ok": ok})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Presets — lectura ────────────────────────────────────────────────────

    @Slot(result=str)
    def get_presets(self):
        try:
            with _db_lock:
                conn = _get_conn()
                try:
                    rows = conn.execute(
                        "SELECT id, name, description, source, created_at "
                        "FROM presets ORDER BY updated_at DESC"
                    ).fetchall()
                    return json.dumps([dict(r) for r in rows])
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"error": str(e)})

    @Slot(str, result=str)
    def search_presets(self, query):
        try:
            q = query.strip()
            if not q:
                return self.get_presets()

            # Sanear caracteres especiales de FTS5
            def _sanitize(s):
                for ch in '"*():-+^\\':
                    s = s.replace(ch, " ")
                return s.strip()

            safe  = _sanitize(q)
            terms = [w for w in safe.split() if w]

            with _db_lock:
                conn = _get_conn()
                try:
                    # Intentar FTS5 con prefijo (ej. "glow*")
                    if terms:
                        try:
                            fts_q = " ".join(w + "*" for w in terms)
                            rows  = conn.execute(
                                "SELECT id, name, description, source, created_at "
                                "FROM presets WHERE id IN "
                                "(SELECT rowid FROM presets_fts WHERE presets_fts MATCH ?) "
                                "ORDER BY updated_at DESC",
                                (fts_q,),
                            ).fetchall()
                            return json.dumps([dict(r) for r in rows])
                        except Exception:
                            pass  # FTS falló → usar LIKE

                    # Fallback LIKE (siempre funciona)
                    pattern = "%" + q + "%"
                    rows = conn.execute(
                        "SELECT id, name, description, source, created_at FROM presets "
                        "WHERE name LIKE ? OR description LIKE ? "
                        "ORDER BY updated_at DESC",
                        (pattern, pattern),
                    ).fetchall()
                    return json.dumps([dict(r) for r in rows])
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Presets — escritura ──────────────────────────────────────────────────

    @Slot(str, result=str)
    def save_preset(self, data_json):
        try:
            data        = json.loads(data_json)
            name        = str(data.get("name", "")).strip()
            description = str(data.get("description", "")).strip()
            fusion_data = str(data.get("fusion_data", "")).strip()
            source      = str(data.get("source", "clipboard"))

            if not name:
                return json.dumps({"ok": False, "error": "El nombre es obligatorio"})
            if not fusion_data:
                return json.dumps({"ok": False, "error": "No hay datos de Fusion para guardar"})

            with _db_lock:
                conn = _get_conn()
                try:
                    cur = conn.execute(
                        "INSERT INTO presets (name, description, fusion_data, source) "
                        "VALUES (?, ?, ?, ?)",
                        (name, description, fusion_data, source),
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
            preset_id = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    conn.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
                    conn.commit()
                    return json.dumps({"ok": True})
                finally:
                    conn.close()
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Nodos — portapapeles ─────────────────────────────────────────────────

    @Slot(result=str)
    def copy_nodes(self):
        """Lee el portapapeles y devuelve los datos de Fusion al JS."""
        try:
            text = clipboard_get_text()
            if not text or not text.strip():
                return json.dumps({"ok": False, "error": "Portapapeles vacío — usa Ctrl+C en Fusion primero"})
            preview = text[:120].replace("\n", " ")
            return json.dumps({
                "ok":      True,
                "data":    text,
                "preview": preview,
                "length":  len(text),
            })
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    @Slot(str, result=str)
    def paste_nodes(self, preset_id_str):
        """Escribe el fusion_data del preset en el portapapeles."""
        try:
            preset_id = int(preset_id_str)
            with _db_lock:
                conn = _get_conn()
                try:
                    row = conn.execute(
                        "SELECT fusion_data, name FROM presets WHERE id = ?", (preset_id,)
                    ).fetchone()
                finally:
                    conn.close()

            if not row:
                return json.dumps({"ok": False, "error": "Preset no encontrado"})

            ok = clipboard_set_text(row["fusion_data"])
            if ok:
                return json.dumps({
                    "ok":  True,
                    "msg": "Portapapeles listo — usa Ctrl+V en Fusion",
                    "name": row["name"],
                })
            return json.dumps({"ok": False, "error": "No se pudo escribir en el portapapeles"})

        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 6 — Ventana principal
# ══════════════════════════════════════════════════════════════════════════════
from PySide6.QtWidgets         import QMainWindow, QSizeGrip
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore   import QWebEngineScript
from PySide6.QtWebChannel      import QWebChannel
from PySide6.QtCore            import Qt, QUrl
from PySide6.QtGui             import QIcon


class MCopyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MCopy")
        self.setMinimumSize(820, 560)
        self.resize(980, 650)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)

        # ── WebEngineView ────────────────────────────────────────────────────
        self._view = QWebEngineView(self)
        self.setCentralWidget(self._view)

        # ── QWebChannel ──────────────────────────────────────────────────────
        self._channel = QWebChannel()
        self._backend = Backend(self)
        self._channel.registerObject("backend", self._backend)
        self._view.page().setWebChannel(self._channel)

        # ── Aceleración GPU en WebEngine ─────────────────────────────────────
        from PySide6.QtWebEngineCore import QWebEngineSettings
        _ws = self._view.page().settings()
        _ws.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        _ws.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)

        # ── Inyectar qwebchannel.js en DocumentCreation (fix Qt 6.7+) ───────
        script = QWebEngineScript()
        script.setSourceUrl(QUrl("qrc:/qtwebchannel/qwebchannel.js"))
        script.setName("mcopy-qwebchannel")
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        self._view.page().scripts().insert(script)

        # ── SizeGrip para redimensionar ventana frameless ────────────────────
        self._grip = QSizeGrip(self)
        self._grip.resize(14, 14)
        self._grip.setStyleSheet("background: transparent;")
        self._grip.raise_()

        # ── Cargar UI ────────────────────────────────────────────────────────
        if os.path.isfile(_UI_FILE):
            self._view.setUrl(QUrl.fromLocalFile(_UI_FILE))
        else:
            self._view.setHtml(
                "<body style='background:#0a0a0a;color:#e05c5c;"
                "font-family:monospace;padding:24px'>"
                "<h2>ui.html no encontrado</h2>"
                "<p>Ruta esperada: " + _UI_FILE + "</p></body>"
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grip.move(self.width() - 15, self.height() - 15)


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 7 — Punto de entrada
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # ── GPU / HiDPI — deben configurarse ANTES de QApplication ──────────────
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--enable-gpu-rasterization "
        "--enable-zero-copy "
        "--ignore-gpu-blocklist "
        "--enable-oop-rasterization",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("MCopy")
    app.setOrganizationName("MMarket")
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    window = MCopyWindow()
    window.show()
    sys.exit(app.exec())
