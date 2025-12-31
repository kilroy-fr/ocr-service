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

# Speichere originale os-Funktionen BEVOR sie von app.py gepatcht werden
_os_remove_original = os.remove
_os_rename_original = os.rename

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
        work_root: Pfad zum Work-Root (z.B. /app/medidok/work)
        output_root: Pfad zum Output-Root (z.B. /app/medidok/staging)
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
                
                # Wenn Session nicht aktiv -> löschen
                if session_id not in active_sessions:
                    try:
                        # Dateien zählen
                        file_count = sum(1 for _ in session_dir.rglob('*') if _.is_file())

                        log(f"   🗑️ Lösche Session-Verzeichnis: {session_id} ({file_count} Dateien)")

                        # Netzlaufwerk-Kompatibilität: rmtree hat Probleme mit dir_fd auf CIFS
                        # Lösung: Manuelles Löschen statt shutil.rmtree()
                        def remove_readonly(func, path, exc_info):
                            """Entferne Read-Only-Attribut und versuche erneut"""
                            import stat
                            os.chmod(path, stat.S_IWRITE)
                            func(path)

                        # Erst alle Dateien löschen, dann Verzeichnisse von unten nach oben
                        for item in session_dir.rglob('*'):
                            try:
                                if item.is_file():
                                    item.unlink()
                                elif item.is_dir():
                                    # Wird später gelöscht
                                    pass
                            except Exception:
                                pass

                        # Jetzt Verzeichnisse von unten nach oben löschen
                        for item in sorted(session_dir.rglob('*'), reverse=True):
                            try:
                                if item.is_dir():
                                    item.rmdir()
                            except Exception:
                                pass

                        # Abschließend das Session-Verzeichnis selbst löschen
                        try:
                            session_dir.rmdir()
                        except Exception:
                            pass

                        stats['work_dirs_removed'] += 1
                        stats['work_files_removed'] += file_count
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
    name = re.sub(r'[\\/:"*?<>|]', '_', name)
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

def merge_images_to_pdf(image_paths, output_path):
    images = []
    for img_path in sorted(image_paths):
        img = Image.open(img_path)
        if img_path.lower().endswith(('.tif', '.tiff')) and getattr(img, "n_frames", 1) > 1:
            for i in range(img.n_frames):
                img.seek(i)
                images.append(img.convert("RGB").copy())
        else:
            images.append(img.convert("RGB"))

    if not images:
        raise ValueError("Keine gültigen Bilder zum Zusammenfassen gefunden.")
    
    images[0].save(output_path, save_all=True, append_images=images[1:])

def timestamped_pdf_name(prefix="merged_images"):
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
def safe_filename_from_summary(summary: str, ext=".pdf") -> str:
    name = summary.replace("§", "_").replace(" ", "_").replace("/", "-").strip()
    name = "".join(c for c in name if c.isalnum() or c in "._-")
    return name[:260] + ext

def copy_to_target(source_path, target_dir, new_filename):
    log(f"[SKIP COPY] {source_path} -> {os.path.join(target_dir, new_filename)} (wird erst beim Commit finalisiert)")
    return os.path.join(target_dir, new_filename)
    
def handle_successful_processing(summary_data, original_path, target_dir):
    feld1 = sanitize_filename(summary_data.get("name", "Unbekannt"))
    feld2 = sanitize_filename(summary_data.get("vorname", "Unbekannt"))
    feld3 = sanitize_filename(summary_data.get("geburtsdatum", "Unbekannt"))
    feld4 = sanitize_filename(summary_data.get("datum", "Unbekannt"))
    feld5 = sanitize_filename(summary_data.get("beschreibung1", "Unbekannt"))[:30]
    feld6 = sanitize_filename(summary_data.get("beschreibung2", "Unbekannt"))[:120]
    feld7 = sanitize_filename(summary_data.get("categoryID", "11"))

    new_filename = f"{feld1}_{feld2}_{feld3}_{feld4}_{feld5}, {feld6}_{feld7}.pdf"

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

def clear_folder(folder_path):
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            log(f'Fehler beim Löschen von {file_path}: {e}')

def _image_to_temp_pdf(img_path: str, tmp_dir: str) -> str:
    out = os.path.join(tmp_dir, Path(img_path).stem + "_tmp.pdf")
    with open(out, "wb") as f:
        f.write(img2pdf.convert([img_path]))
    return out

