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
  const previewId = tab === 'medidok' ? 'preview' :
                    tab === 'einzel' ? 'einzelPreview' :
                    'batchPreview';
  
  document.addEventListener('click', (e) => {
    const label = e.target.closest('.file-label');
    if (!label) return;
    
    const item = label.closest('.file-item');
    if (item && item.classList.contains('processed')) return;
    
    const filename = label.getAttribute("data-file");
    const ext = getExtension(filename);
    let content = "";
    
    if (["jpg","jpeg","png"].includes(ext)) {
      content = `<img src="/preview/${encodeURIComponent(filename)}" alt="Bildvorschau">`;
    } else if (ext === "pdf") {
      content = `<iframe src="/preview/${encodeURIComponent(filename)}#page=1&zoom=fit" scrolling="no"></iframe>`;
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
    
    const containerId = tab === 'medidok' ? 'stagedFiles' :
                        tab === 'einzel' ? 'einzelStagedFiles' :
                        'batchStagedFiles';
    
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
      
      div.innerHTML = `
        <input type="checkbox" name="selected_files" value="${file}" class="file-checkbox" ${isProcessed ? 'disabled' : ''}>
        <label class="file-label" data-file="${file}" style="color: #0066cc;">📄 ${file}</label>
      `;
      container.appendChild(div);
    });
    
    updateFileListUI(tab);
  } catch (e) {
    console.error('Fehler beim Laden der Staging-Dateien:', e);
  }
}

function updateButtonStates(tab = currentTab) {
  const prefix = tab === 'medidok' ? 'medi' :
                 tab === 'einzel' ? 'einzel' :
                 'batch';
  
  const selector = tab === 'medidok' ? 
    'input[name="selected_files"]:not(:disabled)' :
    `#${tab === 'einzel' ? 'einzelStagedFiles' : 'batchStagedFiles'} input[type="checkbox"]:not(:disabled)`;
  
  const checkboxes = document.querySelectorAll(selector);
  const submitBtn = document.getElementById(prefix === 'medi' ? 'medidokSubmit' : `${prefix}Analyze`);
  const combineBtn = document.getElementById(`${prefix}Combine`);
  const splitBtn = document.getElementById(`${prefix}Split`);
  
  const selected = Array.from(checkboxes).filter(cb => cb.checked);
  const count = selected.length;
  
  if (submitBtn) submitBtn.disabled = count === 0;
  if (combineBtn) combineBtn.disabled = count < 2;
  if (splitBtn) {
    const onePdfSelected = count === 1 && selected[0].value.toLowerCase().endsWith('.pdf');
    splitBtn.disabled = !onePdfSelected;
  }
  
  // Master-Checkbox aktualisieren
  if (tab === 'medidok') {
    updateMasterCheckbox('medidok');
  } else if (tab === 'batch') {
    updateMasterCheckbox('batch');
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
// PROGRESSIVE ANALYSE - FUNKTIONEN
// ========================================

async function handleMedidokAnalyze() {
  const selected = Array.from(document.querySelectorAll('input[name="selected_files"]:checked:not(:disabled)'))
    .map(cb => cb.value);
  
  if (selected.length === 0) { 
    alert("Bitte mindestens eine Datei auswählen."); 
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
      alert("Fehler beim Analysieren: " + (data.message || `HTTP ${res.status}`));
      return;
    }
    
    // ✅ PROGRESSIVE ANALYSE: Sofort zu control.html weiterleiten
    if (data.progressive) {
      console.log(`📊 Progressive Analyse: ${data.completed}/${data.total} Dateien fertig`);
      console.log(`🔄 ${data.total - data.completed} Dateien werden im Hintergrund analysiert`);
    }
    
    // Immer zu control.html weiterleiten (auch bei nur einer Datei)
    window.location.href = "/control?index=0&progressive=" + (data.progressive ? "true" : "false");
    
  } catch (err) {
    console.error("[medidok analyze] Fehler:", err);
    alert("Netzwerk-/JS-Fehler: " + err);
  } finally {
    showSpinner(false);
  }
}

async function handleEinzelAnalyze() {
  const stagedFiles = Array.from(document.querySelectorAll('#einzelStagedFiles .file-item'))
    .map(item => item.getAttribute('data-filename'))
    .filter(f => f);
  
  if (stagedFiles.length === 0) {
    alert('Keine Dateien zum Analysieren vorhanden.');
    return;
  }
  
  showSpinner(true);
  
  try {
    const res = await fetch("/copy_and_analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: stagedFiles })
    });
    
    const data = await res.json().catch(() => ({}));
    
    if (!res.ok || !data.success) {
      alert("Fehler beim Analysieren: " + (data.message || `HTTP ${res.status}`));
      return;
    }
    
    // Progressive Analyse
    const progressive = data.progressive ? "true" : "false";
    window.location.href = `/control?index=0&progressive=${progressive}`;
    
  } catch (err) {
    console.error('[einzel analyze] Fehler:', err);
    alert('Netzwerk-/JS-Fehler: ' + err);
  } finally {
    showSpinner(false);
  }
}

