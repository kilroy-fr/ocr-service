// ========================================
// GLOBALE VARIABLEN & UTILITY-FUNKTIONEN
// ========================================

let processedFiles = {};
let currentTab = 'medidok';

try {
  const serverData = window.processedFilesData || {};
  processedFiles = serverData;
  console.log('📋 Verarbeitete Dateien beim Laden:', processedFiles);
} catch(e) {
  console.error('❌ Fehler beim Parsen der Server-Daten:', e);
}

// Tab-spezifische Konfiguration (Selektoren, IDs, Sortier-Container)
const TAB_CONFIG = {
  medidok: {
    prefix: 'medi',
    checkboxSelector: 'input[name="selected_files"]:not(:disabled)',
    checkedSelector: 'input[name="selected_files"]:checked:not(:disabled)',
    previewId: 'preview',
    stagedContainerId: 'stagedFiles',
    sortContainers: ['fileList', 'stagedFiles']
  },
  einzel: {
    prefix: 'einzel',
    checkboxSelector: '#einzelStagedFiles input[type="checkbox"]:not(:disabled)',
    checkedSelector: '#einzelStagedFiles input[type="checkbox"]:checked:not(:disabled)',
    previewId: 'einzelPreview',
    stagedContainerId: 'einzelStagedFiles',
    sortContainers: ['einzelStagedFiles']
  },
  batch: {
    prefix: 'batch',
    checkboxSelector: '#batchStagedFiles input[type="checkbox"]:not(:disabled)',
    checkedSelector: '#batchStagedFiles input[type="checkbox"]:checked:not(:disabled)',
    previewId: 'batchPreview',
    stagedContainerId: 'batchStagedFiles',
    sortContainers: ['batchStagedFiles']
  }
};

function showSpinner(on = true) {
  const el = document.getElementById("spinnerOverlay");
  if (el) el.style.display = on ? "flex" : "none";
}

const getExtension = f => (f.split(".").pop() || "").toLowerCase();

async function loadProcessedFiles() {
  try {
    const res = await fetch('/get_processed_files');
    const data = await res.json();
    if (data.success && data.processed_files) {
      processedFiles = data.processed_files;
      updateAllFileLists();
    }
  } catch (e) {
    console.error('❌ Fehler beim Laden der verarbeiteten Dateien:', e);
  }
}

function updateAllFileLists() {
  updateFileListUI('medidok');
  updateFileListUI('einzel');
  updateFileListUI('batch');
}

function updateFileListUI(tab = currentTab) {
  const selector = tab === 'medidok' ? '#fileList .file-item, #stagedFiles .file-item' :
                   tab === 'einzel' ? '#einzelStagedFiles .file-item' :
                   '#batchStagedFiles .file-item';
  
  document.querySelectorAll(selector).forEach(item => {
    const filename = item.getAttribute('data-filename');
    if (processedFiles[filename]) {
      const info = processedFiles[filename];
      item.classList.add('processed');
      
      const checkbox = item.querySelector('input[type="checkbox"]');
      if (checkbox) {
        checkbox.disabled = true;
        checkbox.checked = false;
      }
      
      if (!item.querySelector('.operation-badge')) {
        const label = item.querySelector('.file-label');
        const badge = document.createElement('span');
        badge.className = 'operation-badge ' + (info.operation === 'merged' ? 'merged' : 'split');
        
        if (info.operation === 'merged') {
          badge.textContent = ' 🧩 zusammengefügt';
          const resultName = info.result ? info.result.split('/').pop() : 'combined PDF';
          item.setAttribute('data-tooltip', `Wurde mit anderen Dateien zusammengefügt zu: ${resultName}`);
        } else if (info.operation === 'split') {
          badge.textContent = ' 🔪 zerlegt';
          item.setAttribute('data-tooltip', `Wurde in ${info.result_count || '?'} Einzelseiten zerlegt`);
        }
        
        label.appendChild(badge);
      }
    }
  });
  updateButtonStates(tab);
}

function setupPreview(tab) {
  const previewId = TAB_CONFIG[tab].previewId;

  document.addEventListener('click', (e) => {
    const label = e.target.closest('.file-label');
    if (!label) return;

    const item = label.closest('.file-item');
    if (item && item.classList.contains('processed')) return;

    const filename = label.getAttribute("data-file");
    console.log(`🔍 Vorschau für Datei: "${filename}"`);

    const ext = getExtension(filename);
    console.log(`📎 Dateiendung: "${ext}"`);

    let content = "";

    if (["jpg","jpeg","png"].includes(ext)) {
      const previewUrl = `/preview/${encodeURIComponent(filename)}`;
      console.log(`🖼️ Bild-Vorschau URL: ${previewUrl}`);
      content = `<img src="${previewUrl}" alt="Bildvorschau"
                      onload="console.log('✅ Bild geladen:', '${filename}')"
                      onerror="console.error('❌ Bild-Ladefehler:', '${filename}', this.src)">`;
    } else if (ext === "pdf") {
      const previewUrl = `/preview/${encodeURIComponent(filename)}#page=1&zoom=fit`;
      console.log(`📄 PDF-Vorschau URL: ${previewUrl}`);
      content = `<iframe src="${previewUrl}" scrolling="no"></iframe>`;
    } else if (ext === "txt") {
      const previewUrl = `/preview/${encodeURIComponent(filename)}`;
      console.log(`📝 TXT-Vorschau URL: ${previewUrl}`);
      content = `<iframe src="${previewUrl}" scrolling="auto" style="background: #1e1e1e;"></iframe>`;
    } else {
      content = "<p>Dateiformat wird nicht unterstützt.</p>";
    }

    const preview = document.getElementById(previewId);
    if (preview) {
      preview.innerHTML = content;
    }
    document.querySelectorAll(".file-label").forEach(l => l.classList.remove("active"));
    label.classList.add("active");
  });
}