def combine_and_delete(source_dir: str, selected_filenames: list[str]) -> str:
    if not selected_filenames:
        raise ValueError("Keine Dateien ausgewählt.")

    rel_inputs = []
    for name in selected_filenames:
        abs_p = os.path.join(source_dir, name)
        if not os.path.exists(abs_p):
            raise FileNotFoundError(f"Datei nicht gefunden: {name}")
        
        rel = to_rel_under_input(abs_p)
        if not rel:
            raise ValueError(f"Pfad liegt nicht unter INPUT_ROOT: {abs_p}")
        rel_inputs.append(rel)

    rel_dir = _to_rel_dir_under_input(source_dir)
    if not rel_dir:
        raise ValueError(f"Quellordner liegt nicht unter INPUT_ROOT: {source_dir}")

    out_name = f"combined_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
    out_rel  = os.path.join(rel_dir, out_name) if rel_dir else out_name

    fs.plan_merge(rel_inputs, out_rel)
    fs.merge_in_staging(rel_inputs, out_rel)

    log(f"✅ Merge abgeschlossen: {out_rel}")
    return out_rel

def split_pdf_to_pages(source_dir: str, filename: str) -> list[str]:
    """Zerlegt eine PDF in einzelne Seiten im STAGING."""
    abs_path = os.path.join(source_dir, filename)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"PDF nicht gefunden: {filename}")
    
    if not filename.lower().endswith('.pdf'):
        raise ValueError(f"Keine PDF-Datei: {filename}")
    
    rel_input = to_rel_under_input(abs_path)
    if not rel_input:
        raise ValueError(f"Pfad liegt nicht unter INPUT_ROOT: {abs_path}")
    
    rel_dir = os.path.dirname(rel_input)
    base_name = Path(filename).stem
    
    try:
        doc = fitz.open(abs_path)
    except Exception as e:
        raise ValueError(f"Fehler beim Öffnen der PDF: {e}")
    
    num_pages = len(doc)
    if num_pages <= 1:
        doc.close()
        raise ValueError(f"PDF hat nur {num_pages} Seite(n). Mindestens 2 Seiten erforderlich.")
    
    created_files = []
    staging_dir = fs.work_dir / rel_dir if rel_dir else fs.work_dir
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    for page_num in range(num_pages):
        new_name = f"{base_name}_Seite_{page_num + 1}.pdf"
        new_rel = os.path.join(rel_dir, new_name) if rel_dir else new_name
        
        staged_path = fs.work_dir / new_rel
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        new_doc.save(str(staged_path))
        new_doc.close()
        
        created_files.append(new_rel)
    
    doc.close()
    log(f"✅ PDF in {num_pages} Einzelseiten zerlegt: {filename}")
    
    return created_files

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

        # Netzlaufwerk-Kompatibilität: Manuelles Löschen statt rmtree
        if self.work_dir.exists():
            try:
                # Erst alle Dateien löschen
                for item in self.work_dir.rglob('*'):
                    try:
                        if item.is_file():
                            item.unlink()
                    except Exception:
                        pass

                # Dann Verzeichnisse von unten nach oben
                for item in sorted(self.work_dir.rglob('*'), reverse=True):
                    try:
                        if item.is_dir():
                            item.rmdir()
                    except Exception:
                        pass

                # Abschließend work_dir selbst
                try:
                    self.work_dir.rmdir()
                except Exception:
                    pass
            except Exception:
                pass

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

        # Netzlaufwerk-Kompatibilität: Manuelles Löschen statt rmtree
        if self.work_dir.exists():
            try:
                # Erst alle Dateien löschen
                for item in self.work_dir.rglob('*'):
                    try:
                        if item.is_file():
                            item.unlink()
                    except Exception:
                        pass

                # Dann Verzeichnisse von unten nach oben
                for item in sorted(self.work_dir.rglob('*'), reverse=True):
                    try:
                        if item.is_dir():
                            item.rmdir()
                    except Exception:
                        pass

                # Abschließend work_dir selbst
                try:
                    self.work_dir.rmdir()
                except Exception:
                    pass
            except Exception:
                pass

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

def _resolve_rel_for_read(rel: str) -> Path:
    cand = fs.work_dir / rel
    return cand if cand.exists() else (fs.input_root / rel)