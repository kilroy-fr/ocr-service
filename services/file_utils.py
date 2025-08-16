from __future__ import annotations
from PIL import Image
from pathlib import Path
from datetime import datetime, timedelta
from services.logger import log_queue, log
from typing import List, Tuple, Optional
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

def sanitize_filename(name):
    # Entfernt oder ersetzt ungültige Zeichen für Dateinamen.
    name = re.sub(r'[\\/:"*?<>|]', '_', name)  # Windows-/Unix-kritische Zeichen
    # name = name.replace(',', '').replace('$', '_')
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

        # Alle Seiten bei mehrseitigen TIFFs extrahieren
        if img_path.lower().endswith(('.tif', '.tiff')) and getattr(img, "n_frames", 1) > 1:
            for i in range(img.n_frames):
                img.seek(i)
                images.append(img.convert("RGB").copy())
        else:
            images.append(img.convert("RGB"))

    if not images:
        raise ValueError("Keine gültigen Bilder zum Zusammenfassen gefunden.")

    # Erstes Bild als Start, Rest anhängen
    images[0].save(output_path, save_all=True, append_images=images[1:])

def timestamped_pdf_name(prefix="merged_images"):
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
def safe_filename_from_summary(summary: str, ext=".pdf") -> str:
    name = summary.replace("§", "_").replace(" ", "_").replace("/", "-").strip()
    name = "".join(c for c in name if c.isalnum() or c in "._-")
    return name[:260] + ext  # sicherstellen, dass Pfadlänge nicht zu lang wird

def copy_to_target(source_path, target_dir, new_filename):
    """
    DEPRECATED im Preview-Modus.
    Belässt die Datei unangetastet und loggt nur.
    Die tatsächliche Verschiebung/Umbenennung geschieht bei fs.commit().
    """
    log(f"[SKIP COPY] {source_path} -> {os.path.join(target_dir, new_filename)} (wird erst beim Commit finalisiert)")
    # absichtlich kein copy; gib lediglich einen erwarteten Ziel-Pfad zurück:
    return os.path.join(target_dir, new_filename)

    
def handle_successful_processing(summary_data, original_path, target_dir):
    """
    Statt sofort zu kopieren + Original zu löschen:
    -> Wir planen NUR eine Umbenennung (im selben Ordner unter INPUT_ROOT).
    'target_dir' wird ignoriert, bis ein expliziter Commit stattfindet.
    """
    feld1 = summary_data.get("name", "Unbekannt")
    feld2 = summary_data.get("vorname", "Unbekannt")
    feld3 = summary_data.get("geburtsdatum", "Unbekannt")
    feld4 = summary_data.get("datum", "Unbekannt")
    feld5 = summary_data.get("beschreibung1", "Unbekannt")
    feld6 = summary_data.get("beschreibung2", "Unbekannt")
    feld7 = summary_data.get("categoryID", "11")

    new_filename = f"{feld1}µ{feld2}µ{feld3}µ{feld4}µ{feld5}, {feld6}µ{feld7}.pdf"

    # REL- oder ABS-Pfad in REL unter INPUT_ROOT auflösen
    rel_src = to_rel_under_input(original_path)
    if not rel_src:
        raise ValueError(f"Pfad liegt nicht unter INPUT_ROOT: {original_path}")

    rel_dir = os.path.dirname(rel_src)
    rel_dst = os.path.join(rel_dir, new_filename)

    # Nur planen – keine echte Mutation
    fs.plan_rename(rel_src, rel_dst)
    log(f"[PLAN] rename {rel_src} -> {rel_dst}")

    return {
        "original": os.path.basename(original_path),
        "renamed": new_filename,
        "summary": summary_data
    }

def cleanup_old_json_files(folder, days_old=1):
    cutoff = datetime.now() - timedelta(days=days_old)

    for filename in os.listdir(folder):
        if filename.endswith(".json"):
            file_path = os.path.join(folder, filename)
            try:
                modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if modified_time < cutoff:
                    os.remove(file_path)
                    print(f"🧹 Alte JSON gelöscht: {filename}")
            except Exception as e:
                print(f"⚠️ Fehler beim Löschen von {filename}: {e}")