async function handleBatchAnalyze() {
  const stagedFiles = Array.from(document.querySelectorAll('#batchStagedFiles .file-item'))
    .map(item => item.getAttribute('data-filename'))
    .filter(f => f);
  
  if (stagedFiles.length === 0) {
    alert('Keine Dateien zum Analysieren vorhanden.');
    return;
  }
  
  showSpinner(true);
  
  try {
    const res = await fetch("/copy_and_analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: stagedFiles })
    });
    
    const data = await res.json().catch(() => ({}));
    
    if (!res.ok || !data.success) {
      alert("Fehler beim Analysieren: " + (data.message || `HTTP ${res.status}`));
      return;
    }
    
    // Progressive Analyse
    const progressive = data.progressive ? "true" : "false";
    window.location.href = `/control?index=0&progressive=${progressive}`;
    
  } catch (err) {
    console.error('[batch analyze] Fehler:', err);
    alert('Netzwerk-/JS-Fehler: ' + err);
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
}

// ========================================
// MEDIDOK-TAB FUNKTIONEN
// ========================================


async function handleMedidokCombine() {
  const selected = Array.from(document.querySelectorAll('input[name="selected_files"]:checked:not(:disabled)'))
    .map(cb => cb.value);
  
  if (selected.length < 2) { 
    alert("Bitte mindestens zwei Dateien auswählen."); 
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
      alert("Fehler beim Zusammenfassen: " + (data.message || `HTTP ${res.status}`));
      return;
    }
    
    alert(`✅ ${selected.length} Dateien zusammengefügt: ${data.combined}`);
    
    if (data.processed_files) {
      data.processed_files.forEach(file => {
        processedFiles[file] = {
          operation: 'merged',
          timestamp: Date.now() / 1000,
          result: data.combined
        };
      });
      updateFileListUI('medidok');
    }
    
    await loadStagedFiles('medidok');
    
    const preview = document.getElementById("preview");
    const iframe = `<iframe src="/processed/${encodeURIComponent(data.combined)}#page=1&zoom=fit" scrolling="no"></iframe>`;
    preview.innerHTML = iframe;
    
  } catch (err) {
    console.error("[medidok combine] Fehler:", err);
    alert("Netzwerk-/JS-Fehler: " + err);
  } finally {
    showSpinner(false);
  }
}