async function loadStagedFiles(tab = 'medidok') {
  try {
    const res = await fetch('/list_staged_files');
    const data = await res.json();

    console.log(`📋 loadStagedFiles(${tab}) - Server-Response:`, data);

    const containerId = TAB_CONFIG[tab].stagedContainerId;

    const container = document.getElementById(containerId);
    if (!container) return;

    if (!data.success || !data.files || data.files.length === 0) {
      container.innerHTML = '<p style="color: #999; font-style: italic;">Keine bearbeiteten Dateien</p>';
      return;
    }

    container.innerHTML = '';
    data.files.forEach(file => {
      const div = document.createElement('div');
      div.className = 'file-item';
      div.setAttribute('data-filename', file);

      const isProcessed = processedFiles[file];
      if (isProcessed) div.classList.add('processed');

      console.log(`📄 Erstelle Datei-Item: ${file} (data-file="${file}")`);

      div.innerHTML = `
        <input type="checkbox" name="selected_files" value="${file}" class="file-checkbox" ${isProcessed ? 'disabled' : ''}>
        <label class="file-label" data-file="${file}" style="color: #0066cc;">📄 ${file}</label>
      `;
      container.appendChild(div);
    });
    
    updateFileListUI(tab);

    // Sortierung für den Container re-initialisieren
    if (window.FileSorting) {
      window.FileSorting.init(containerId);
    }
  } catch (e) {
    console.error('Fehler beim Laden der Staging-Dateien:', e);
  }
}

function updateMasterCheckbox(tab) {
  const config = {
    medidok: {
      checkbox: 'masterCheckbox',
      label: 'masterCheckboxLabel',
      count: 'selectionCount',
      selector: 'input[name="selected_files"]:not(:disabled)'
    },
    einzel: {
      checkbox: 'einzelMasterCheckbox',
      label: 'einzelMasterCheckboxLabel',
      count: 'einzelSelectionCount',
      selector: '#einzelStagedFiles input[type="checkbox"]:not(:disabled)'
    },
    batch: {
      checkbox: 'batchMasterCheckbox',
      label: 'batchMasterCheckboxLabel',
      count: 'batchSelectionCount',
      selector: '#batchStagedFiles input[type="checkbox"]:not(:disabled)'
    }
  };
  
  const cfg = config[tab];
  if (!cfg) return;
  
  const masterCheckbox = document.getElementById(cfg.checkbox);
  const selectionCount = document.getElementById(cfg.count);
  const masterLabel = document.getElementById(cfg.label);
  
  if (!masterCheckbox) return;
  
  const selectableCheckboxes = Array.from(document.querySelectorAll(cfg.selector));
  const checkedCount = selectableCheckboxes.filter(cb => cb.checked).length;
  const totalCount = selectableCheckboxes.length;
  
  if (checkedCount === 0) {
    masterCheckbox.checked = false;
    masterCheckbox.indeterminate = false;
    masterLabel.textContent = 'Alle auswählbaren Dateien auswählen';
  } else if (checkedCount === totalCount) {
    masterCheckbox.checked = true;
    masterCheckbox.indeterminate = false;
    masterLabel.textContent = 'Alle abwählen';
  } else {
    masterCheckbox.checked = false;
    masterCheckbox.indeterminate = true;
    masterLabel.textContent = 'Einige ausgewählt';
  }
  
  if (selectionCount) {
    selectionCount.textContent = `${checkedCount} / ${totalCount}`;
  }
}

function setupMasterCheckbox(tab) {
  const config = {
    medidok: {
      checkbox: 'masterCheckbox',
      selector: 'input[name="selected_files"]:not(:disabled)'
    },
    einzel: {
      checkbox: 'einzelMasterCheckbox',
      selector: '#einzelStagedFiles input[type="checkbox"]:not(:disabled)'
    },
    batch: {
      checkbox: 'batchMasterCheckbox',
      selector: '#batchStagedFiles input[type="checkbox"]:not(:disabled)'
    }
  };
  
  const cfg = config[tab];
  if (!cfg) return;
  
  const masterCheckbox = document.getElementById(cfg.checkbox);
  if (!masterCheckbox) return;
  
  masterCheckbox.addEventListener('change', (e) => {
    const shouldCheck = e.target.checked || e.target.indeterminate;
    const selectableCheckboxes = document.querySelectorAll(cfg.selector);
    selectableCheckboxes.forEach(cb => cb.checked = shouldCheck);
    updateButtonStates(tab);
  });
}

