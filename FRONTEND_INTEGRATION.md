# Frontend-Integration für Queue Monitor

## Quick Start

### 1. JavaScript einbinden

Fügen Sie in Ihrem Template (z.B. `templates/control.html` oder `templates/index.html`) folgendes hinzu:

```html
<!-- Queue Monitor JavaScript -->
<script src="{{ url_for('static', filename='queue_monitor.js') }}"></script>
```

### 2. Status-Container hinzufügen

Fügen Sie an gewünschter Stelle einen Container für die Status-Anzeige ein:

```html
<!-- Import Queue Status -->
<div class="container mt-4">
    <div id="queue-status"></div>
</div>
```

### 3. Monitor starten

Starten Sie den Monitor nach dem Laden der Seite:

```html
<script>
    // Queue Monitor nach dem Laden starten
    document.addEventListener('DOMContentLoaded', function() {
        QueueMonitor.start('queue-status');
    });
</script>
```

## Vollständiges Beispiel

### Option A: In bestehendes Control-Panel integrieren

**In `templates/control.html`:**

```html
{% extends "base.html" %}

{% block content %}
<div class="container">
    <!-- Bestehender Content -->
    <h1>Control Panel</h1>

    <!-- Hier kommt Ihr Control-Code -->

    <!-- NEU: Import Queue Status -->
    <div class="mt-5">
        <div id="queue-status"></div>
    </div>
</div>

<!-- Queue Monitor einbinden -->
<script src="{{ url_for('static', filename='queue_monitor.js') }}"></script>
<script>
    document.addEventListener('DOMContentLoaded', function() {
        // Monitor starten
        QueueMonitor.start('queue-status');

        // Optional: Nach Finalisierung Monitor anzeigen
        document.getElementById('finalize-button').addEventListener('click', function() {
            // Ihr bestehender Finalize-Code

            // Monitor einblenden nach erfolgreichem Import
            document.getElementById('queue-status').scrollIntoView({
                behavior: 'smooth'
            });
        });
    });
</script>
{% endblock %}
```

### Option B: Separaten Modal-Dialog verwenden

```html
<!-- Modal für Queue Status -->
<div class="modal fade" id="queueStatusModal" tabindex="-1" role="dialog">
    <div class="modal-dialog modal-lg" role="document">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Import-Fortschritt</h5>
                <button type="button" class="close" data-dismiss="modal">
                    <span>&times;</span>
                </button>
            </div>
            <div class="modal-body">
                <div id="queue-status-modal"></div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-dismiss="modal">
                    Schließen
                </button>
            </div>
        </div>
    </div>
</div>

<!-- JavaScript -->
<script src="{{ url_for('static', filename='queue_monitor.js') }}"></script>
<script>
    // Monitor starten wenn Modal geöffnet wird
    $('#queueStatusModal').on('show.bs.modal', function() {
        QueueMonitor.start('queue-status-modal');
    });

    // Monitor stoppen wenn Modal geschlossen wird
    $('#queueStatusModal').on('hidden.bs.modal', function() {
        QueueMonitor.stop();
    });

    // Modal nach Finalisierung öffnen
    document.getElementById('finalize-button').addEventListener('click', function() {
        // Ihr bestehender Finalize-Code

        // Modal öffnen um Fortschritt zu zeigen
        $('#queueStatusModal').modal('show');
    });
</script>
```

### Option C: Inline nach Finalisierung einblenden

```html
<button id="finalize-button" class="btn btn-primary">
    Finalisieren
</button>

<!-- Status wird hier eingeblendet -->
<div id="queue-status-container" style="display: none;" class="mt-4">
    <div id="queue-status"></div>
    <button class="btn btn-secondary mt-3" onclick="QueueMonitor.stop(); this.parentElement.style.display='none';">
        Monitoring beenden
    </button>
</div>

<script src="{{ url_for('static', filename='queue_monitor.js') }}"></script>
<script>
    document.getElementById('finalize-button').addEventListener('click', async function() {
        // Bestehender Finalize-Code...
        const response = await fetch('/finalize_import', {
            method: 'POST',
            // ... Ihre Parameter
        });

        const result = await response.json();

        if (result.success) {
            // Status-Container einblenden
            document.getElementById('queue-status-container').style.display = 'block';

            // Monitor starten
            QueueMonitor.start('queue-status');

            // Alert anzeigen
            alert(result.message);
        }
    });
</script>
```

