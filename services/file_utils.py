from __future__ import annotations
from PIL import Image
from pathlib import Path
from datetime import datetime, timedelta
from services.logger import log_queue, log
from typing import Set, List, Tuple, Optional
from config import INPUT_ROOT, WORK_ROOT, OUTPUT_ROOT
from dataclasses import dataclass, asdict

import tempfile
import fitz  # PyMuPDF
import os
import json
import time
import shutil
import re
import img2pdf
import logging

logger = logging.getLogger(__name__)


def _rmtree_cifs(path: Path, verbose: bool = False) -> bool:
    """
    Löscht Verzeichnis rekursiv, CIFS/SMB-kompatibel.

    Versucht mehrere Strategien:
    1. Normales shutil.rmtree mit Berechtigungsanpassung
    2. Manuelles Löschen aller Dateien, dann Unterverzeichnisse
    3. Windows-spezifische rd-Kommando (falls verfügbar)

    Args:
        path: Pfad zum zu löschenden Verzeichnis
        verbose: Wenn True, werden Details geloggt

    Returns:
        True wenn erfolgreich gelöscht
    """
    import stat
    import platform

    if not path.exists():
        return True

    # Strategie 1: Standard shutil.rmtree mit Berechtigungsanpassung
    # WICHTIG: Der onexc-Handler muss ORIGINALE os-Funktionen nutzen!
    def _onexc(*args):
        # args = (func, fpath, exc_info) aber wir brauchen nur fpath
        fpath = args[1] if len(args) > 1 else None
        if not fpath:
            return

        try:
            # Versuche Berechtigungen zu setzen
            os.chmod(fpath, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)

            # Nutze ORIGINALE Funktionen statt der gepatchten
            if os.path.isfile(fpath) or os.path.islink(fpath):
                _os_unlink_original(fpath)
            elif os.path.isdir(fpath):
                _os_rmdir_original(fpath)
        except Exception as e:
            if verbose:
                log(f"   ⚠️ onexc-Handler fehlgeschlagen für {fpath}: {e}", level="debug")

    try:
        shutil.rmtree(str(path), onexc=_onexc)
        if not path.exists():
            return True
    except Exception as e:
        if verbose:
            log(f"   ⚠️ shutil.rmtree fehlgeschlagen: {e}", level="debug")

    # Strategie 2: Manuelles rekursives Löschen mit ORIGINALEN os-Funktionen
    # WICHTIG: Nutze _os_*_original um das Staging-System zu umgehen!
    try:
        # Sammle alle Dateien und Verzeichnisse
        all_files = []
        all_dirs = []

        for item in path.rglob('*'):
            if item.is_file() or item.is_symlink():
                all_files.append(item)
            elif item.is_dir():
                all_dirs.append(item)

        # Lösche zuerst alle Dateien
        for item in all_files:
            try:
                try:
                    os.chmod(str(item), stat.S_IWRITE)
                except:
                    pass
                # Nutze ORIGINALE unlink-Funktion, nicht die gepatchte!
                _os_unlink_original(str(item))
            except Exception as e:
                if verbose:
                    log(f"   ⚠️ Fehler beim Löschen von Datei {item.name}: {e}", level="debug")

        # Lösche Verzeichnisse von innen nach außen (tiefste zuerst)
        for item in sorted(all_dirs, key=lambda p: len(str(p)), reverse=True):
            try:
                try:
                    os.chmod(str(item), stat.S_IWRITE | stat.S_IEXEC)
                except:
                    pass
                # Nutze ORIGINALE rmdir-Funktion, nicht die gepatchte!
                _os_rmdir_original(str(item))
            except Exception as e:
                if verbose:
                    log(f"   ⚠️ Fehler beim Löschen von Verzeichnis {item.name}: {e}", level="debug")

        # Hauptverzeichnis löschen
        try:
            os.chmod(str(path), stat.S_IWRITE | stat.S_IEXEC)
        except:
            pass
        # Nutze ORIGINALE rmdir-Funktion
        _os_rmdir_original(str(path))

        if not path.exists():
            return True
    except Exception as e:
        if verbose:
            log(f"   ⚠️ Manuelles Löschen fehlgeschlagen: {e}", level="debug")

    # Strategie 3: Windows-spezifisch - verwende rd-Kommando
    if platform.system() == 'Windows':
        try:
            import subprocess
            result = subprocess.run(
                ['cmd', '/c', 'rd', '/s', '/q', str(path)],
                capture_output=True,
                timeout=30
            )
            if not path.exists():
                return True
            if verbose and result.returncode != 0:
                log(f"   ⚠️ rd-Kommando fehlgeschlagen: {result.stderr.decode('utf-8', errors='ignore')}", level="debug")
        except Exception as e:
            if verbose:
                log(f"   ⚠️ Windows rd-Kommando fehlgeschlagen: {e}", level="debug")

    # Letzte Prüfung
    return not path.exists()


