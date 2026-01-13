// Progressive Analyse Status
let isProgressiveMode = false;
let progressiveInterval = null;
let lastKnownCount = 0;


// Spinner-Funktionen für Kopiervorgänge
function showCopySpinner() {
  const overlay = document.createElement('div');
  overlay.id = 'copySpinnerOverlay';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.7);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
  `;
  
  const spinnerContainer = document.createElement('div');
  spinnerContainer.style.cssText = `
    background: white;
    padding: 40px;
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    text-align: center;
    max-width: 400px;
  `;
  
  spinnerContainer.innerHTML = `
    <div style="
      width: 60px;
      height: 60px;
      border: 6px solid #f3f3f3;
      border-top: 6px solid #007BFF;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto 20px;
    "></div>
    <h3 style="margin: 0 0 10px 0; color: #333;">Dateien werden kopiert...</h3>
    <p style="margin: 0; color: #666; font-size: 14px;">
      Bitte warten. Zwischen jedem Kopiervorgang wird eine 5-Sekunden-Pause eingehalten.
    </p>
  `;
  
  overlay.appendChild(spinnerContainer);
  document.body.appendChild(overlay);
  
  if (!document.getElementById('spinnerStyles')) {
    const style = document.createElement('style');
    style.id = 'spinnerStyles';
    style.textContent = `
      @keyframes spin {
        to { transform: rotate(360deg); }
      }
    `;
    document.head.appendChild(style);
  }
}

function hideCopySpinner() {
  const overlay = document.getElementById('copySpinnerOverlay');
  if (overlay) {
    overlay.remove();
  }
}

// Beim Laden prüfen ob progressive Analyse aktiv
window.addEventListener("DOMContentLoaded", () => {
  // Files aus HTML-inline-Script prüfen
  console.log("Geladene Files:", files);
  if (files && files.length > 0) {
    files.forEach((f, i) => console.log(`File ${i}: originalFilename=${f.originalFilename}`));
  }
  
  // URL-Parameter auslesen
  const urlParams = new URLSearchParams(window.location.search);
  isProgressiveMode = urlParams.get('progressive') === 'true';
  
  if (isProgressiveMode) {
    console.log('Progressive Analyse-Modus aktiviert');
    setupProgressiveMode();
  }
  
  // Rest der bisherigen Initialisierung...
  console.log(`Initialisierung: ${files.length} Dateien geladen`);
  
  if (!files || files.length === 0) {
    document.getElementById("preview").innerHTML = `<p>Keine Dateien vorhanden.</p>`;
    return;
  }

  lastKnownCount = files.length;
  updateUI();
  setupSessionCheckboxes();

  document.getElementById("prevBtn").addEventListener("click", prevFile);
  document.getElementById("nextBtn").addEventListener("click", nextFile);
  document.getElementById("finalizeBtn").addEventListener("click", finalizeAnalysis);
  document.getElementById("abortBtn").addEventListener("click", abortAll);

  // PDF Rotation Buttons
  const rotateLeftBtn = document.getElementById("rotateLeftBtn");
  const rotate180Btn = document.getElementById("rotate180Btn");
  const rotateRightBtn = document.getElementById("rotateRightBtn");
  if (rotateLeftBtn) {
    rotateLeftBtn.addEventListener("click", () => rotatePDF("left"));
  }
  if (rotate180Btn) {
    rotate180Btn.addEventListener("click", () => rotatePDF("180"));
  }
  if (rotateRightBtn) {
    rotateRightBtn.addEventListener("click", () => rotatePDF("right"));
  }

  // Auto-save Setup
  const autoSaveFields = ['name', 'vorname', 'geburtsdatum', 'datum', 'beschreibung1', 'beschreibung2', 'categoryID'];
  autoSaveFields.forEach(fieldId => {
    const field = document.getElementById(fieldId);
    if (field) {
      field.addEventListener('change', () => {
        saveCurrentFileData();
        const newName = buildNewName(files[currentIndex]);
        document.getElementById("newFilename").textContent = "Neu: " + newName;
        updateProgress();
      });
    }
  });
  
  document.querySelectorAll('input[name="includeOption"]').forEach(radio => {
    radio.addEventListener('change', () => {
      saveCurrentFileData();
      updateProgress();
      checkFinalizeReady();
    });
  });
});

function setupProgressiveMode() {
  // Status-Banner als transparente Overlay-Anzeige rechts oben erstellen
  const banner = document.createElement('div');
  banner.id = 'progressiveBanner';
  banner.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    width: 200px;
    background: rgba(16, 185, 129, 0.95);
    color: white;
    padding: 15px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    z-index: 1000;
    font-size: 0.85em;
  `;

  banner.innerHTML = `
    <div style="text-align: center;">
      <div id="progressiveSpinner" style="
        width: 24px;
        height: 24px;
        border: 3px solid rgba(255,255,255,0.3);
        border-top: 3px solid white;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 10px;
      "></div>
      <strong style="display: block; margin-bottom: 8px;">Bearbeitung l\u00e4uft...</strong>
      <div id="progressiveStatus" style="font-size: 0.9em; opacity: 0.95;">
        Lade Status...
      </div>
    </div>
  `;

  // Banner direkt an body anhängen
  document.body.appendChild(banner);
  
  // CSS für Spinner-Animation hinzufügen
  if (!document.getElementById('progressiveStyles')) {
    const style = document.createElement('style');
    style.id = 'progressiveStyles';
    style.textContent = `
      @keyframes spin {
        to { transform: rotate(360deg); }
      }
      .new-file-indicator {
        animation: pulse 0.5s ease-in-out;
        background: #90ee90 !important;
      }
      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
      }
    `;
    document.head.appendChild(style);
  }
  
  // Polling starten
  startProgressivePolling();
}