## Konfiguration

### Update-Intervall ändern

Standardmäßig wird alle 3 Sekunden aktualisiert. Um das zu ändern:

```javascript
// Vor dem Start konfigurieren
QueueMonitor.updateInterval = 5000;  // 5 Sekunden
QueueMonitor.start('queue-status');
```

### Custom Styling

Sie können das Aussehen mit CSS anpassen:

```css
/* In Ihrer style.css */
#queue-status .card {
    border: 2px solid #007bff;
    border-radius: 10px;
}

#queue-status .metric h3 {
    font-size: 2.5rem;
    color: #28a745;
}

#queue-status .progress {
    height: 40px;
    font-size: 1.1rem;
}
```

## Erweiterte Verwendung

### Callback bei Abschluss

```javascript
// Custom Update-Logik
const originalUpdate = QueueMonitor.updateStatus;
QueueMonitor.updateStatus = async function() {
    await originalUpdate.call(this);

    // Custom-Logik nach Update
    const response = await fetch('/import_queue_status');
    const data = await response.json();

    if (data.success && data.stats.current_queue_size === 0 && data.stats.total_processed > 0) {
        // Alle Dateien verarbeitet!
        alert('✅ Alle Dateien wurden erfolgreich importiert!');
        QueueMonitor.stop();
    }
};
```

### Notification bei Fehlern

```javascript
// Überwache Fehler
let lastFailedCount = 0;

const originalRender = QueueMonitor.renderStatus;
QueueMonitor.renderStatus = function(stats) {
    originalRender.call(this, stats);

    // Prüfe auf neue Fehler
    if (stats.total_failed > lastFailedCount) {
        alert(`⚠️ ${stats.total_failed - lastFailedCount} neue Fehler beim Import!`);
    }
    lastFailedCount = stats.total_failed;
};
```

## Bootstrap-Anforderungen

Der Queue Monitor verwendet Bootstrap-Klassen. Stellen Sie sicher, dass Bootstrap eingebunden ist:

```html
<!-- Bootstrap CSS -->
<link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">

<!-- Optional: Font Awesome für Icons -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
```

## Troubleshooting

### Monitor startet nicht

**Problem:** Nichts wird angezeigt

**Lösung:**
1. Überprüfen Sie die Browser-Konsole auf Fehler
2. Stellen Sie sicher, dass der Container existiert: `document.getElementById('queue-status')`
3. Prüfen Sie, ob der Endpoint erreichbar ist: `curl http://localhost:5000/import_queue_status`

### Updates funktionieren nicht

**Problem:** Status wird nicht aktualisiert

**Lösung:**
1. Überprüfen Sie die Browser-Konsole auf Network-Fehler
2. Stellen Sie sicher, dass der Backend-Service läuft
3. Prüfen Sie CORS-Einstellungen falls Frontend und Backend auf verschiedenen Domains laufen

### Styling passt nicht

**Problem:** Darstellung ist fehlerhaft

**Lösung:**
1. Stellen Sie sicher, dass Bootstrap korrekt eingebunden ist
2. Überprüfen Sie CSS-Konflikte in Ihrer bestehenden style.css
3. Nutzen Sie Browser-DevTools um CSS-Probleme zu debuggen

## Minimal-Beispiel (Copy & Paste)

```html
<!DOCTYPE html>
<html>
<head>
    <title>Queue Monitor Test</title>
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
</head>
<body>
    <div class="container mt-5">
        <h1>Import Queue Monitor</h1>
        <div id="queue-status"></div>
    </div>

    <script src="/static/queue_monitor.js"></script>
    <script>
        QueueMonitor.start('queue-status');
    </script>
</body>
</html>
```

Speichern Sie dies als Test-Template und rufen Sie es auf um den Monitor zu testen!