// ========================================
// ANALYSE
// ========================================

async function handleAnalyze(tab) {
  const cfg = TAB_CONFIG[tab];
  const selected = Array.from(document.querySelectorAll(cfg.checkedSelector)).map(cb => cb.value);

  if (selected.length === 0) {
    Notifications.warning("Bitte mindestens eine Datei auswählen.");
    return;
  }

  showSpinner(true);
  try {
    const res = await fetch("/copy_and_analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: selected })
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok || !data.success) {
      Notifications.error("Fehler beim Analysieren: " + (data.message || `HTTP ${res.status}`));
      return;
    }

    if (data.progressive) {
      console.log(`📊 Progressive Analyse: ${data.completed}/${data.total} Dateien fertig`);
      console.log(`🔄 ${data.total - data.completed} Dateien werden im Hintergrund analysiert`);
    }

    window.location.href = "/control?index=0&progressive=" + (data.progressive ? "true" : "false");
  } catch (err) {
    console.error(`[${tab} analyze] Fehler:`, err);
    Notifications.error("Netzwerk-/JS-Fehler: " + err);
  } finally {
    showSpinner(false);
  }
}


// ========================================
// MODELL-VERWALTUNG
// ========================================

async function loadModels() {
  console.log('📄 loadModels() gestartet');
  const select = document.getElementById("modelSelect");
  if (!select) {
    console.warn('⚠️ modelSelect nicht gefunden');
    return;
  }
  
  try {
    console.log('📡 Fetching /available_models...');
    const res = await fetch("/available_models");
    const data = await res.json();
    console.log('📦 Server-Response:', data);
    
    if (!res.ok || !data.success) {
      console.error('❌ Fehler beim Laden der Modelle:', data);
      return;
    }
    
    const models = data.models || [];
    const currentModel = data.current || null;
    
    console.log('📋 Verfügbare Modelle:', models);
    console.log('✅ Aktuelles Modell:', currentModel);
    
    select.innerHTML = '';
    
    if (models.length === 0) {
      const opt = document.createElement("option");
      opt.textContent = "Keine Modelle verfügbar";
      opt.disabled = true;
      select.appendChild(opt);
      select.disabled = true;
      return;
    }
    
    const modelExists = models.includes(currentModel);
    
    models.forEach(model => {
      const opt = document.createElement("option");
      opt.value = model;
      opt.textContent = model;
      select.appendChild(opt);
    });
    
    if (modelExists) {
      select.value = currentModel;
      console.log(`✓ Server-Modell "${currentModel}" im Dropdown gesetzt`);
    } else if (currentModel) {
      console.warn(`⚠️ Modell "${currentModel}" nicht in Ollama-Liste gefunden!`);
      select.selectedIndex = 0;
      const firstModel = models[0];
      await fetch("/set_model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: firstModel })
      });
      console.log(`🔄 Wechsel zu verfügbarem Modell: ${firstModel}`);
    } else if (models.length > 0) {
      select.selectedIndex = 0;
      const firstModel = models[0];
      console.log(`⚙️ Kein Modell gesetzt - wähle erstes: ${firstModel}`);
      await fetch("/set_model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: firstModel })
      });
    }
    
    console.log(`🔍 Dropdown zeigt: "${select.value}"`);
    
    if (data.fallback) {
      console.warn('⚠️ Ollama nicht erreichbar - Fallback-Modelle angezeigt');
    }
    
    console.log('✅ loadModels() abgeschlossen');
    
  } catch (e) {
    console.error("❌ Fehler beim Laden der Modelle:", e);
    select.innerHTML = '<option disabled>Fehler beim Laden</option>';
    select.disabled = true;
  }
}

// ========================================
// TAB-VERWALTUNG
// ========================================

function switchTab(tabName) {
  const tabButtons = document.querySelectorAll('.tab-button');
  const tabContents = document.querySelectorAll('.tab-content');

  tabButtons.forEach(btn => btn.classList.remove("active"));
  tabContents.forEach(content => content.classList.remove("active"));

  document.querySelector(`.tab-button[data-tab="${tabName}"]`)?.classList.add("active");
  document.getElementById(tabName)?.classList.add("active");

  currentTab = tabName;

  // Dateibearbeitungs-Buttons für den aktiven Tab anzeigen
  updateFileOpsButtons(tabName);
}

function updateFileOpsButtons(tab) {
  ['medidok', 'einzel', 'batch'].forEach(t => {
    const p = TAB_CONFIG[t].prefix;
    const isActive = t === tab;
    ['Combine', 'Split', 'OcrOnly', 'Download'].forEach(type => {
      const btn = document.getElementById(`${p}${type}`);
      if (btn) btn.style.display = isActive ? 'inline-block' : 'none';
    });
    const rotCtrl = document.getElementById(`${p}Rotation`);
    if (rotCtrl) rotCtrl.style.display = isActive ? 'inline-flex' : 'none';
  });
}

// ========================================
// MEDIDOK-TAB FUNKTIONEN
// ========================================