async function startProgressivePolling() {
  console.log('Starte Polling f\u00fcr neue Analyse-Ergebnisse');
  
  // Alle 2 Sekunden Status prüfen
  progressiveInterval = setInterval(async () => {
    try {
      await checkForNewFiles();
      await updateAnalysisStatus();
    } catch (err) {
      console.error('Fehler beim Polling:', err);
    }
  }, 2000);
}

async function checkForNewFiles() {
  try {
    const res = await fetch('/get_control_data');
    const data = await res.json();
    
    if (!data.success || !data.data) return;
    
    const newFiles = data.data;
    const newCount = newFiles.length;
    
    if (newCount > lastKnownCount) {
      console.log(`${newCount - lastKnownCount} neue Datei(en) verf\u00fcgbar`);
      
      // Neue Dateien zu globalem Array hinzufügen
      const addedFiles = newFiles.slice(lastKnownCount);
      files.push(...addedFiles);
      
      // Visuelles Feedback
      showNewFileNotification(addedFiles.length);
      
      lastKnownCount = newCount;
      
      // UI aktualisieren
      updateProgress();
      checkFinalizeReady();
    }
    
  } catch (err) {
    console.error('Fehler beim Laden neuer Dateien:', err);
  }
}

async function updateAnalysisStatus() {
  try {
    const res = await fetch('/analysis_status');
    const data = await res.json();
    
    if (!data.success) return;
    
    const statusEl = document.getElementById('progressiveStatus');
    if (!statusEl) return;
    
    if (data.status === 'idle') {
      // Keine Analyse mehr aktiv
      finishProgressiveMode();
      return;
    }
    
    const completed = data.completed || 0;
    const total = data.total || 0;
    const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
    
    statusEl.textContent = `${completed} von ${total} Dateien analysiert (${percent}%)`;
    
    if (data.status === 'completed') {
      finishProgressiveMode();
    }
    
  } catch (err) {
    console.error('Fehler beim Status-Update:', err);
  }
}

function finishProgressiveMode() {
  console.log('Progressive Analyse abgeschlossen');
  
  if (progressiveInterval) {
    clearInterval(progressiveInterval);
    progressiveInterval = null;
  }
  
  const banner = document.getElementById('progressiveBanner');
  if (banner) {
    banner.style.background = 'rgba(40, 167, 69, 0.95)';
    banner.innerHTML = `
      <div style="text-align: center;">
        <strong style="display: block; margin-bottom: 8px;">Alle Dateien analysiert!</strong>
        <div style="font-size: 0.9em; opacity: 0.95;">
          Sie k\u00f6nnen nun alle Dokumente bearbeiten.
        </div>
      </div>
    `;
    
    // Banner nach 5 Sekunden ausblenden
    setTimeout(() => {
      banner.style.transition = 'opacity 0.5s';
      banner.style.opacity = '0';
      setTimeout(() => banner.remove(), 500);
    }, 5000);
  }
  
  isProgressiveMode = false;
  
  // Final Update
  updateProgress();
  checkFinalizeReady();
}