async function handleMedidokSplit() {
  const selected = Array.from(document.querySelectorAll('input[name="selected_files"]:checked:not(:disabled)'))
    .map(cb => cb.value);
  
  if (selected.length !== 1) {
    alert("Bitte genau eine Datei auswählen.");
    return;
  }
  
  const filename = selected[0];
  if (!filename.toLowerCase().endsWith('.pdf')) {
    alert("Nur PDF-Dateien können zerlegt werden.");
    return;
  }

  if (!confirm(`PDF "${filename}" in einzelne Seiten zerlegen?\n\nDie Original-Datei bleibt unverändert.`)) {
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
      alert("Fehler beim Zerlegen: " + (data.message || `HTTP ${res.status}`));
      return;
    }
    
    alert(`✅ PDF in ${data.count} Einzelseiten zerlegt!\n\nDie Seiten wurden im Staging-Bereich erstellt.`);
    
    if (data.processed_file) {
      processedFiles[data.processed_file] = {
        operation: 'split',
        timestamp: Date.now() / 1000,
        result_count: data.count
      };
      updateFileListUI('medidok');
    }
    
    await loadStagedFiles('medidok');
    
  } catch (err) {
    console.error("[medidok split] Fehler:", err);
    alert("Netzwerk-/JS-Fehler: " + err);
  } finally {
    showSpinner(false);
  }
}

// ========================================
// EINZEL-UPLOAD FUNKTIONEN
// ========================================

async function handleEinzelCombine() {
  const selected = Array.from(document.querySelectorAll('#einzelStagedFiles input[type="checkbox"]:checked:not(:disabled)'))
    .map(cb => cb.value);
  
  if (selected.length < 2) {
    alert('Bitte mindestens zwei Dateien auswählen.');
    return;
  }
  
  showSpinner(true);
  try {
    const res = await fetch('/combine_medidok', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: selected })
    });
    
    const data = await res.json();
    
    if (!res.ok || !data.success) {
      alert('Fehler beim Kombinieren: ' + (data.message || `HTTP ${res.status}`));
      return;
    }
    
    console.log(`✅ ${selected.length} Dateien kombiniert: ${data.combined}`);
    
    if (data.processed_files) {
      data.processed_files.forEach(file => {
        processedFiles[file] = {
          operation: 'merged',
          timestamp: Date.now() / 1000,
          result: data.combined
        };
      });
    }
    
    await loadStagedFiles('einzel');
    
    const preview = document.getElementById('einzelPreview');
    preview.innerHTML = `<iframe src="/processed/${encodeURIComponent(data.combined)}#page=1&zoom=fit" scrolling="no"></iframe>`;
    
  } catch (err) {
    console.error('[einzel combine] Fehler:', err);
    alert('Fehler: ' + err);
  } finally {
    showSpinner(false);
  }
}

async function handleEinzelSplit() {
  const selected = Array.from(document.querySelectorAll('#einzelStagedFiles input[type="checkbox"]:checked:not(:disabled)'))
    .map(cb => cb.value);
  
  if (selected.length !== 1) {
    alert('Bitte genau eine PDF-Datei auswählen.');
    return;
  }
  
  const filename = selected[0];
  if (!filename.toLowerCase().endsWith('.pdf')) {
    alert('Nur PDF-Dateien können zerlegt werden.');
    return;
  }
  
  if (!confirm(`PDF "${filename}" in einzelne Seiten zerlegen?`)) {
    return;
  }
  
  showSpinner(true);
  try {
    const res = await fetch('/split_pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file: filename })
    });
    
    const data = await res.json();
    
    if (!res.ok || !data.success) {
      alert('Fehler beim Zerlegen: ' + (data.message || `HTTP ${res.status}`));
      return;
    }
    
    alert(`✅ PDF in ${data.count} Einzelseiten zerlegt!`);
    
    if (data.processed_file) {
      processedFiles[data.processed_file] = {
        operation: 'split',
        timestamp: Date.now() / 1000,
        result_count: data.count
      };
    }
    
    await loadStagedFiles('einzel');
    
  } catch (err) {
    console.error('[einzel split] Fehler:', err);
    alert('Fehler: ' + err);
  } finally {
    showSpinner(false);
  }
}

// ========================================
// BATCH-UPLOAD FUNKTIONEN
// ========================================