/**
 * Verschiebt die kombinierte Datei direkt unter die erste ausgeblendete Datei.
 * @param {string} containerId - ID des Containers (z.B. 'stagedFiles')
 * @param {string} combinedFilename - Name der kombinierten Datei
 * @param {Array<string>} processedFilesList - Liste der verarbeiteten Dateinamen
 */
function repositionCombinedFile(containerId, combinedFilename, processedFilesList) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const allItems = Array.from(container.querySelectorAll('.file-item'));

  // Finde die kombinierte Datei
  const combinedItem = allItems.find(item =>
    item.getAttribute('data-filename') === combinedFilename
  );

  if (!combinedItem) {
    console.warn(`Kombinierte Datei "${combinedFilename}" nicht gefunden`);
    return;
  }

  // Finde die erste ausgeblendete Datei (processed)
  const firstProcessedItem = allItems.find(item =>
    processedFilesList.includes(item.getAttribute('data-filename'))
  );

  if (firstProcessedItem) {
    // Füge die kombinierte Datei direkt nach der ersten ausgeblendeten Datei ein
    firstProcessedItem.insertAdjacentElement('afterend', combinedItem);
    console.log(`✅ Kombinierte Datei "${combinedFilename}" direkt unter "${firstProcessedItem.getAttribute('data-filename')}" verschoben`);
  } else {
    console.warn('Keine ausgeblendete Datei gefunden');
  }
}

async function handleCombine(tab) {
  const cfg = TAB_CONFIG[tab];
  let selected;
  if (window.FileSorting) {
    selected = cfg.sortContainers.flatMap(id => window.FileSorting.getOrder(id));
  } else {
    selected = Array.from(document.querySelectorAll(cfg.checkedSelector)).map(cb => cb.value);
  }

  if (selected.length < 2) {
    Notifications.warning("Bitte mindestens zwei Dateien auswählen.");
    return;
  }

  showSpinner(true);
  try {
    const res = await fetch("/combine_medidok", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: selected })
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok || !data.success) {
      Notifications.error("Fehler beim Zusammenfassen: " + (data.message || `HTTP ${res.status}`));
      return;
    }

    console.log(`✅ ${selected.length} Dateien zusammengefügt: ${data.combined}`);

    if (data.processed_files) {
      data.processed_files.forEach(file => {
        processedFiles[file] = { operation: 'merged', timestamp: Date.now() / 1000, result: data.combined };
      });
    }

    await loadStagedFiles(tab);
    updateFileListUI(tab);
    repositionCombinedFile(cfg.stagedContainerId, data.combined, data.processed_files || []);

    const preview = document.getElementById(cfg.previewId);
    if (preview) {
      preview.innerHTML = `<iframe src="/processed/${encodeURIComponent(data.combined)}#page=1&zoom=fit" scrolling="no"></iframe>`;
    }
  } catch (err) {
    console.error(`[${tab} combine] Fehler:`, err);
    Notifications.error("Netzwerk-/JS-Fehler: " + err);
  } finally {
    showSpinner(false);
  }
}

async function handleSplit(tab) {
  const cfg = TAB_CONFIG[tab];
  const selected = Array.from(document.querySelectorAll(cfg.checkedSelector)).map(cb => cb.value);

  if (selected.length !== 1) {
    Notifications.warning("Bitte genau eine Datei auswählen.");
    return;
  }

  const filename = selected[0];
  if (!filename.toLowerCase().endsWith('.pdf')) {
    Notifications.warning("Nur PDF-Dateien können zerlegt werden.");
    return;
  }

  showSpinner(true);
  try {
    const res = await fetch("/split_pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: filename })
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok || !data.success) {
      Notifications.error("Fehler beim Zerlegen: " + (data.message || `HTTP ${res.status}`));
      return;
    }

    Notifications.success(`PDF in ${data.count} Einzelseiten zerlegt`);

    if (data.processed_file) {
      processedFiles[data.processed_file] = { operation: 'split', timestamp: Date.now() / 1000, result_count: data.count };
    }

    await loadStagedFiles(tab);
    updateFileListUI(tab);
  } catch (err) {
    console.error(`[${tab} split] Fehler:`, err);
    Notifications.error("Netzwerk-/JS-Fehler: " + err);
  } finally {
    showSpinner(false);
  }
}

// ========================================
// DOWNLOAD SELECTED FILES
// ========================================

async function handleDownload(tab) {
  const cfg = TAB_CONFIG[tab];
  const selected = Array.from(document.querySelectorAll(cfg.checkedSelector)).map(cb => cb.value);

  if (selected.length === 0) {
    Notifications.warning("Bitte mindestens eine Datei auswählen.");
    return;
  }

  console.log(`💾 Starte Download für ${selected.length} Datei(en)`);

  if (selected.length === 1) {
    // Einzelne Datei: Direkt herunterladen
    const filename = selected[0];
    const downloadUrl = `/download_staged/${encodeURIComponent(filename)}`;
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    console.log(`✅ Download gestartet: ${filename}`);
    Notifications.success("Download gestartet");
  } else {
    // Mehrere Dateien: ZIP erstellen und herunterladen
    showSpinner(true);
    try {
      const res = await fetch("/download_multiple_as_zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: selected })
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        Notifications.error("Fehler beim Erstellen des ZIP-Archives: " + (data.message || `HTTP ${res.status}`));
        return;
      }

      // ZIP-Datei als Blob herunterladen
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `download_${new Date().toISOString().slice(0,10)}.zip`;
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      console.log(`✅ ZIP-Download gestartet: ${selected.length} Dateien`);
      Notifications.success(`${selected.length} Dateien als ZIP heruntergeladen`);
    } catch (err) {
      console.error('[download] Fehler:', err);
      Notifications.error("Netzwerk-/JS-Fehler: " + err);
    } finally {
      showSpinner(false);
    }
  }
}