function showNewFileNotification(count) {
  // Temporäre Benachrichtigung
  const notification = document.createElement('div');
  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: #28a745;
    color: white;
    padding: 15px 20px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    z-index: 10000;
    animation: slideIn 0.3s ease-out;
  `;
  
  notification.innerHTML = `
    <strong>${count} neue Datei(en) verf\u00fcgbar</strong>
  `;
  
  document.body.appendChild(notification);
  
  // Nach 3 Sekunden entfernen
  setTimeout(() => {
    notification.style.transition = 'opacity 0.3s';
    notification.style.opacity = '0';
    setTimeout(() => notification.remove(), 300);
  }, 3000);
}

// Cleanup beim Verlassen der Seite
window.addEventListener('beforeunload', () => {
  if (progressiveInterval) {
    clearInterval(progressiveInterval);
  }
});

// files-Variable wird von control.html übergeben
let currentIndex = 0;
const visited = new Set();
const SESSION_FIELDS = ["name", "vorname", "geburtsdatum"];

// Session-Daten (werden beim Sperren eines Feldes gesetzt)
const sessionData = {
  name: { locked: false, value: "" },
  vorname: { locked: false, value: "" },
  geburtsdatum: { locked: false, value: "" }
};

function sanitizeBase(name) {
  return (name || "").replace(/[\\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim();
}

function buildNewName(f) {
  const p = [
    f.name || "Unbekannt",
    f.vorname || "Unbekannt",
    f.geburtsdatum || "Unbekannt",
    f.datum || "Unbekannt",
    f.beschreibung1 || "Kein Arzt erkannt",
    f.beschreibung2 || "Keine Beschreibung verfügbar",
    f.categoryID || "11"
  ].map(sanitizeBase);

  return `${p[0]}_${p[1]}_${p[2]}_${p[3]}_${p[4]}, ${p[5]}_${p[6]}.pdf`;
}

function extOf(p) {
  const s = (p || "").toLowerCase();
  const i = s.lastIndexOf(".");
  return i >= 0 ? s.slice(i + 1) : "";
}

function updateUI() {
  const file = files[currentIndex];
  if (!file) return;

  const catID = parseInt(file.categoryID || "11", 10);
  file.categoryID = (catID === 5 || catID === 6) ? String(catID) : "11";

  // originalFilename bewahren - NIEMALS überschreiben!
  // Fallback nur wenn wirklich nicht gesetzt (sollte normalerweise vom Backend kommen)
  if (!file.originalFilename || file.originalFilename === file.filename) {
    if (file.filename && file.filename.includes('_ocr.pdf')) {
      // Fallback: _ocr.pdf entfernen (behält Original-Extension bei)
      file.originalFilename = file.filename.replace('_ocr.pdf', '.pdf');
    } else {
      file.originalFilename = file.filename;
    }
  }

  console.log(`[updateUI] File: ${file.filename}, Original: ${file.originalFilename}`);

  // Session-Felder: entweder gesperrter Wert oder Datei-Wert
  SESSION_FIELDS.forEach(field => {
    const input = document.getElementById(field);
    const checkbox = document.getElementById(`${field}-session`);

    if (sessionData[field].locked) {
      input.value = sessionData[field].value;
      input.readOnly = true;
      input.classList.add('session-locked');
      checkbox.checked = true;
    } else {
      input.value = file[field] || "";
      input.readOnly = false;
      input.classList.remove('session-locked');
      checkbox.checked = false;
    }
  });

  // Normale Felder
  document.getElementById("datum").value = file.datum || "";
  document.getElementById("beschreibung1").value = file.beschreibung1 || "";
  document.getElementById("beschreibung2").value = file.beschreibung2 || "";
  document.getElementById("categoryID").value = file.categoryID || "11";

  // Include-Option initial NICHT vorbelegt
  document.querySelectorAll('input[name="includeOption"]').forEach(r => r.checked = false);

  if (file.include === true || file.include === false) {
    const radio = document.querySelector(`input[name="includeOption"][value="${file.include}"]`);
    if (radio) radio.checked = true;
  }

  const newName = buildNewName(file);
  document.getElementById("newFilename").textContent = "Neu: " + newName;
  document.getElementById("originalFilename").textContent = "Original: " + (file.filename || "");

  // Fortschrittsanzeige aktualisieren
  updateProgress();

  // Vorschau
  // WICHTIG: Verwende filename (tatsächlicher Name im Staging), nicht file (geplanter neuer Name)
  const previewFile = file.filename || file.file;
  const ext = extOf(previewFile);
  let previewContent = "";

  // PDF Rotation Controls zeigen/verstecken
  const pdfControls = document.getElementById("pdfControls");
  if (ext === "pdf" && pdfControls) {
    pdfControls.style.display = "flex";
  } else if (pdfControls) {
    pdfControls.style.display = "none";
  }

  if (["jpg","jpeg","png"].includes(ext)) {
    previewContent = `<img src="/processed/${encodeURIComponent(previewFile)}" alt="Bildvorschau">`;
  } else if (ext === "pdf") {
    previewContent = `<iframe src="/processed/${encodeURIComponent(previewFile)}#page=1&zoom=fit"></iframe>`;
  } else if (ext === "txt") {
    previewContent = `<iframe src="/preview/${encodeURIComponent(previewFile)}" scrolling="auto" style="background: #1e1e1e;"></iframe>`;
  } else {
    previewContent = `<p>Keine Vorschau verfügbar</p>`;
  }
  document.getElementById("preview").innerHTML = previewContent;

  visited.add(currentIndex);
  checkFinalizeReady();
}

async function saveData() {
  const f = files[currentIndex];
  if (!f) return;

  const prevFileRel = f.file;

  // Formular â†’ Objekt (Session-Felder nutzen gesperrte Werte)
  SESSION_FIELDS.forEach(field => {
    if (sessionData[field].locked) {
      f[field] = sessionData[field].value;
    } else {
      f[field] = document.getElementById(field).value;
    }
  });

  f.datum = document.getElementById("datum").value;
  f.beschreibung1 = document.getElementById("beschreibung1").value;
  f.beschreibung2 = document.getElementById("beschreibung2").value;
  f.categoryID = document.getElementById("categoryID").value;

  // Include nur setzen wenn ein Radio-Button gewählt ist
  const selected = document.querySelector('input[name="includeOption"]:checked');
  if (selected) {
    f.include = selected.value === "true";
  }

  const newName = buildNewName(f);

  // 1) Metadaten in control_*.json sichern
  await fetch("/save_control_data", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      index: currentIndex,
      name: f.name,
      vorname: f.vorname,
      geburtsdatum: f.geburtsdatum,
      datum: f.datum,
      beschreibung1: f.beschreibung1,
      beschreibung2: f.beschreibung2,
      categoryID: f.categoryID,
      selected: f.include === true
    })
  }).catch(() => {});

  // 2) Umbenennung planen
  const relDir = prevFileRel.split("/").slice(0, -1).join("/");
  const newRel = relDir ? `${relDir}/${newName}` : newName;

  const res = await fetch("/rename_file", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      old_filename: prevFileRel,
      new_filename: newRel
    })
  });

  if (!res.ok) {
    Notifications.error("Fehler beim Umbenennen (Plan).");
  } else {
    const j = await res.json().catch(() => ({}));
    const effectiveRel = j && j.new_filename ? j.new_filename : newRel;
    f.file = effectiveRel;
    f.new_filename = newName;
    document.getElementById("newFilename").textContent = "Neu: " + newName;
    updateUI();
  }

  visited.add(currentIndex);
  checkFinalizeReady();
}

function checkFinalizeReady() {
  // Button nur aktivieren, wenn ALLE Dateien:
  // 1. Besucht wurden UND
  // 2. Eine Include-Entscheidung haben (ja oder nein)
  const allVisited = files.every((_, index) => visited.has(index));
  const allDecided = files.every(f => f.include === true || f.include === false);
  
  document.getElementById("finalizeBtn").disabled = !(allVisited && allDecided);
  
  if (allVisited && !allDecided) {
    const remaining = files.filter(f => f.include !== true && f.include !== false).length;
    console.log(`WARNUNG: ${remaining} Datei(en) haben noch keine Include-Entscheidung`);
  }
}

function updateProgress() {
  const total = files.length;
  const current = currentIndex + 1;
  const visitedCount = visited.size;
  
  // Zusätzlich zählen wir entschiedene Dateien
  const decidedCount = files.filter(f => f.include === true || f.include === false).length;
  const percent = total > 0 ? Math.round((decidedCount / total) * 100) : 0;
  
  const progressText = document.getElementById("progressText");
  const progressPercent = document.getElementById("progressPercent");
  const progressBar = document.getElementById("progressBar");
  
  if (progressText) {
    progressText.textContent = `Datei ${current} von ${total} (${decidedCount} entschieden)`;
  }
  
  if (progressPercent) {
    progressPercent.textContent = `${percent}%`;
  }
  
  if (progressBar) {
    progressBar.style.width = `${percent}%`;
    
    if (percent === 100) {
      progressBar.style.background = "linear-gradient(90deg, #28a745 0%, #20c997 100%)";
    } else if (percent >= 50) {
      progressBar.style.background = "linear-gradient(90deg, #007BFF 0%, #0056b3 100%)";
    } else {
      progressBar.style.background = "linear-gradient(90deg, #ffc107 0%, #ff9800 100%)";
    }
  }
  
  console.log(`Progress: ${current}/${total}, visited: ${visitedCount}, decided: ${decidedCount}, percent: ${percent}%`);
}

function prevFile() {
  saveCurrentFileData();
  if (currentIndex > 0) { currentIndex--; updateUI(); }
}

function nextFile() {
  saveCurrentFileData();
  if (currentIndex < files.length - 1) { currentIndex++; updateUI(); }
}

async function rotatePDF(direction) {
  const file = files[currentIndex];
  if (!file) return;

  const filename = file.filename || file.file;

  // Buttons deaktivieren während Rotation
  const rotateLeftBtn = document.getElementById("rotateLeftBtn");
  const rotate180Btn = document.getElementById("rotate180Btn");
  const rotateRightBtn = document.getElementById("rotateRightBtn");
  if (rotateLeftBtn) rotateLeftBtn.disabled = true;
  if (rotate180Btn) rotate180Btn.disabled = true;
  if (rotateRightBtn) rotateRightBtn.disabled = true;

  // Zeige Lade-Overlay
  const overlay = document.createElement('div');
  overlay.id = 'rotateSpinner';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.7);
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
  `;

  overlay.innerHTML = `
    <div style="
      background: white;
      padding: 40px;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      text-align: center;
      max-width: 400px;
    ">
      <div style="
        width: 60px;
        height: 60px;
        border: 6px solid #f3f3f3;
        border-top: 6px solid #3b82f6;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 20px;
      "></div>
      <h3 style="margin: 0 0 10px 0; color: #333;">PDF wird gedreht...</h3>
      <p style="margin: 0; color: #666; font-size: 14px;">
        Das PDF wird gedreht und automatisch neu analysiert.
      </p>
    </div>
  `;

  document.body.appendChild(overlay);

  try {
    const response = await fetch("/rotate_pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: filename,
        direction: direction
      })
    });

    const data = await response.json();

    if (response.ok && data.success) {
      console.log(`✅ PDF gedreht: ${direction}`, data);

      // Vorschau neu laden durch Cache-Busting
      const previewFile = file.filename || file.file;
      const timestamp = new Date().getTime();
      const previewContent = `<iframe src="/processed/${encodeURIComponent(previewFile)}?t=${timestamp}#page=1&zoom=fit"></iframe>`;
      document.getElementById("preview").innerHTML = previewContent;

      // Wenn neu analysiert wurde, aktualisiere die Formularfelder
      if (data.reanalyzed && data.fields) {
        console.log('🔄 Aktualisiere Formularfelder mit neuen Analysedaten');

        // Aktualisiere das File-Objekt im Array
        const fields = data.fields;
        file.name = fields.name || file.name || "";
        file.vorname = fields.vorname || file.vorname || "";
        file.geburtsdatum = fields.geburtsdatum || file.geburtsdatum || "";
        file.datum = fields.datum || file.datum || "";
        file.beschreibung1 = fields.beschreibung1 || file.beschreibung1 || "";
        file.beschreibung2 = fields.beschreibung2 || file.beschreibung2 || "";

        // Aktualisiere die Formularfelder (nur wenn nicht session-locked)
        if (!sessionData.name.locked) {
          document.getElementById("name").value = file.name;
        }
        if (!sessionData.vorname.locked) {
          document.getElementById("vorname").value = file.vorname;
        }
        if (!sessionData.geburtsdatum.locked) {
          document.getElementById("geburtsdatum").value = file.geburtsdatum;
        }

        document.getElementById("datum").value = file.datum;
        document.getElementById("beschreibung1").value = file.beschreibung1;
        document.getElementById("beschreibung2").value = file.beschreibung2;

        // Aktualisiere den neuen Dateinamen
        const newName = buildNewName(file);
        document.getElementById("newFilename").textContent = "Neu: " + newName;

        if (typeof Notifications !== 'undefined') {
          Notifications.success("PDF gedreht und neu analysiert ✓");
        }
      } else {
        if (typeof Notifications !== 'undefined') {
          Notifications.success("PDF erfolgreich gedreht");
        }
      }
    } else {
      console.error("❌ Fehler beim Drehen:", data.message);
      if (typeof Notifications !== 'undefined') {
        Notifications.error("Fehler beim Drehen: " + (data.message || "Unbekannter Fehler"));
      } else {
        alert("Fehler beim Drehen: " + (data.message || "Unbekannter Fehler"));
      }
    }
  } catch (error) {
    console.error("❌ Fehler beim Drehen:", error);
    if (typeof Notifications !== 'undefined') {
      Notifications.error("Fehler beim Drehen: " + error.message);
    } else {
      alert("Fehler beim Drehen: " + error.message);
    }
  } finally {
    // Entferne Spinner
    overlay.remove();

    // Buttons wieder aktivieren
    if (rotateLeftBtn) rotateLeftBtn.disabled = false;
    if (rotate180Btn) rotate180Btn.disabled = false;
    if (rotateRightBtn) rotateRightBtn.disabled = false;
  }
}