async function handleBatchCombine() {
  const selected = Array.from(document.querySelectorAll('#batchStagedFiles input[type="checkbox"]:checked:not(:disabled)'))
    .map(cb => cb.value);
  
  if (selected.length < 2) {
    alert('Bitte mindestens zwei Dateien auswählen.');
    return;
  }
  
  showSpinner(true);
  try {
    const res = await fetch('/combine_medidok', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: selected })
    });
    
    const data = await res.json();
    
    if (!res.ok || !data.success) {
      alert('Fehler beim Kombinieren: ' + (data.message || `HTTP ${res.status}`));
      return;
    }
    
    console.log(`✅ ${selected.length} Dateien kombiniert: ${data.combined}`);
    
    if (data.processed_files) {
      data.processed_files.forEach(file => {
        processedFiles[file] = {
          operation: 'merged',
          timestamp: Date.now() / 1000,
          result: data.combined
        };
      });
    }
    
    await loadStagedFiles('batch');
    
    const preview = document.getElementById('batchPreview');
    preview.innerHTML = `<iframe src="/processed/${encodeURIComponent(data.combined)}#page=1&zoom=fit" scrolling="no"></iframe>`;
    
  } catch (err) {
    console.error('[batch combine] Fehler:', err);
    alert('Fehler: ' + err);
  } finally {
    showSpinner(false);
  }
}