// ========================================
// OCR ONLY
// ========================================

async function handleOcrOnly(tab) {
  const cfg = TAB_CONFIG[tab];
  const selected = Array.from(document.querySelectorAll(cfg.checkedSelector)).map(cb => cb.value);

  if (selected.length === 0) {
    Notifications.warning("Bitte mindestens eine Datei auswählen.");
    return;
  }

  showSpinner(true);
  try {
    const res = await fetch("/ocr_only", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: selected })
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok || !data.success) {
      Notifications.error("Fehler beim OCR: " + (data.message || `HTTP ${res.status}`));
      return;
    }

    const successful = data.results.filter(r => r.success);
    const failed = data.results.filter(r => !r.success);

    if (failed.length > 0) {
      console.error('OCR-Fehler:', failed);
    }

    // Download für erfolgreiche OCR-Dateien
    if (successful.length > 0) {
      console.log(`📥 Starte Download für ${successful.length} OCR-Datei(en)`);

      if (successful.length === 1) {
        // Einzelne Datei: Direkt herunterladen
        const downloadUrl = `/download_ocr/${encodeURIComponent(successful[0].ocr_file)}`;
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = successful[0].ocr_file;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        console.log(`✅ Download gestartet: ${successful[0].ocr_file}`);
        if (failed.length > 0) {
          Notifications.warning(`1 von ${data.results.length} Dateien erfolgreich verarbeitet`);
        } else {
          Notifications.success("OCR-Datei wird heruntergeladen");
        }
      } else {
        // Mehrere Dateien: Als ZIP herunterladen
        const ocrFiles = successful.map(r => r.ocr_file);
        const zipRes = await fetch("/download_multiple_as_zip", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ files: ocrFiles })
        });

        if (!zipRes.ok) {
          const zipData = await zipRes.json().catch(() => ({}));
          Notifications.error("Fehler beim Erstellen des ZIP-Archives: " + (zipData.message || `HTTP ${zipRes.status}`));
          return;
        }

        const blob = await zipRes.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `ocr_${new Date().toISOString().slice(0, 10)}.zip`;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
        console.log(`✅ ZIP-Download gestartet: ${successful.length} OCR-Dateien`);
        if (failed.length > 0) {
          Notifications.warning(`${successful.length} von ${data.results.length} Dateien erfolgreich verarbeitet und als ZIP heruntergeladen`);
        } else {
          Notifications.success(`${successful.length} OCR-Dateien als ZIP heruntergeladen`);
        }
      }
    }

    // WICHTIG: loadStagedFiles NICHT aufrufen, damit OCR-Dateien nicht in der Liste erscheinen
    // await loadStagedFiles(tab);  <-- ENTFERNT

  } catch (err) {
    console.error(`[${tab} ocr only] Fehler:`, err);
    Notifications.error("Netzwerk-/JS-Fehler: " + err);
  } finally {
    showSpinner(false);
  }
}

// ========================================
// BUTTON-STATUS UPDATE
// ========================================

function updateButtonStates(tab = currentTab) {
  const cfg = TAB_CONFIG[tab];
  const p = cfg.prefix;

  const checkboxes = document.querySelectorAll(cfg.checkboxSelector);
  const submitBtn = document.getElementById(p === 'medi' ? 'medidokSubmit' : `${p}Analyze`);
  const combineBtn = document.getElementById(`${p}Combine`);
  const splitBtn = document.getElementById(`${p}Split`);
  const ocrOnlyBtn = document.getElementById(`${p}OcrOnly`);
  const downloadBtn = document.getElementById(`${p}Download`);
  const rotateLeftBtn = document.getElementById(`${p}RotateLeft`);
  const rotate180Btn = document.getElementById(`${p}Rotate180`);
  const rotateRightBtn = document.getElementById(`${p}RotateRight`);

  const selected = Array.from(checkboxes).filter(cb => cb.checked);
  const count = selected.length;

  if (submitBtn) submitBtn.disabled = count === 0;
  if (combineBtn) combineBtn.disabled = count < 2;
  if (splitBtn) {
    const onePdfSelected = count === 1 && selected[0].value.toLowerCase().endsWith('.pdf');
    splitBtn.disabled = !onePdfSelected;
  }
  if (ocrOnlyBtn) ocrOnlyBtn.disabled = count === 0;
  if (downloadBtn) downloadBtn.disabled = count === 0;

  const oneRotatableSelected = count === 1 &&
    ['pdf', 'jpg', 'jpeg', 'png'].includes(getExtension(selected[0].value));
  if (rotateLeftBtn) rotateLeftBtn.disabled = !oneRotatableSelected;
  if (rotate180Btn) rotate180Btn.disabled = !oneRotatableSelected;
  if (rotateRightBtn) rotateRightBtn.disabled = !oneRotatableSelected;

  updateFloatingAnalyzeButton(count > 0);

  if (tab === 'medidok') updateMasterCheckbox('medidok');
  else if (tab === 'einzel') updateMasterCheckbox('einzel');
  else if (tab === 'batch') updateMasterCheckbox('batch');
}