def clear_folder(folder_path):
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)  # Datei oder Symlink löschen
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)  # Unterordner rekursiv löschen
        except Exception as e:
            log(f'Fehler beim Löschen von {file_path}: {e}')

def _image_to_temp_pdf(img_path: str, tmp_dir: str) -> str:
    """Bild zu temporärer PDF konvertieren und Pfad zurückgeben."""
    out = os.path.join(tmp_dir, Path(img_path).stem + "_tmp.pdf")
    with open(out, "wb") as f:
        f.write(img2pdf.convert([img_path]))
    return out

def combine_and_delete(source_dir: str, selected_filenames: list[str]) -> str:
    """
    NEU: Kombiniert die ausgewählten Dateien zu EINER PDF **im STAGING**.
    - plant zusätzlich den Merge fürs Commit
    - löscht KEINE Originale mehr
    - gibt den Dateinamen der neuen PDF zurück
    """
    if not selected_filenames:
        raise ValueError("Keine Dateien ausgewählt.")

    # relative Pfade der Inputs unter INPUT_ROOT ermitteln
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
    out_rel  = os.path.join(rel_dir, out_name)

    # Merge wird geplant und sofort fürs Preview im Staging erzeugt
    fs.plan_merge(rel_inputs, out_rel)
    fs.merge_in_staging(rel_inputs, out_rel)

    log(f"🧩 Kombiniert (STAGING): {len(rel_inputs)} Dateien → {out_rel}")
    log("✅ Hinweis: Originale bleiben unverändert bis zum Commit.")
    return out_rel  # relativer Pfad, inkl. Unterordner


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