function saveCurrentFileData() {
  const f = files[currentIndex];
  if (!f) return;

  // Session-Felder: verwende gesperrte Werte oder aktuelle Eingabe
  SESSION_FIELDS.forEach(field => {
    if (sessionData[field].locked) {
      f[field] = sessionData[field].value;
    } else {
      f[field] = document.getElementById(field).value;
    }
  });

  // Normale Felder
  f.datum = document.getElementById("datum").value;
  f.beschreibung1 = document.getElementById("beschreibung1").value;
  f.beschreibung2 = document.getElementById("beschreibung2").value;
  f.categoryID = document.getElementById("categoryID").value;

  // Include nur setzen wenn Radio-Button gewählt
  const selected = document.querySelector('input[name="includeOption"]:checked');
  if (selected) {
    f.include = selected.value === "true";
  }
}

async function finalizeAnalysis() {
  saveCurrentFileData();
  
  // Prüfen ob alle Dateien eine Entscheidung haben
  const undecided = files.filter(f => f.include !== true && f.include !== false);
  
  if (undecided.length > 0) {
    alert(`WARNUNG: Bitte treffen Sie für alle ${undecided.length} Datei(en) eine Entscheidung (Ja/Nein), bevor Sie die Analyse abschließen.`);
    return;
  }

  // Alle Metadaten speichern
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    await fetch("/save_control_data", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        index: i,
        name: f.name,
        vorname: f.vorname,
        geburtsdatum: f.geburtsdatum,
        datum: f.datum,
        beschreibung1: f.beschreibung1,
        beschreibung2: f.beschreibung2,
        categoryID: f.categoryID,
        selected: f.include === true
      })
    }).catch(() => {});

    // Umbenennung planen
    const newName = buildNewName(f);
    const relDir = f.file.split("/").slice(0, -1).join("/");
    const newRel = relDir ? `${relDir}/${newName}` : newName;

    await fetch("/rename_file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        old_filename: f.file,
        new_filename: newRel
      })
    }).then(async res => {
      if (res.ok) {
        const j = await res.json().catch(() => ({}));
        if (j && j.new_filename) {
          f.file = j.new_filename;
        }
      }
    }).catch(() => {});
  }

  // Finalisieren
  const payload = files.map(f => ({
    file: f.file,
    originalFilename: f.originalFilename,
    include: !!f.include
  }));

  // Zeige Spinner während des Kopiervorgangs
  showCopySpinner();

  try {
    const res = await fetch("/finalize_import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: payload })
    });
    const data = await res.json().catch(() => ({}));

    // Verstecke Spinner nach Abschluss
    hideCopySpinner();

    if (res.ok && data.success) {
      console.log('✅ Finalize erfolgreich, rufe showQueueMonitor() auf', data);
      // Zeige Queue-Monitor statt direkt zur Startseite zu springen
      showQueueMonitor(data);
    } else {
      console.error('❌ Finalize fehlgeschlagen', data);
      Notifications.error("Fehler: " + (data.message || `HTTP ${res.status}`));
    }
  } catch (error) {
    // Verstecke Spinner auch bei Fehler
    hideCopySpinner();
    Notifications.error("Fehler beim Finalisieren: " + error.message);
  }
}