# Speichere originale os-Funktionen BEVOR sie von app.py gepatcht werden
_os_remove_original = os.remove
_os_rename_original = os.rename
_os_unlink_original = os.unlink
_os_rmdir_original = os.rmdir

# ============================================================================
# DATACLASSES
# ============================================================================
@dataclass
class RenameOp:
    src_rel: str
    dst_rel: str
    kind: str = "rename"

@dataclass
class DeleteOp:
    target_rel: str
    kind: str = "delete"

@dataclass
class MergeOp:
    inputs_rel: list[str]
    output_rel: str
    kind: str = "merge"

# ============================================================================
# SESSION REGISTRY
# ============================================================================
class SessionRegistry:
    """Verwaltet aktive Sessions und deren Zeitstempel."""
    
    def __init__(self, registry_path: Path):
        self.registry_path = registry_path
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self) -> dict:
        if not self.registry_path.exists():
            return {}
        try:
            with open(self.registry_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save(self, data: dict):
        with open(self.registry_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def register(self, session_id: str):
        registry = self._load()
        registry[session_id] = {
            'started': time.time(),
            'last_activity': time.time()
        }
        self._save(registry)
        logger.info(f"Session registriert: {session_id}")
    
    def update_activity(self, session_id: str):
        registry = self._load()
        if session_id in registry:
            registry[session_id]['last_activity'] = time.time()
            self._save(registry)
    
    def unregister(self, session_id: str):
        registry = self._load()
        if session_id in registry:
            del registry[session_id]
            self._save(registry)
            logger.info(f"Session unregistriert: {session_id}")
    
    def get_active_sessions(self, timeout_minutes: int = 30) -> Set[str]:
        registry = self._load()
        cutoff = time.time() - (timeout_minutes * 60)
        active = set()
        
        for session_id, data in registry.items():
            if data.get('last_activity', 0) > cutoff:
                active.add(session_id)
        
        return active
    
    def cleanup_stale_sessions(self, timeout_minutes: int = 30) -> Set[str]:
        registry = self._load()
        cutoff = time.time() - (timeout_minutes * 60)
        stale = set()
        
        for session_id, data in list(registry.items()):
            if data.get('last_activity', 0) <= cutoff:
                stale.add(session_id)
                del registry[session_id]
        
        if stale:
            self._save(registry)
            logger.info(f"Abgelaufene Sessions entfernt: {len(stale)}")
        
        return stale

# ============================================================================
# CLEANUP FUNCTIONS
# ============================================================================
def cleanup_orphaned_files(work_root: Path, output_root: Path, 
                           active_sessions: Set[str]) -> dict:
    """
    Bereinigt verwaiste Dateien aus Work- und Output-Verzeichnissen.
    
    Args:
        work_root: Pfad zum Staging-Root (z.B. /app/medidok/staging)
        output_root: Pfad zum Output-Root (z.B. /app/medidok/output)
        active_sessions: Set mit aktiven Session-IDs
    
    Returns:
        Dict mit Statistiken über gelöschte Dateien
    """
    stats = {
        'work_dirs_removed': 0,
        'work_files_removed': 0,
        'staging_files_removed': 0,
        'errors': []
    }
    
    # Sicherstellen, dass work_root und output_root Path-Objekte sind
    work_root = Path(work_root)
    output_root = Path(output_root)
    
    log(f"🔍 Cleanup: work_root={work_root}, output_root={output_root}")
    log(f"🔍 Cleanup: {len(active_sessions)} aktive Sessions: {active_sessions}")
    
    # 1. Work-Verzeichnisse aufräumen
    if work_root.exists():
        log(f"📂 Prüfe Work-Verzeichnis: {work_root}")
        try:
            # Alle Session-Verzeichnisse auflisten
            session_dirs = [d for d in work_root.iterdir() if d.is_dir()]
            log(f"   Gefundene Session-Verzeichnisse: {len(session_dirs)}")
            
            for session_dir in session_dirs:
                session_id = session_dir.name

                if session_id not in active_sessions:
                    try:
                        file_count = sum(1 for f in session_dir.rglob('*') if f.is_file())
                        log(f"   🗑️ Lösche Session-Verzeichnis: {session_id} ({file_count} Dateien)")

                        if _rmtree_cifs(session_dir):
                            stats['work_dirs_removed'] += 1
                            stats['work_files_removed'] += file_count
                        else:
                            stats['errors'].append(f"Work-Dir {session_id}: nicht vollständig gelöscht")
                            log(f"   ⚠️ Nicht vollständig gelöscht: {session_id}", level="warning")
                    except Exception as e:
                        error_msg = f"Work-Dir {session_id}: {e}"
                        stats['errors'].append(error_msg)
                        log(f"   ❌ {error_msg}", level="warning")
                else:
                    log(f"   ✅ Behalte aktive Session: {session_id}")
        except Exception as e:
            error_msg = f"Fehler beim Scannen von work_root: {e}"
            stats['errors'].append(error_msg)
            log(f"❌ {error_msg}", level="error")
    else:
        log(f"⚠️ Work-Root existiert nicht: {work_root}")
    
    # 2. Output/Staging-Dateien aufräumen (nur wenn KEINE aktiven Sessions)
    if output_root.exists() and not active_sessions:
        log(f"📂 Prüfe Output-Verzeichnis: {output_root}")
        cutoff = datetime.now() - timedelta(hours=24)
        
        try:
            # Alle Dateien im Output-Verzeichnis
            all_files = [f for f in output_root.rglob('*') if f.is_file()]
            log(f"   Gefundene Dateien: {len(all_files)}")
            
            for item in all_files:
                try:
                    mtime = datetime.fromtimestamp(item.stat().st_mtime)
                    
                    # Nur alte Dateien löschen
                    if mtime < cutoff:
                        log(f"   🗑️ Lösche alte Staging-Datei: {item.name} (von {mtime.strftime('%Y-%m-%d %H:%M')})")
                        item.unlink()
                        stats['staging_files_removed'] += 1
                    else:
                        log(f"   ⏳ Behalte neuere Datei: {item.name}")
                except Exception as e:
                    error_msg = f"Staging {item.name}: {e}"
                    stats['errors'].append(error_msg)
                    log(f"   ❌ {error_msg}", level="warning")
        except Exception as e:
            error_msg = f"Fehler beim Scannen von output_root: {e}"
            stats['errors'].append(error_msg)
            log(f"❌ {error_msg}", level="error")
    elif active_sessions:
        log(f"⏭️ Überspringe Output-Cleanup: {len(active_sessions)} aktive Sessions")
    else:
        log(f"⚠️ Output-Root existiert nicht: {output_root}")
    
    return stats

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def sanitize_filename(name):
    # Entfernt nur ungültige Dateisystem-Zeichen und Unterstriche (da _ als Trennzeichen dient)
    # Leerzeichen, Kommas und Punkte bleiben erhalten
    name = re.sub(r'[\\/:"*?<>|]', '', name)
    name = name.replace('_', '')
    return name.strip()
    
def safe_line(lines, index, fallback):
    try:
        line = lines[index]
    except IndexError:
        return fallback
    if line is None:
        return fallback
    line = str(line).strip()
    return line if line else fallback

def build_absender(fachrichtung: str, name: str) -> str:
    """Baut Absender immer als [Fachrichtung] [Name]."""
    fachrichtung = fachrichtung.strip()
    name = name.strip()

    if fachrichtung and name:
        return f"{fachrichtung} {name}"
    elif fachrichtung:
        return fachrichtung
    elif name:
        return name
    else:
        return "Kein Arzt erkannt"

def handle_successful_processing(summary_data, original_path, target_dir):
    feld1 = sanitize_filename(summary_data.get("name", "Unbekannt"))
    feld2 = sanitize_filename(summary_data.get("vorname", "Unbekannt"))
    feld3 = sanitize_filename(summary_data.get("geburtsdatum", "Unbekannt"))
    feld4 = sanitize_filename(summary_data.get("datum", "Unbekannt"))
    feld5 = sanitize_filename(summary_data.get("beschreibung1", "Unbekannt"))[:30]
    feld7 = sanitize_filename(summary_data.get("categoryID", "11"))

    # Windows-Pfadlängen-Limit: f:\MDok\import\Dateiname.pdf
    # Max 115 Zeichen für Dateiname (inkl. .pdf) - optimiertes Limit
    MAX_FILENAME_LENGTH = 115

    # Berechne Länge aller Teile außer feld6 (Befund)
    prefix = f"{feld1}_{feld2}_{feld3}_{feld4}_{feld5}, "
    suffix = f"_{feld7}.pdf"
    prefix_suffix_length = len(prefix) + len(suffix)

    # Berechne maximale Länge für feld6 (Befund)
    max_feld6_length = MAX_FILENAME_LENGTH - prefix_suffix_length

    # Stelle sicher, dass mindestens 10 Zeichen für Befund bleiben
    if max_feld6_length < 10:
        max_feld6_length = 10

    # Kürze feld6 auf verfügbare Länge
    feld6 = sanitize_filename(summary_data.get("beschreibung2", "Unbekannt"))[:max_feld6_length]

    new_filename = f"{feld1}_{feld2}_{feld3}_{feld4}_{feld5}, {feld6}_{feld7}.pdf"

    log(f"🔍 DEBUG handle_successful_processing:")
    log(f"   feld1={repr(feld1)}, feld2={repr(feld2)}")
    log(f"   new_filename={repr(new_filename)}")
    log(f"   Enthält Unterstriche: {'_' in new_filename}")

    if os.path.isabs(original_path):
        rel_src = to_rel_under_input(original_path)
        if not rel_src:
            rel_src = summary_data.get("file", os.path.basename(original_path))
    else:
        rel_src = original_path

    rel_dir = os.path.dirname(rel_src) if "/" in rel_src else ""
    rel_dst = os.path.join(rel_dir, new_filename) if rel_dir else new_filename

    fs.plan_rename(rel_src, rel_dst)

    return {
        "original": os.path.basename(original_path),
        "renamed": new_filename,
        "summary": summary_data
    }

def cleanup_old_json_files(folder, days_old=1):
    """Löscht alte JSON-Dateien und gibt Statistik zurück."""
    if not os.path.exists(folder):
        log(f"⚠️ JSON-Ordner existiert nicht: {folder}")
        return 0

    cutoff = datetime.now() - timedelta(days=days_old)
    deleted_count = 0

    for filename in os.listdir(folder):
        if filename.endswith(".json"):
            file_path = os.path.join(folder, filename)
            try:
                modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if modified_time < cutoff:
                    # Verwende originale os.remove (umgeht das Staging-System)
                    _os_remove_original(file_path)
                    deleted_count += 1
                    log(f"🗑️ Alte control.json gelöscht: {filename}")
            except Exception as e:
                log(f"⚠️ Fehler beim Löschen von {filename}: {e}", level="warning")

    if deleted_count > 0:
        log(f"✅ {deleted_count} alte control.json-Dateien aufgeräumt")
    else:
        log(f"ℹ️ Keine alten JSON-Dateien zum Löschen gefunden")

    return deleted_count

# ============================================================================
# STAGING SESSION
# ============================================================================
class StagingSession:
    def __init__(self):
        self.input_root  = Path(INPUT_ROOT)
        self.work_root   = Path(WORK_ROOT)
        self.output_root = Path(OUTPUT_ROOT)
        self.session_id: str | None = None
        self.ops: list[dict] = []

    @property
    def work_dir(self) -> Path:
        if not self.session_id:
            raise RuntimeError("No active session")
        return self.work_root / self.session_id / "staging"

    @property
    def meta_file(self) -> Path:
        if not self.session_id:
            raise RuntimeError("No active session")
        return self.work_root / self.session_id / "manifest.json"

    def _save(self):
        self.meta_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump({"ops": self.ops}, f, ensure_ascii=False, indent=2)

    def start(self, session_id: str):
        self.session_id = session_id
        self.ops = []
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._save()
        logger.info("Staging session %s started", session_id)

    def abort(self):
        if not self.session_id:
            return

        if self.work_dir.exists():
            _rmtree_cifs(self.work_dir)

        self.meta_file.unlink(missing_ok=True)
        logger.info("Staging session %s aborted", self.session_id)
        self.session_id = None
        self.ops = []

    def commit(self):
        for op in self.ops:
            if op.get("kind") != "rename":
                continue
            src_rel = op["src_rel"]
            dst_rel = op["dst_rel"]

            staged_src = self.work_dir / src_rel
            final_dst = self.output_root / dst_rel
            final_dst.parent.mkdir(parents=True, exist_ok=True)

            if staged_src.exists():
                os.replace(staged_src, final_dst)
            else:
                logger.warning(f"Commit rename: Quelle nicht gefunden: {src_rel}")

        for op in self.ops:
            if op.get("kind") == "delete":
                target = self.input_root / op["target_rel"]
                if target.exists():
                    target.unlink()

        for op in self.ops:
            if op.get("kind") == "merge":
                staged_out = self.work_dir / op["output_rel"]
                final_out = self.output_root / op["output_rel"]
                final_out.parent.mkdir(parents=True, exist_ok=True)
                if staged_out.exists():
                    os.replace(staged_out, final_out)

        if self.work_dir.exists():
            _rmtree_cifs(self.work_dir)

        self.meta_file.unlink(missing_ok=True)
        logger.info(f"Staging session {self.session_id} committed")
        self.session_id = None
        self.ops = []

    def plan_rename(self, src_rel: str, dst_rel: str):
        self.ops.append(asdict(RenameOp(src_rel, dst_rel)))
        self._save()

    def plan_delete(self, rel_path: str):
        self.ops.append(asdict(DeleteOp(rel_path)))
        self._save()

    def plan_merge(self, inputs_rel: list[str], output_rel: str):
        self.ops.append(asdict(MergeOp(inputs_rel, output_rel)))
        self._save()

    def link_or_copy_to_staging(self, rel_path: str):
        src = self.input_root / rel_path
        dst = self.work_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)
        except Exception:
            shutil.copy2(src, dst)

    def merge_in_staging(self, inputs_rel: list[str], output_rel: str):
        """Merged PDFs mit Ghostscript"""
        import subprocess
        
        if not self.session_id:
            raise RuntimeError("Keine aktive Session")
        
        source_paths = [str(self.input_root / r) for r in inputs_rel]
        out_path = self.work_dir / output_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        cmd = ['gs', '-dBATCH', '-dNOPAUSE', '-q', '-sDEVICE=pdfwrite', 
               '-dPDFSETTINGS=/prepress', f'-sOutputFile={out_path}'] + source_paths
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and out_path.exists():
            test = fitz.open(str(out_path))
            page_count = test.page_count
            test.close()
            log(f"✅ Merge erfolgreich: {page_count} Seiten")
        else:
            log(f"❌ Ghostscript Fehler: {result.stderr}", level="error")
            raise RuntimeError(f"PDF Merge fehlgeschlagen: {result.stderr}")

    def preview_listing(self) -> list[str]:
        existing = {
            p.relative_to(self.input_root).as_posix()
            for p in self.input_root.rglob("*") if p.is_file()
        }
        for op in self.ops:
            if op["kind"] == "rename":
                existing.discard(op["src_rel"])
                existing.add(op["dst_rel"])
            elif op["kind"] == "delete":
                existing.discard(op["target_rel"])
            elif op["kind"] == "merge":
                existing.add(op["output_rel"])
        return sorted(existing)
    
    def list_staged_files(self) -> list[str]:
        """Gibt Liste aller Dateien im aktuellen Staging zurück."""
        if not self.session_id or not self.work_dir.exists():
            return []
        
        files = []
        for item in self.work_dir.rglob('*'):
            if item.is_file():
                rel_path = item.relative_to(self.work_dir).as_posix()
                files.append(rel_path)
        
        return sorted(files)

# Globale Instanz
fs = StagingSession()

# ============================================================================
# PATH UTILITIES
# ============================================================================
def to_rel_under_input(path: str | Path) -> str | None:
    if not os.path.isabs(path):
        return Path(path).as_posix()

    p = Path(path).resolve()
    in_root = Path(INPUT_ROOT).resolve()

    try:
        return p.relative_to(in_root).as_posix()
    except Exception:
        pass

    if fs.session_id:
        try:
            return p.relative_to(fs.work_dir.resolve()).as_posix()
        except Exception:
            pass

    return None

def _to_rel_dir_under_input(abs_dir: str | Path) -> Optional[str]:
    p = Path(abs_dir).resolve()
    root = Path(INPUT_ROOT).resolve()
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        logger.warning("Dir %s not under INPUT_ROOT %s", p, root)
        return None