class StagingSession:
    def __init__(self):
        self.input_root  = Path(INPUT_ROOT)
        self.work_root   = Path(WORK_ROOT)
        self.output_root = Path(OUTPUT_ROOT)
        self.session_id: str | None = None
        self.ops: list[dict] = []

    # ---- intern ----
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

    # ---- Session-API ----
    def start(self, session_id: str):
        self.session_id = session_id
        self.ops = []
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._save()
        logger.info("Staging session %s started", session_id)

    def abort(self):
        if not self.session_id:
            return
        shutil.rmtree(self.work_dir, ignore_errors=True)
        self.meta_file.unlink(missing_ok=True)
        logger.info("Staging session %s aborted (staging cleaned)", self.session_id)
        self.session_id = None
        self.ops = []

    def commit(self):
        """
        Wendet alle geplanten Operationen an:
        - rename: Quelle kann im STAGING (alter ODER bereits neuer Name) oder im INPUT liegen.
                  Ziel:
                    * STAGING-Quelle -> OUTPUT_ROOT/<dst_rel>
                    * INPUT-Quelle   -> INPUT_ROOT/<dst_rel>
        - delete: nur im INPUT löschen
        - merge : STAGING-Output -> OUTPUT_ROOT
        """
        # --- Renames ---
        for op in self.ops:
            if op.get("kind") != "rename":
                continue
            src_rel = op["src_rel"]
            dst_rel = op["dst_rel"]

            staged_src_old = self.work_dir / src_rel
            staged_src_new = self.work_dir / dst_rel  # falls im Staging schon umbenannt (für Preview)
            input_src      = self.input_root / src_rel

            # Ziel im finalen Output (für Staging-Quellen)
            final_dst = self.output_root / dst_rel
            final_dst.parent.mkdir(parents=True, exist_ok=True)

            if staged_src_old.exists():
                os.replace(staged_src_old, final_dst)
            elif staged_src_new.exists():
                os.replace(staged_src_new, final_dst)
            elif input_src.exists():
                # echte Originale innerhalb INPUT_ROOT umbenennen
                input_dst = self.input_root / dst_rel
                input_dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(input_src, input_dst)
            else:
                # Quelle nirgends gefunden – nicht fatal, nur loggen
                logger.warning("Commit rename: Quelle nicht gefunden (weder Staging noch Input): %s", src_rel)

        # --- Deletes (nur Originale im INPUT_ROOT anfassen) ---
        for op in self.ops:
            if op.get("kind") == "delete":
                target = self.input_root / op["target_rel"]
                if target.exists():
                    target.unlink()

        # --- Merges aus dem Staging finalisieren -> OUTPUT_ROOT ---
        for op in self.ops:
            if op.get("kind") == "merge":
                staged_out = self.work_dir / op["output_rel"]
                final_out  = self.output_root / op["output_rel"]
                final_out.parent.mkdir(parents=True, exist_ok=True)
                if staged_out.exists():
                    os.replace(staged_out, final_out)
                else:
                    logger.warning("Commit merge: Staging-Output fehlt: %s", op["output_rel"])

        # --- Cleanup Staging ---
        shutil.rmtree(self.work_dir, ignore_errors=True)
        self.meta_file.unlink(missing_ok=True)
        logger.info("Staging session %s committed", self.session_id)
        self.session_id = None
        self.ops = []

    # ---- Plan-Only (nichts an Originals anfassen) ----
    def plan_rename(self, src_rel: str, dst_rel: str):
        self.ops.append(asdict(RenameOp(src_rel, dst_rel))); self._save()

    def plan_delete(self, rel_path: str):
        self.ops.append(asdict(DeleteOp(rel_path))); self._save()

    def plan_merge(self, inputs_rel: list[str], output_rel: str):
        self.ops.append(asdict(MergeOp(inputs_rel, output_rel))); self._save()

    # ---- Staging-Helfer ----
    def link_or_copy_to_staging(self, rel_path: str):
        src = self.input_root / rel_path
        dst = self.work_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)  # Hardlink spart Platz/zeit
        except Exception:
            shutil.copy2(src, dst)

    def merge_in_staging(self, inputs_rel: list[str], output_rel: str):
        out = self.work_dir / output_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as w:
            for rel in inputs_rel:
                with open(self.input_root / rel, "rb") as r:
                    shutil.copyfileobj(r, w)

    # ---- Vorschauzustand berechnen ----
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

# Globale Instanz:
fs = StagingSession()

# Utility: echte Pfade -> relative Pfade unter INPUT_ROOT mappen
def to_rel_under_input(path: str | Path) -> str | None:
    """Gibt einen REL-Pfad zurück, wenn `path` unter INPUT_ROOT ODER unter fs.work_dir liegt.
       REL-Pfade bleiben unverändert. Andernfalls None.
    """
    from services.file_utils import fs  # lazy import, falls nötig

    # Relativ? -> direkt normalisieren
    if not os.path.isabs(path):
        return Path(path).as_posix()

    p = Path(path).resolve()
    in_root = Path(INPUT_ROOT).resolve()

    # 1) unter INPUT_ROOT?
    try:
        return p.relative_to(in_root).as_posix()
    except Exception:
        pass

    # 2) unter aktuellem STAGING?
    if fs.session_id:
        try:
            return p.relative_to(fs.work_dir.resolve()).as_posix()
        except Exception:
            pass

    return None  # liegt weder unter INPUT_ROOT noch im Staging

# Neu: kleines Hilfsding, falls noch nicht vorhanden
def _to_rel_dir_under_input(abs_dir: str | Path) -> Optional[str]:
    """Wie to_rel_under_input, aber für Verzeichnisse."""
    p = Path(abs_dir).resolve()
    root = Path(INPUT_ROOT).resolve()
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        logger.warning("Dir %s not under INPUT_ROOT %s; skipping", p, root)
        return None

def _resolve_rel_for_read(rel: str) -> Path:
    cand = fs.work_dir / rel
    return cand if cand.exists() else (fs.input_root / rel)