async function abortAll() {
  if (!await Notifications.confirm("Alle Änderungen verwerfen und zur Startseite zurückkehren?", "Zur Startseite", "Bleiben")) return;
  const res = await fetch("/abort", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (res.ok && data.success) {
    window.location.href = "/";
  } else {
    Notifications.error("Fehler beim Abbrechen: " + (data.message || `HTTP ${res.status}`));
  }
}

// Queue Monitor Funktionen
function showQueueMonitor(finalizeData) {
  console.log('📦 showQueueMonitor() aufgerufen', finalizeData);

  // Verstecke Hauptformular und zeige Queue-Monitor
  const container = document.querySelector('.container');
  const filenameSection = document.querySelector('.filename-section');
  const queueSection = document.getElementById('queue-status-section');

  if (container) {
    container.style.display = 'none';
    console.log('✅ Hauptcontainer ausgeblendet');
  }

  if (filenameSection) {
    filenameSection.style.display = 'none';
    console.log('✅ Filename-Section ausgeblendet');
  }

  if (queueSection) {
    queueSection.style.display = 'block';
    console.log('✅ Queue-Section eingeblendet');

    // Scroll zum Queue-Monitor
    queueSection.scrollIntoView({ behavior: 'smooth' });
  } else {
    console.error('❌ Queue-Section nicht gefunden!');
    return;
  }

  // Kleine Verzögerung vor Start damit Alert geschlossen werden kann
  setTimeout(() => {
    console.log('🚀 Starte Queue-Monitor...');
    // Starte Queue-Monitor
    QueueMonitor.start('queue-status');

    // Überwache Abschluss
    monitorQueueCompletion();
  }, 500);
}

function monitorQueueCompletion() {
  let hasSeenActivity = false;  // Flag um zu wissen ob Queue aktiv war

  // Prüfe alle 3 Sekunden ob Queue leer ist (schneller für besseres UX)
  const checkInterval = setInterval(async () => {
    try {
      const response = await fetch('/import_queue_status');
      const data = await response.json();

      if (data.success && data.stats) {
        const { current_queue_size, total_processed, total_queued } = data.stats;

        // Merke dass Queue aktiv war/ist
        if (total_queued > 0 || current_queue_size > 0) {
          hasSeenActivity = true;
        }

        // Wenn Queue leer und alle verarbeitet UND wir haben Aktivität gesehen
        if (hasSeenActivity && current_queue_size === 0 && total_processed > 0 && total_processed === total_queued) {
          clearInterval(checkInterval);
          QueueMonitor.stop();

          // Zeige Success-Message mit Verzögerung
          setTimeout(async () => {
            const proceed = await Notifications.confirm(
              `✅ Alle ${total_processed} Dateien wurden erfolgreich importiert!\n\nZur Startseite zurückkehren?`,
              "Zur Startseite",
              "Hier bleiben"
            );

            if (proceed) {
              // Fallback für undefined/null HOME_URL
              let targetUrl = "/";
              if (typeof HOME_URL !== 'undefined' && HOME_URL && HOME_URL !== 'undefined') {
                targetUrl = HOME_URL;
              }
              console.log(`🔄 Weiterleitung zu: ${targetUrl} (HOME_URL type: ${typeof HOME_URL}, value: ${HOME_URL})`);
              window.location.href = targetUrl;
            } else {
              // Wenn Benutzer "Hier bleiben" wählt, blende Fortschritt-Fenster aus
              // und zeige Hauptformular wieder
              const queueSection = document.getElementById('queue-status-section');
              if (queueSection) {
                queueSection.style.display = 'none';
              }
              const container = document.querySelector('.container');
              if (container) {
                container.style.display = 'block';
              }
              const filenameSection = document.querySelector('.filename-section');
              if (filenameSection) {
                filenameSection.style.display = 'block';
              }
            }
          }, 1000); // 1 Sekunde Verzögerung
        }
      }
    } catch (error) {
      console.error('Fehler beim Überwachen der Queue:', error);
    }
  }, 3000); // Alle 3 Sekunden prüfen (war 5)
}

// Event-Listener für "Monitoring beenden" Button
// Verwende Event-Delegation auf document, da der Button dynamisch angezeigt wird
document.addEventListener('click', async function(e) {
  if (e.target && e.target.id === 'closeQueueMonitor') {
    e.preventDefault();
    e.stopPropagation();

    console.log('closeQueueMonitor Button geklickt');

    // Hole aktuellen Queue-Status
    try {
      const response = await fetch('/import_queue_status');
      const data = await response.json();
      console.log('Queue Status:', data);

      if (data.success && data.stats) {
        const { current_queue_size, total_processed } = data.stats;

        // Warnung wenn noch Dateien in der Queue
        if (current_queue_size > 0) {
          console.log('Queue nicht leer, zeige Warnung');
          const proceed = await Notifications.confirm(
            `⚠️ ACHTUNG: Es sind noch ${current_queue_size} Datei(en) in der Warteschlange!\n\n${total_processed} Datei(en) wurden bereits importiert.\n\nWenn Sie jetzt abbrechen, werden die verbleibenden Dateien NICHT importiert.\n\nTrotzdem zur Startseite zurückkehren?`,
            "Zur Startseite",
            "Abbrechen"
          );
          console.log('User Entscheidung:', proceed);
          if (!proceed) return;
        } else {
          // Queue ist leer - normale Bestätigung
          console.log('Queue leer, zeige Erfolgsmeldung');
          const proceed = await Notifications.confirm(
            `✅ ${total_processed} Datei(en) wurden erfolgreich importiert.\n\nZur Startseite zurückkehren?`,
            "Zur Startseite",
            "Hier bleiben"
          );
          console.log('User Entscheidung:', proceed);
          if (!proceed) {
            // Wenn Benutzer "Hier bleiben" wählt, schließe Fortschritt-Fenster
            const queueSection = document.getElementById('queue-status-section');
            if (queueSection) {
              queueSection.style.display = 'none';
            }
            const container = document.querySelector('.container');
            if (container) {
              container.style.display = 'block';
            }
            const filenameSection = document.querySelector('.filename-section');
            if (filenameSection) {
              filenameSection.style.display = 'block';
            }
            return;
          }
        }
      }
    } catch (error) {
      // Fallback bei Fehler
      console.error('Fehler beim Laden des Queue Status:', error);
      const proceed = await Notifications.confirm(
        'Queue-Monitoring beenden und zur Startseite zurückkehren?',
        "Zur Startseite",
        "Abbrechen"
      );
      console.log('User Entscheidung (Fehlerfall):', proceed);
      if (!proceed) return;
    }

    // Fallback für undefined/null HOME_URL
    let targetUrl = "/";
    if (typeof HOME_URL !== 'undefined' && HOME_URL && HOME_URL !== 'undefined') {
      targetUrl = HOME_URL;
    }
    console.log(`Stopping QueueMonitor und redirect zu: ${targetUrl} (HOME_URL: ${HOME_URL})`);
    QueueMonitor.stop();
    window.location.href = targetUrl;
  }
});

// Session-Checkbox Handler
function setupSessionCheckboxes() {
  SESSION_FIELDS.forEach(field => {
    const checkbox = document.getElementById(`${field}-session`);
    const input = document.getElementById(field);
    
    if (!checkbox || !input) return;

    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        const currentValue = input.value.trim();
        
        if (!currentValue) {
          checkbox.checked = false;
          input.focus();
          return;
        }

        sessionData[field].locked = true;
        sessionData[field].value = currentValue;

        input.readOnly = true;
        input.classList.add('session-locked');

        files.forEach(f => {
          f[field] = currentValue;
        });
        // Aktualisiere den Dateinamen für die aktuelle Datei
        const newName = buildNewName(files[currentIndex]);
        document.getElementById("newFilename").textContent = "Neu: " + newName;
        
        // Speichere die Änderungen
        saveCurrentFileData();
        updateProgress();
        console.log(`Feld "${field}" f\u00fcr Session gesperrt mit Wert: "${currentValue}"`);
      } else {
        sessionData[field].locked = false;
        sessionData[field].value = "";

        input.readOnly = false;
        input.classList.remove('session-locked');

        const currentFile = files[currentIndex];
        if (currentFile) {
          input.value = currentFile[field] || "";
        }
        // Aktualisiere den Dateinamen nach dem Entsperren
        const newName = buildNewName(files[currentIndex]);
        document.getElementById("newFilename").textContent = "Neu: " + newName;
        
        // Speichere die Änderungen
        saveCurrentFileData();
        updateProgress();
        console.log(`Feld "${field}" f\u00fcr Session entsperrt`);
      }
    });
  });
}

