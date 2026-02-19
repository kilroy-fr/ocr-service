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
    onComplete: null,          // Callback wenn Queue vollständig verarbeitet
    hasSeenActivity: false,    // Verhindert Falsch-"fertig" bei leerem Start
    _idleSince: null,          // Zeitstempel wenn Queue zuletzt inaktiv wurde (Fallback-Timer)

    /**
     * Startet die Queue-Überwachung
     * @param {string} containerId - ID des DOM-Elements für Status-Anzeige
     * @param {Function} [onComplete] - Wird aufgerufen wenn alle Dateien verarbeitet sind, Parameter: total_processed
     */
    start(containerId = 'queue-status', onComplete = null) {
        // Vorhandenes Intervall auräumen (verhindert Doppel-Start)
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }

        this.statusContainer = document.getElementById(containerId);
        this.onComplete = onComplete;
        this.hasSeenActivity = false;
        this._idleSince = null;

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
        }
        this.onComplete = null;
        this.hasSeenActivity = false;
        this._idleSince = null;
        console.log('🛑 Queue Monitor gestoppt');
    },

    /**
     * Lädt aktuellen Queue-Status vom Server
     */
    async updateStatus() {
        console.log('🔄 Queue-Monitor: Fetching /import_queue_status...');
        try {
            const response = await fetch('/import_queue_status');

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            console.log('📊 Queue-Monitor: Received data:', data);

            if (data.success && data.stats) {
                this.renderStatus(data.stats);
                this._checkCompletion(data.stats);
            } else if (data.stats) {
                this.renderStatus(data.stats);
                this._checkCompletion(data.stats);
            } else {
                console.warn('⚠️ Queue-Status ohne stats:', data);
                this.renderError(data.message || 'Queue-Service startet...');
            }
        } catch (error) {
            console.error('❌ Fehler beim Laden des Queue-Status:', error);
            this.renderError('Verbindung zum Queue-Service wird hergestellt...');
        }
    },

    /**
     * Prüft ob Queue vollständig verarbeitet ist und ruft onComplete auf
     */
    _checkCompletion(stats) {
        const { current_queue_size, total_processed, total_queued, current_file } = stats;

        if (total_queued > 0 || current_queue_size > 0) {
            this.hasSeenActivity = true;
        }

        if (!this.onComplete || !this.hasSeenActivity) return;

        // Queue ist inaktiv: kein Item wartend, keine Datei in Bearbeitung
        const isIdle = (current_queue_size === 0 && !current_file);

        if (isIdle) {
            if (!this._idleSince) this._idleSince = Date.now();
        } else {
            this._idleSince = null;  // Aktivität → Timer zurücksetzen
        }

        // Primäre Prüfung: Queue leer, keine aktive Datei, Zähler stimmen überein
        if (isIdle && total_processed > 0 && total_processed === total_queued) {
            console.log('✅ Queue-Monitor: Completion erkannt (primär)');
            this._triggerComplete(total_processed);
            return;
        }

        // Schneller Fallback: Queue seit > 5s inaktiv, mindestens eine Datei verarbeitet
        // Fängt Edge-Cases ab wo total_processed ≠ total_queued (z.B. Fehler oder Singleton-Akkumulation)
        if (isIdle && total_processed > 0 && this._idleSince && (Date.now() - this._idleSince) > 5000) {
            console.warn('⚠️ Queue-Monitor: Fallback-Completion nach 5s Inaktivität (processed=' + total_processed + ', queued=' + total_queued + ')');
            this._triggerComplete(total_processed);
        }
    },

    /**
     * Feuert den onComplete-Callback und stoppt den Monitor
     */
    _triggerComplete(processedCount) {
        const callback = this.onComplete;
        this.stop();
        callback(processedCount);
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
        const statusIcon = is_running && current_file
            ? `🔄 Aktiv`
            : current_queue_size > 0
            ? `⏸️ Wartend`
            : `✅ Abgeschlossen`;

        // HTML generieren ohne Bootstrap
        const html = `
            <div style="background: var(--bg-secondary, #2a2a2a); border-radius: 8px; padding: 20px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h3 style="margin: 0; color: var(--text-primary, #fff);">📦 Import Queue Status</h3>
                    <span style="padding: 5px 15px; background: var(--accent-color, #4a9eff); border-radius: 4px; font-weight: bold;">
                        ${statusIcon}
                    </span>
                </div>

                ${current_file ? `
                    <div style="background: rgba(74, 158, 255, 0.2); border-left: 4px solid #4a9eff; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
                        <strong>Aktuelle Datei:</strong><br>
                        <code style="color: #4a9eff; word-break: break-all;">${this.truncateFilename(current_file, 60)}</code>
                        <span style="display: inline-block; margin-left: 10px;">⏳</span>
                    </div>
                ` : ''}

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 20px; margin-bottom: 20px; text-align: center;">
                    <div class="queue-metric">
                        <div class="queue-metric-value" style="font-size: 2.5em; font-weight: bold; color: #ffa500;">${current_queue_size}</div>
                        <div class="queue-metric-label" style="color: #999; font-size: 0.9em; margin-top: 5px;">In Warteschlange</div>
                    </div>
                    <div class="queue-metric">
                        <div class="queue-metric-value" style="font-size: 2.5em; font-weight: bold; color: #4caf50;">${total_processed}</div>
                        <div class="queue-metric-label" style="color: #999; font-size: 0.9em; margin-top: 5px;">Verarbeitet</div>
                    </div>
                    <div class="queue-metric">
                        <div class="queue-metric-value" style="font-size: 2.5em; font-weight: bold; color: #f44336;">${total_failed}</div>
                        <div class="queue-metric-label" style="color: #999; font-size: 0.9em; margin-top: 5px;">Fehler</div>
                    </div>
                    <div class="queue-metric">
                        <div class="queue-metric-value" style="font-size: 2.5em; font-weight: bold; color: #4a9eff;">${total_queued}</div>
                        <div class="queue-metric-label" style="color: #999; font-size: 0.9em; margin-top: 5px;">Gesamt</div>
                    </div>
                </div>

                ${total_queued > 0 ? `
                    <div style="background: #1a1a1a; border-radius: 15px; height: 30px; overflow: hidden; margin-bottom: 15px;">
                        <div style="background: linear-gradient(90deg, #4caf50, #8bc34a); height: 100%; width: ${processed_percent}%;
                                    display: flex; align-items: center; justify-content: center; font-weight: bold;
                                    transition: width 0.3s ease; color: #fff;">
                            ${processed_percent}% abgeschlossen
                        </div>
                    </div>
                ` : ''}

                <div style="text-align: center; color: #999; font-size: 0.85em; margin-top: 15px;">
                    ⏰ Aktualisiert: ${new Date().toLocaleTimeString('de-DE')}
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
            <div style="background: rgba(74, 158, 255, 0.2); border-left: 4px solid #4a9eff; padding: 20px; border-radius: 4px;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 2em;">⏳</div>
                    <div>
                        <strong style="color: #4a9eff;">Warte auf Queue-Service...</strong><br>
                        <small style="color: #999;">${message}</small>
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

// Minimales CSS für Queue-Metriken (nur einmal hinzufügen)
if (!document.getElementById('queue-monitor-styles')) {
    const style = document.createElement('style');
    style.id = 'queue-monitor-styles';
    style.textContent = `
        .queue-metric {
            padding: 15px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            transition: transform 0.2s;
        }
        .queue-metric:hover {
            transform: translateY(-2px);
            background: rgba(255, 255, 255, 0.08);
        }
    `;
    document.head.appendChild(style);
}

// Export für ES6-Module (optional)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = QueueMonitor;
}