async function handleBatchSplit() {
  const selected = Array.from(document.querySelectorAll('#batchStagedFiles input[type="checkbox"]:checked:not(:disabled)'))
    .map(cb => cb.value);
  
  if (selected.length !== 1) {
    alert('Bitte genau eine PDF-Datei auswählen.');
    return;
  }
  
  const filename = selected[0];
  if (!filename.toLowerCase().endsWith('.pdf')) {
    alert('Nur PDF-Dateien können zerlegt werden.');
    return;
  }
  
  if (!confirm(`PDF "${filename}" in einzelne Seiten zerlegen?`)) {
    return;
  }
  
  showSpinner(true);
  try {
    const res = await fetch('/split_pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file: filename })
    });
    
    const data = await res.json();
    
    if (!res.ok || !data.success) {
      alert('Fehler beim Zerlegen: ' + (data.message || `HTTP ${res.status}`));
      return;
    }
    
    alert(`✅ PDF in ${data.count} Einzelseiten zerlegt!`);
    
    if (data.processed_file) {
      processedFiles[data.processed_file] = {
        operation: 'split',
        timestamp: Date.now() / 1000,
        result_count: data.count
      };
    }
    
    await loadStagedFiles('batch');
    
  } catch (err) {
    console.error('[batch split] Fehler:', err);
    alert('Fehler: ' + err);
  } finally {
    showSpinner(false);
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
  setupMasterCheckbox('batch');
  updateAllFileLists();
  await loadStagedFiles('medidok');
  updateMasterCheckbox('medidok');

  // Checkbox-Listener (Global für alle Tabs)
  document.addEventListener('change', (e) => {
    if (e.target.matches('input[type="checkbox"]')) {
      updateButtonStates(currentTab);
    }
  });

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
            currentTab = targetTab;
            
            const previewId = targetTab === 'medidok' ? 'preview' :
                            targetTab === 'einzel' ? 'einzelPreview' :
                            'batchPreview';
            const preview = document.getElementById(previewId);
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

  // ===== MEDIDOK TAB =====
  
  const medidokSubmit = document.getElementById("medidokSubmit");
  if (medidokSubmit) {
    medidokSubmit.addEventListener("click", handleMedidokAnalyze);
  }
  
  const mediCombine = document.getElementById("mediCombine");
  if (mediCombine) {
    mediCombine.addEventListener("click", handleMedidokCombine);
  }
  
  const mediSplit = document.getElementById("mediSplit");
  if (mediSplit) {
    mediSplit.addEventListener("click", handleMedidokSplit);
  }

  // ===== EINZEL TAB =====
  
  const fileInput = document.getElementById("fileInput");
  
  if (fileInput) {
    fileInput.addEventListener("change", async function () {
      const files = this.files;
      
      if (!files || files.length === 0) {
        return;
      }
      
      showSpinner(true);
      
      const formData = new FormData();
      for (let file of files) {
        formData.append('files', file);
      }
      
      try {
        const res = await fetch('/upload', {
          method: 'POST',
          body: formData
        });
        
        const data = await res.json();
        
        if (!res.ok || !data.success) {
          alert('Fehler beim Upload: ' + (data.message || `HTTP ${res.status}`));
          return;
        }
        
        await loadStagedFiles('einzel');
        
        const einzelAnalyze = document.getElementById('einzelAnalyze');
        if (einzelAnalyze) {
          einzelAnalyze.disabled = false;
        }
        
        console.log(`✅ ${files.length} Datei(en) hochgeladen und bereit zur Analyse`);
        
        setTimeout(() => {
          const firstLabel = document.querySelector("#einzelStagedFiles .file-label");
          if (firstLabel) firstLabel.click();
        }, 100);
        
      } catch (err) {
        console.error('[einzel upload] Fehler:', err);
        alert('Netzwerk-/JS-Fehler: ' + err);
      } finally {
        showSpinner(false);
      }
    });
  }
  
  const einzelAnalyze = document.getElementById("einzelAnalyze");
  if (einzelAnalyze) {
    einzelAnalyze.addEventListener("click", handleEinzelAnalyze);
  }
  
  const einzelCombine = document.getElementById("einzelCombine");
  if (einzelCombine) {
    einzelCombine.addEventListener("click", handleEinzelCombine);
  }
  
  const einzelSplit = document.getElementById("einzelSplit");
  if (einzelSplit) {
    einzelSplit.addEventListener("click", handleEinzelSplit);
  }

  // ===== BATCH TAB =====
  
  const folderInput = document.getElementById("folderInput");
  
  if (folderInput) {
    folderInput.addEventListener("change", async function() {
      const files = this.files;
      
      if (!files || files.length === 0) {
        return;
      }
      
      showSpinner(true);
      
      const formData = new FormData();
      for (let file of files) {
        formData.append('files', file);
      }
      
      try {
        const res = await fetch('/upload_folder', {
          method: 'POST',
          body: formData
        });
        
        const data = await res.json();
        
        if (!res.ok || !data.success) {
          alert('Fehler beim Upload: ' + (data.message || `HTTP ${res.status}`));
          return;
        }
        
        await loadStagedFiles('batch');
        
        const batchAnalyze = document.getElementById('batchAnalyze');
        if (batchAnalyze) {
          batchAnalyze.disabled = false;
        }
        
        console.log(`✅ ${files.length} Datei(en) hochgeladen und bereit zur Analyse`);
        
        setTimeout(() => {
          const firstLabel = document.querySelector("#batchStagedFiles .file-label");
          if (firstLabel) firstLabel.click();
        }, 100);
        
      } catch (err) {
        console.error('[batch upload] Fehler:', err);
        alert('Netzwerk-/JS-Fehler: ' + err);
      } finally {
        showSpinner(false);
      }
    });
  }
  
  const batchAnalyze = document.getElementById("batchAnalyze");
  if (batchAnalyze) {
    batchAnalyze.addEventListener("click", handleBatchAnalyze);
  }
  
  const batchCombine = document.getElementById("batchCombine");
  if (batchCombine) {
    batchCombine.addEventListener("click", handleBatchCombine);
  }
  
  const batchSplit = document.getElementById("batchSplit");
  if (batchSplit) {
    batchSplit.addEventListener("click", handleBatchSplit);
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
          alert("⚙️ Fehler beim Setzen des Modells: " + (data.message || "unbekannt"));
          return;
        }
        
        console.log('✅ Modell erfolgreich gewechselt:', selectedModel);
        
      } catch (err) {
        console.error('❌ Fehler beim Modellwechsel:', err);
        alert('Fehler beim Speichern der Modellauswahl');
      }
    });
  }
  
  console.log('✅ Initialisierung abgeschlossen');
});