// Init
window.addEventListener("DOMContentLoaded", () => {
  console.log(`Initialisierung: ${files.length} Dateien geladen`);
  
  if (!files || files.length === 0) {
    document.getElementById("preview").innerHTML = `<p>Keine Dateien vorhanden.</p>`;
    return;
  }

  // Erste Datei anzeigen
  updateUI();

  setupSessionCheckboxes();

  document.getElementById("prevBtn").addEventListener("click", prevFile);
  document.getElementById("nextBtn").addEventListener("click", nextFile);
  document.getElementById("finalizeBtn").addEventListener("click", finalizeAnalysis);
  document.getElementById("abortBtn").addEventListener("click", abortAll);
  
  // Auto-save bei Änderungen in Feldern
  const autoSaveFields = ['name', 'vorname', 'geburtsdatum', 'datum', 'beschreibung1', 'beschreibung2', 'categoryID'];
  autoSaveFields.forEach(fieldId => {
    const field = document.getElementById(fieldId);
    if (field) {
      field.addEventListener('change', () => {
        saveCurrentFileData();
        const newName = buildNewName(files[currentIndex]);
        document.getElementById("newFilename").textContent = "Neu: " + newName;
        updateProgress();
      });
    }
  });
  
  // Auto-save bei Radio-Button Änderung + checkFinalizeReady
  document.querySelectorAll('input[name="includeOption"]').forEach(radio => {
    radio.addEventListener('change', () => {
      saveCurrentFileData();
      updateProgress();
      checkFinalizeReady();
    });
  });

  // Debug: HOME_URL prüfen
  console.log('🏠 HOME_URL definiert:', typeof HOME_URL !== 'undefined' ? HOME_URL : 'NICHT DEFINIERT');

  // Queue-Monitor automatisch starten, wenn Import-Fortschritt-Sektion sichtbar ist
  const queueSection = document.getElementById('queue-status-section');
  if (queueSection && queueSection.style.display !== 'none') {
    console.log('📦 Import-Fortschritt-Sektion ist sichtbar - starte Queue-Monitor sofort');
    QueueMonitor.start('queue-status');
    monitorQueueCompletion();
  }
});