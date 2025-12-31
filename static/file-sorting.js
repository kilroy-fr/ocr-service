// ========================================
// DATEI-SORTIERUNG: DRAG & DROP + PFEILE
// ========================================

/**
 * Initialisiert die Sortier-Funktionalität für eine Dateiliste
 * @param {string} containerId - Die ID des Containers (z.B. 'fileList', 'einzelStagedFiles', 'batchStagedFiles')
 */
function initFileSorting(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Observer für dynamisch hinzugefügte Elemente
  const observer = new MutationObserver(() => {
    setupSortingForItems(container);
  });

  observer.observe(container, {
    childList: true,
    subtree: true
  });

  // Initiale Einrichtung
  setupSortingForItems(container);
}

/**
 * Richtet Drag & Drop und Pfeile für alle file-items ein
 */
function setupSortingForItems(container) {
  const items = container.querySelectorAll('.file-item:not(.processed)');

  items.forEach((item, index) => {
    // Drag & Drop nur einmal einrichten
    if (!item.hasAttribute('data-sort-enabled')) {
      setupDragAndDrop(item);
      item.setAttribute('data-sort-enabled', 'true');
    }

    // Pfeile hinzufügen/aktualisieren
    updateSortArrows(item, index, items.length);
  });
}

/**
 * Richtet Drag & Drop für ein Item ein
 */
function setupDragAndDrop(item) {
  item.setAttribute('draggable', 'true');

  item.addEventListener('dragstart', handleDragStart);
  item.addEventListener('dragover', handleDragOver);
  item.addEventListener('drop', handleDrop);
  item.addEventListener('dragenter', handleDragEnter);
  item.addEventListener('dragleave', handleDragLeave);
  item.addEventListener('dragend', handleDragEnd);
}

let draggedItem = null;

function handleDragStart(e) {
  if (this.classList.contains('processed')) {
    e.preventDefault();
    return;
  }

  draggedItem = this;
  this.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/html', this.innerHTML);
}

function handleDragOver(e) {
  if (e.preventDefault) {
    e.preventDefault();
  }
  e.dataTransfer.dropEffect = 'move';
  return false;
}

function handleDragEnter(e) {
  if (this.classList.contains('processed') || this === draggedItem) {
    return;
  }
  this.classList.add('drag-over');
}

function handleDragLeave(e) {
  this.classList.remove('drag-over');
}

function handleDrop(e) {
  if (e.stopPropagation) {
    e.stopPropagation();
  }

  if (this.classList.contains('processed') || this === draggedItem) {
    return false;
  }

  // Element verschieben
  const container = draggedItem.parentNode;
  const allItems = Array.from(container.querySelectorAll('.file-item'));
  const draggedIndex = allItems.indexOf(draggedItem);
  const targetIndex = allItems.indexOf(this);

  if (draggedIndex < targetIndex) {
    this.parentNode.insertBefore(draggedItem, this.nextSibling);
  } else {
    this.parentNode.insertBefore(draggedItem, this);
  }

  // Pfeile für alle Items aktualisieren
  setupSortingForItems(container);

  return false;
}

function handleDragEnd(e) {
  this.classList.remove('dragging');

  // Alle drag-over Klassen entfernen
  const items = this.parentNode.querySelectorAll('.file-item');
  items.forEach(item => {
    item.classList.remove('drag-over');
  });
}

/**
 * Fügt Sortier-Pfeile zu einem Item hinzu oder aktualisiert sie
 */
function updateSortArrows(item, index, totalCount) {
  // Vorhandene Pfeile entfernen
  const existingArrows = item.querySelector('.sort-arrows');
  if (existingArrows) {
    existingArrows.remove();
  }

  // Pfeile erstellen
  const arrowsDiv = document.createElement('div');
  arrowsDiv.className = 'sort-arrows';

  // Aufwärts-Pfeil
  const upBtn = document.createElement('button');
  upBtn.className = 'sort-arrow sort-arrow-up';
  upBtn.innerHTML = '▲';
  upBtn.title = 'Nach oben';
  upBtn.type = 'button';
  upBtn.disabled = index === 0;
  upBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    moveItem(item, -1);
  });

  // Abwärts-Pfeil
  const downBtn = document.createElement('button');
  downBtn.className = 'sort-arrow sort-arrow-down';
  downBtn.innerHTML = '▼';
  downBtn.title = 'Nach unten';
  downBtn.type = 'button';
  downBtn.disabled = index === totalCount - 1;
  downBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    moveItem(item, 1);
  });

  arrowsDiv.appendChild(upBtn);
  arrowsDiv.appendChild(downBtn);
  item.appendChild(arrowsDiv);
}

/**
 * Verschiebt ein Item nach oben oder unten
 * @param {HTMLElement} item - Das zu verschiebende Element
 * @param {number} direction - -1 für nach oben, 1 für nach unten
 */
function moveItem(item, direction) {
  const container = item.parentNode;
  const items = Array.from(container.querySelectorAll('.file-item:not(.processed)'));
  const currentIndex = items.indexOf(item);

  if (currentIndex === -1) return;

  const newIndex = currentIndex + direction;

  if (newIndex < 0 || newIndex >= items.length) return;

  // Element im DOM verschieben
  if (direction === -1) {
    // Nach oben
    const previousItem = items[newIndex];
    container.insertBefore(item, previousItem);
  } else {
    // Nach unten
    const nextItem = items[newIndex];
    container.insertBefore(item, nextItem.nextSibling);
  }

  // Pfeile für alle Items aktualisieren
  setupSortingForItems(container);
}

/**
 * Gibt die aktuelle Reihenfolge der Dateien zurück
 * @param {string} containerId - Die ID des Containers
 * @returns {Array<string>} - Array mit Dateinamen in der aktuellen Reihenfolge
 */
function getFileSortOrder(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return [];

  const items = container.querySelectorAll('.file-item');
  const fileNames = [];

  items.forEach(item => {
    const checkbox = item.querySelector('input[type="checkbox"]');
    if (checkbox && checkbox.checked && !checkbox.disabled) {
      fileNames.push(checkbox.value);
    }
  });

  return fileNames;
}

// ========================================
// EXPORT
// ========================================
window.FileSorting = {
  init: initFileSorting,
  getOrder: getFileSortOrder
};