// ========================================
// ROTATIONS-FUNKTIONEN (VOR ANALYSE)
// ========================================

async function rotateFile(direction, tab = currentTab) {
  const cfg = TAB_CONFIG[tab];
  const p = cfg.prefix;

  const selected = Array.from(document.querySelectorAll(cfg.checkedSelector));
  if (selected.length !== 1) {
    Notifications.warning("Bitte genau eine Datei zum Drehen auswählen.");
    return;
  }

  const filename = selected[0].value;
  const ext = getExtension(filename);

  if (!['pdf', 'jpg', 'jpeg', 'png'].includes(ext)) {
    Notifications.warning("Nur PDF und Bilddateien (JPG, PNG) können gedreht werden.");
    return;
  }

  const rotateLeftBtn = document.getElementById(`${p}RotateLeft`);
  const rotate180Btn = document.getElementById(`${p}Rotate180`);
  const rotateRightBtn = document.getElementById(`${p}RotateRight`);

  if (rotateLeftBtn) rotateLeftBtn.disabled = true;
  if (rotate180Btn) rotate180Btn.disabled = true;
  if (rotateRightBtn) rotateRightBtn.disabled = true;

  showSpinner(true);

  try {
    const res = await fetch('/rotate_file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, direction })
    });

    const data = await res.json();

    if (!res.ok || !data.success) {
      Notifications.error('Fehler beim Drehen: ' + (data.message || `HTTP ${res.status}`));
      return;
    }

    // Erfolg
    const angleText = direction === 'left' ? '90° links' :
                      direction === 'right' ? '90° rechts' : '180°';
    Notifications.success(`Datei um ${angleText} gedreht`);

    // Vorschau aktualisieren mit Cache-Busting
    const preview = document.getElementById(cfg.previewId);

    if (preview) {
      const timestamp = new Date().getTime();

      if (ext === 'pdf') {
        preview.innerHTML = `<iframe src="/preview/${encodeURIComponent(filename)}?t=${timestamp}#page=1&zoom=fit" scrolling="no"></iframe>`;
      } else {
        preview.innerHTML = `<img src="/preview/${encodeURIComponent(filename)}?t=${timestamp}" alt="Bildvorschau">`;
      }
    }

    // Bei Medidok: Staging-Liste aktualisieren (falls Datei kopiert wurde)
    if (tab === 'medidok') {
      await loadStagedFiles('medidok');
    }

    console.log(`✅ Datei gedreht: ${filename} (${direction})`);

  } catch (err) {
    console.error('[rotate_file] Fehler:', err);
    Notifications.error('Netzwerk-/JS-Fehler: ' + err);
  } finally {
    showSpinner(false);
    // Buttons wieder aktivieren
    updateButtonStates(tab);
  }
}

// ========================================
// FLOATING ANALYSE BUTTON
// ========================================

function updateFloatingAnalyzeButton(hasSelection) {
  const floatingBtn = document.getElementById('floatingAnalyzeBtn');
  if (!floatingBtn) return;

  if (hasSelection) {
    floatingBtn.classList.remove('hidden');
    floatingBtn.disabled = false;
  } else {
    floatingBtn.classList.add('hidden');
    floatingBtn.disabled = true;
  }
}

function handleFloatingAnalyze() {
  handleAnalyze(currentTab);
}

// ========================================
// STICKY HEADER SCROLL EFFECT
// ========================================

function handleFileOpsScroll() {
  const fileOpsSection = document.querySelector('.file-ops-section');
  if (!fileOpsSection) return;

  const scrollTop = window.scrollY || document.documentElement.scrollTop;

  if (scrollTop > 50) {
    fileOpsSection.classList.add('scrolled');
  } else {
    fileOpsSection.classList.remove('scrolled');
  }
}

// ========================================
// INITIALISIERUNG
// ========================================

