/**
 * Import Queue Monitor - Frontend-Modul
 *
 * Überwacht den Status der Import-Queue und zeigt ihn in der UI an.
 *
 * Verwendung:
 * 1. Dieses Skript in templates einbinden: <script src="/static/queue_monitor.js"></script>
 * 2. Status-Container hinzufügen: <div id="queue-status"></div>
 * 3. Monitor starten: QueueMonitor.start()
 */

const QueueMonitor = {
    // Konfiguration
    updateInterval: 3000,  // Update alle 3 Sekunden
    intervalId: null,
    statusContainer: null,

    /**
     * Startet die Queue-Überwachung
     * @param {string} containerId - ID des DOM-Elements für Status-Anzeige
     */
    start(containerId = 'queue-status') {
        this.statusContainer = document.getElementById(containerId);

        if (!this.statusContainer) {
            console.warn('Queue Monitor: Container nicht gefunden:', containerId);
            return;
        }

        // Initial-Update
        this.updateStatus();

        // Periodische Updates
        this.intervalId = setInterval(() => {
            this.updateStatus();
        }, this.updateInterval);

        console.log('✅ Queue Monitor gestartet');
    },

    /**
     * Stoppt die Queue-Überwachung
     */
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            console.log('🛑 Queue Monitor gestoppt');
        }
    },

    /**
     * Lädt aktuellen Queue-Status vom Server
     */
    async updateStatus() {
        try {
            const response = await fetch('/import_queue_status');

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.success && data.stats) {
                this.renderStatus(data.stats);
            } else {
                // Nur Fehler zeigen wenn Queue-Service wirklich nicht läuft
                // Bei leerem/initialem State zeige Status trotzdem an
                if (data.stats) {
                    this.renderStatus(data.stats);
                } else {
                    console.warn('Queue-Status ohne stats:', data);
                    this.renderError(data.message || 'Queue-Service startet...');
                }
            }
        } catch (error) {
            console.error('Fehler beim Laden des Queue-Status:', error);
            // Weniger aufdringliche Fehlerdarstellung
            this.renderError('Verbindung zum Queue-Service wird hergestellt...');
        }
    },

    /**
     * Rendert den Queue-Status in der UI
     * @param {Object} stats - Statistik-Objekt vom Server
     */
    renderStatus(stats) {
        // Fallback-Werte für fehlende Stats
        const {
            total_queued = 0,
            total_processed = 0,
            total_failed = 0,
            current_queue_size = 0,
            current_file = null,
            is_running = false
        } = stats || {};

        // Prozentuale Berechnung
        const processed_percent = total_queued > 0
            ? Math.round((total_processed / total_queued) * 100)
            : 0;

        // Status-Badge
        const statusBadge = is_running && current_file
            ? `<span class="badge badge-success">🔄 Aktiv</span>`
            : current_queue_size > 0
            ? `<span class="badge badge-warning">⏸️ Wartend</span>`
            : `<span class="badge badge-secondary">✅ Leerlauf</span>`;

        // HTML generieren
        const html = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0">📦 Import Queue Status</h5>
                    ${statusBadge}
                </div>
                <div class="card-body">
                    ${current_file ? `
                        <div class="alert alert-info mb-3">
                            <strong>Aktuelle Datei:</strong><br>
                            <code>${this.truncateFilename(current_file, 60)}</code>
                            <div class="spinner-border spinner-border-sm ml-2" role="status">
                                <span class="sr-only">Verarbeitung läuft...</span>
                            </div>
                        </div>
                    ` : ''}

                    <div class="row text-center">
                        <div class="col-md-3">
                            <div class="metric">
                                <h3 class="text-primary">${current_queue_size}</h3>
                                <small class="text-muted">In Warteschlange</small>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="metric">
                                <h3 class="text-success">${total_processed}</h3>
                                <small class="text-muted">Verarbeitet</small>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="metric">
                                <h3 class="text-danger">${total_failed}</h3>
                                <small class="text-muted">Fehler</small>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="metric">
                                <h3 class="text-info">${total_queued}</h3>
                                <small class="text-muted">Gesamt</small>
                            </div>
                        </div>
                    </div>

                    ${total_queued > 0 ? `
                        <div class="progress mt-3" style="height: 30px;">
                            <div class="progress-bar bg-success" role="progressbar"
                                 style="width: ${processed_percent}%"
                                 aria-valuenow="${processed_percent}"
                                 aria-valuemin="0"
                                 aria-valuemax="100">
                                ${processed_percent}% abgeschlossen
                            </div>
                        </div>
                    ` : ''}

                    <div class="mt-3 text-muted small">
                        <i class="fas fa-info-circle"></i>
                        Aktualisiert: ${new Date().toLocaleTimeString('de-DE')}
                    </div>
                </div>
            </div>
        `;

        this.statusContainer.innerHTML = html;
    },

    /**
     * Zeigt Fehlermeldung an
     * @param {string} message - Fehlermeldung
     */
    renderError(message) {
        const html = `
            <div class="alert alert-info">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div class="spinner-border" role="status">
                        <span class="sr-only">Laden...</span>
                    </div>
                    <div>
                        <strong>Warte auf Queue-Service...</strong><br>
                        <small>${message}</small>
                    </div>
                </div>
            </div>
        `;
        this.statusContainer.innerHTML = html;
    },

    /**
     * Kürzt lange Dateinamen
     * @param {string} filename - Dateiname
     * @param {number} maxLength - Maximale Länge
     * @returns {string} - Gekürzter Dateiname
     */
    truncateFilename(filename, maxLength) {
        if (filename.length <= maxLength) {
            return filename;
        }

        const ext = filename.split('.').pop();
        const nameWithoutExt = filename.substring(0, filename.lastIndexOf('.'));
        const maxNameLength = maxLength - ext.length - 4;  // 4 für "..." und "."

        return nameWithoutExt.substring(0, maxNameLength) + '...' + ext;
    }
};

// CSS für bessere Darstellung (optional - kann auch in style.css eingefügt werden)
const style = document.createElement('style');
style.textContent = `
    .metric {
        padding: 15px;
    }
    .metric h3 {
        margin: 0;
        font-weight: bold;
    }
    .metric small {
        display: block;
        margin-top: 5px;
    }
    #queue-status .card {
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    #queue-status .progress {
        border-radius: 15px;
    }
    #queue-status .progress-bar {
        font-weight: bold;
        line-height: 30px;
    }
`;
document.head.appendChild(style);

// Export für ES6-Module (optional)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = QueueMonitor;
}