window.addEventListener("DOMContentLoaded", async () => {
  console.log('🚀 DOMContentLoaded - Initialisierung startet');

  // Setup für alle Tabs
  setupPreview('medidok');
  setupPreview('einzel');
  setupPreview('batch');
  setupMasterCheckbox('medidok');
  setupMasterCheckbox('einzel');
  setupMasterCheckbox('batch');
  updateAllFileLists();
  await loadStagedFiles('medidok');
  updateMasterCheckbox('medidok');

  // Initiale Button-Sichtbarkeit setzen
  updateFileOpsButtons('medidok');

  // Sortier-Funktionalität für alle Dateilisten initialisieren
  if (window.FileSorting) {
    window.FileSorting.init('fileList');
    window.FileSorting.init('stagedFiles');
    window.FileSorting.init('einzelStagedFiles');
    window.FileSorting.init('batchStagedFiles');
    console.log('✅ Datei-Sortierung initialisiert');
  }

  // Checkbox-Listener (Global für alle Tabs)
  document.addEventListener('change', (e) => {
    if (e.target.matches('input[type="checkbox"]')) {
      updateButtonStates(currentTab);
    }
  });

  // Reload-Button Event-Listener
  const reloadBtn = document.getElementById('reloadBtn');
  if (reloadBtn) {
    reloadBtn.addEventListener('click', () => {
      location.reload();
    });
  }

  // Floating Analyse Button Event-Listener
  const floatingAnalyzeBtn = document.getElementById('floatingAnalyzeBtn');
  if (floatingAnalyzeBtn) {
    floatingAnalyzeBtn.addEventListener('click', handleFloatingAnalyze);
  }

  // Scroll Event für Sticky Header Effekt
  window.addEventListener('scroll', handleFileOpsScroll);
  handleFileOpsScroll(); // Initial check

  // Logging via SSE
  try {
    const es = new EventSource("/stream");
    es.onmessage = e => { 
      const outputEl = document.getElementById("output");
      if (outputEl) {
        outputEl.textContent += e.data + "\n"; 
        outputEl.scrollTop = outputEl.scrollHeight;
      }
    };
    es.onerror = () => { 
      const outputEl = document.getElementById("output");
      if (outputEl) {
        outputEl.textContent += "\n[Verbindung zum Server unterbrochen]\n";
      }
    };
  } catch(e) {
    console.error('SSE Fehler:', e);
  }

  // Initiale Vorschau (Medidok)
  setTimeout(() => {
    const firstLabel = document.querySelector(".file-label:not(.file-item.processed .file-label)");
    if (firstLabel) firstLabel.click();
  }, 100);

  // Tab-Wechsel
  const tabButtons = document.querySelectorAll('.tab-button');
  
  const restoredTab = localStorage.getItem("activeTabAfterReset");
  if (restoredTab) { 
    switchTab(restoredTab); 
    localStorage.removeItem("activeTabAfterReset"); 
  }
  
  tabButtons.forEach(button => {
    button.addEventListener("click", async () => {
      const targetTab = button.getAttribute("data-tab");
      const currentTabActive = document.querySelector(".tab-button.active")?.getAttribute("data-tab");
      
      if (targetTab && targetTab !== currentTabActive) {
        showSpinner(true);
        
        try {
          const res = await fetch("/reset_session");
          if (res.ok) {
            switchTab(targetTab);

            const preview = document.getElementById(TAB_CONFIG[targetTab].previewId);
            if (preview) {
              preview.innerHTML = '<p style="color: #666;">Keine Vorschau verfügbar</p>';
            }
            
            await loadStagedFiles(targetTab);
            updateButtonStates(targetTab);
          }
        } catch (err) {
          console.error("Fehler beim Session-Reset:", err);
        } finally {
          showSpinner(false);
        }
      }
    });
  });

  // ===== TAB-BUTTONS (Analyse, Combine, Split, OCR, Download, Rotation) =====
  ['medidok', 'einzel', 'batch'].forEach(tab => {
    const p = TAB_CONFIG[tab].prefix;
    const analyzeId = p === 'medi' ? 'medidokSubmit' : `${p}Analyze`;

    const analyzeBtn = document.getElementById(analyzeId);
    if (analyzeBtn) analyzeBtn.addEventListener('click', () => handleAnalyze(tab));

    const combineBtn = document.getElementById(`${p}Combine`);
    if (combineBtn) combineBtn.addEventListener('click', () => handleCombine(tab));

    const splitBtn = document.getElementById(`${p}Split`);
    if (splitBtn) splitBtn.addEventListener('click', () => handleSplit(tab));

    const ocrBtn = document.getElementById(`${p}OcrOnly`);
    if (ocrBtn) ocrBtn.addEventListener('click', () => handleOcrOnly(tab));

    const downloadBtn = document.getElementById(`${p}Download`);
    if (downloadBtn) downloadBtn.addEventListener('click', () => handleDownload(tab));

    const dirMap = { Left: 'left', '180': '180', Right: 'right' };
    ['Left', '180', 'Right'].forEach(dir => {
      const btn = document.getElementById(`${p}Rotate${dir}`);
      if (btn) btn.addEventListener('click', () => rotateFile(dirMap[dir], tab));
    });
  });

  // ===== EINZEL-UPLOAD =====
  const fileInput = document.getElementById("fileInput");
  if (fileInput) {
    fileInput.addEventListener("change", async function () {
      const files = this.files;
      if (!files || files.length === 0) return;

      showSpinner(true);
      const formData = new FormData();
      for (let file of files) formData.append('files', file);

      try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        const data = await res.json();

        if (!res.ok || !data.success) {
          Notifications.error('Fehler beim Upload: ' + (data.message || `HTTP ${res.status}`));
          return;
        }

        console.log('📤 Upload-Response:', data);
        await loadStagedFiles('einzel');

        setTimeout(() => {
          const checkboxes = document.querySelectorAll('#einzelStagedFiles input[type="checkbox"]:not(:disabled)');
          checkboxes.forEach(cb => cb.checked = true);
          updateButtonStates('einzel');
          const firstLabel = document.querySelector("#einzelStagedFiles .file-label");
          if (firstLabel) firstLabel.click();
        }, 100);

        console.log(`✅ ${files.length} Datei(en) hochgeladen und bereit zur Analyse`);
      } catch (err) {
        console.error('[einzel upload] Fehler:', err);
        Notifications.error('Netzwerk-/JS-Fehler: ' + err);
      } finally {
        showSpinner(false);
      }
    });
  }

  // ===== BATCH-UPLOAD =====
  const folderInput = document.getElementById("folderInput");
  if (folderInput) {
    folderInput.addEventListener("change", async function() {
      const files = this.files;
      if (!files || files.length === 0) return;

      showSpinner(true);
      const formData = new FormData();
      for (let file of files) formData.append('files', file);

      try {
        const res = await fetch('/upload_folder', { method: 'POST', body: formData });
        const data = await res.json();

        if (!res.ok || !data.success) {
          Notifications.error('Fehler beim Upload: ' + (data.message || `HTTP ${res.status}`));
          return;
        }

        await loadStagedFiles('batch');
        console.log(`✅ ${files.length} Datei(en) hochgeladen und bereit zur Analyse`);

        setTimeout(() => {
          const firstLabel = document.querySelector("#batchStagedFiles .file-label");
          if (firstLabel) firstLabel.click();
        }, 100);
      } catch (err) {
        console.error('[batch upload] Fehler:', err);
        Notifications.error('Netzwerk-/JS-Fehler: ' + err);
      } finally {
        showSpinner(false);
      }
    });
  }

  // ===== MODELL-VERWALTUNG =====
  
  loadModels().catch(err => console.error('❌ loadModels() failed:', err));
  
  const modelSelect = document.getElementById("modelSelect");
  if (modelSelect) {
    modelSelect.addEventListener("change", async (e) => {
      const selectedModel = e.target.value;
      
      if (!selectedModel) {
        console.warn('⚠️ Kein Modell ausgewählt');
        return;
      }
      
      console.log(`🔄 Wechsle Modell zu: ${selectedModel}`);
      
      try {
        const res = await fetch("/set_model", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: selectedModel })
        });
        
        const data = await res.json();
        
        if (!data.success) {
          Notifications.error("Fehler beim Setzen des Modells: " + (data.message || "unbekannt"));
          return;
        }
        
        console.log('✅ Modell erfolgreich gewechselt:', selectedModel);
        
      } catch (err) {
        console.error('❌ Fehler beim Modellwechsel:', err);
        Notifications.error('Fehler beim Speichern der Modellauswahl');
      }
    });
  }

  // ========================================
  // CLEANUP STAGING VERZEICHNISSE
  // ========================================

  const cleanupStagingBtn = document.getElementById('cleanupStagingBtn');
  const cleanupStatus = document.getElementById('cleanupStatus');

  if (cleanupStagingBtn && cleanupStatus) {
    cleanupStagingBtn.addEventListener('click', async () => {
      if (!confirm('Möchten Sie wirklich alle alten Staging-Verzeichnisse löschen?\n\nEs werden nur Verzeichnisse gelöscht, die älter als 60 Minuten sind und nicht mehr aktiv verwendet werden.')) {
        return;
      }

      cleanupStagingBtn.disabled = true;
      cleanupStatus.textContent = '🔄 Lösche alte Verzeichnisse...';
      cleanupStatus.style.color = '#f59e0b';

      try {
        const res = await fetch('/cleanup_old_staging', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ max_age_minutes: 60 })
        });

        const data = await res.json();

        if (data.success) {
          cleanupStatus.textContent = `✅ ${data.deleted_count} Verzeichnisse gelöscht, ${data.skipped_count} übersprungen`;
          cleanupStatus.style.color = '#10b981';

          console.log('🧹 Cleanup-Ergebnis:', data);

          if (data.deleted_count > 0) {
            Notifications.success(`${data.deleted_count} alte Staging-Verzeichnisse wurden gelöscht`);
          } else {
            Notifications.info('Keine alten Verzeichnisse zum Löschen gefunden');
          }

          if (data.failed_count > 0) {
            Notifications.warning(`${data.failed_count} Verzeichnisse konnten nicht gelöscht werden`);
          }
        } else {
          cleanupStatus.textContent = '❌ Fehler beim Cleanup';
          cleanupStatus.style.color = '#dc2626';
          Notifications.error('Cleanup fehlgeschlagen: ' + (data.message || 'unbekannt'));
        }
      } catch (err) {
        console.error('❌ Cleanup-Fehler:', err);
        cleanupStatus.textContent = '❌ Fehler beim Cleanup';
        cleanupStatus.style.color = '#dc2626';
        Notifications.error('Fehler beim Cleanup: ' + err.message);
      } finally {
        cleanupStagingBtn.disabled = false;

        // Status nach 5 Sekunden zurücksetzen
        setTimeout(() => {
          cleanupStatus.textContent = '';
        }, 5000);
      }
    });
  }

  console.log('✅ Initialisierung abgeschlossen');
});