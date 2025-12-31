/**
 * Modern Notification System
 * Ersetzt alert() und confirm() durch elegante Toast-Benachrichtigungen und Modals
 */

const Notifications = {
    /**
     * Zeigt eine Toast-Benachrichtigung an
     * @param {string} message - Die anzuzeigende Nachricht
     * @param {string} type - Typ: 'success', 'error', 'warning', 'info'
     * @param {number} duration - Anzeigedauer in ms (0 = dauerhaft)
     */
    toast(message, type = 'info', duration = 4000) {
        const container = this.getOrCreateContainer();

        const toast = document.createElement('div');
        toast.className = `notification-toast notification-${type}`;

        const icon = this.getIcon(type);

        toast.innerHTML = `
            <div class="notification-icon">${icon}</div>
            <div class="notification-content">${message}</div>
            <button class="notification-close" onclick="this.parentElement.remove()">&times;</button>
        `;

        container.appendChild(toast);

        // Animation
        setTimeout(() => toast.classList.add('notification-show'), 10);

        // Auto-remove nach duration
        if (duration > 0) {
            setTimeout(() => {
                toast.classList.remove('notification-show');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }

        return toast;
    },

    /**
     * Zeigt einen Confirm-Dialog als Modal
     * @param {string} message - Die Frage/Nachricht
     * @param {string} confirmText - Text für Bestätigen-Button
     * @param {string} cancelText - Text für Abbrechen-Button
     * @returns {Promise<boolean>} - true bei Bestätigung, false bei Abbruch
     */
    async confirm(message, confirmText = 'OK', cancelText = 'Abbrechen') {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'notification-modal-overlay';

            const modal = document.createElement('div');
            modal.className = 'notification-modal';

            modal.innerHTML = `
                <div class="notification-modal-content">
                    <div class="notification-modal-icon">⚠️</div>
                    <div class="notification-modal-message">${message.replace(/\n/g, '<br>')}</div>
                    <div class="notification-modal-buttons">
                        <button class="notification-btn notification-btn-cancel" data-action="cancel">${cancelText}</button>
                        <button class="notification-btn notification-btn-confirm" data-action="confirm">${confirmText}</button>
                    </div>
                </div>
            `;

            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            // Animation
            setTimeout(() => {
                overlay.classList.add('notification-modal-show');
                modal.classList.add('notification-modal-show');
            }, 10);

            const handleClick = (e) => {
                const action = e.target.dataset.action;
                if (action) {
                    overlay.classList.remove('notification-modal-show');
                    modal.classList.remove('notification-modal-show');

                    setTimeout(() => {
                        overlay.remove();
                        resolve(action === 'confirm');
                    }, 200);
                }
            };

            modal.addEventListener('click', handleClick);

            // ESC zum Abbrechen
            const handleEsc = (e) => {
                if (e.key === 'Escape') {
                    overlay.classList.remove('notification-modal-show');
                    modal.classList.remove('notification-modal-show');
                    setTimeout(() => {
                        overlay.remove();
                        resolve(false);
                    }, 200);
                    document.removeEventListener('keydown', handleEsc);
                }
            };
            document.addEventListener('keydown', handleEsc);
        });
    },

    /**
     * Zeigt eine Info-Nachricht (wie alert)
     * @param {string} message - Die Nachricht
     */
    async alert(message) {
        return this.confirm(message, 'OK', '');
    },

    /**
     * Container für Toasts erstellen/holen
     */
    getOrCreateContainer() {
        let container = document.getElementById('notification-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notification-container';
            container.className = 'notification-container';
            document.body.appendChild(container);
        }
        return container;
    },

    /**
     * Icon für Toast-Type
     */
    getIcon(type) {
        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };
        return icons[type] || icons.info;
    },

    // Convenience methods
    success(message, duration = 4000) {
        return this.toast(message, 'success', duration);
    },

    error(message, duration = 6000) {
        return this.toast(message, 'error', duration);
    },

    warning(message, duration = 5000) {
        return this.toast(message, 'warning', duration);
    },

    info(message, duration = 4000) {
        return this.toast(message, 'info', duration);
    }
};

// CSS-Styles einfügen
const style = document.createElement('style');
style.textContent = `
    /* Toast Container */
    .notification-container {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 100000;
        display: flex;
        flex-direction: column;
        gap: 10px;
        max-width: 400px;
    }

    /* Toast */
    .notification-toast {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 16px 20px;
        background: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        transform: translateX(120%);
        transition: transform 0.3s ease, opacity 0.3s ease;
        opacity: 0;
        border-left: 4px solid #007BFF;
    }

    .notification-toast.notification-show {
        transform: translateX(0);
        opacity: 1;
    }

    .notification-toast.notification-success {
        border-left-color: #28a745;
    }

    .notification-toast.notification-error {
        border-left-color: #dc3545;
    }

    .notification-toast.notification-warning {
        border-left-color: #ffc107;
    }

    .notification-toast.notification-info {
        border-left-color: #007BFF;
    }

    .notification-icon {
        font-size: 24px;
        flex-shrink: 0;
    }

    .notification-content {
        flex: 1;
        color: #333;
        font-size: 14px;
        line-height: 1.4;
    }

    .notification-close {
        background: none;
        border: none;
        font-size: 24px;
        color: #999;
        cursor: pointer;
        padding: 0;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: color 0.2s;
        flex-shrink: 0;
    }

    .notification-close:hover {
        color: #333;
    }

    /* Modal Overlay */
    .notification-modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        z-index: 100001;
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0;
        transition: opacity 0.2s ease;
    }

    .notification-modal-overlay.notification-modal-show {
        opacity: 1;
    }

    /* Modal */
    .notification-modal {
        background: white;
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        max-width: 500px;
        width: 90%;
        transform: scale(0.9);
        opacity: 0;
        transition: transform 0.2s ease, opacity 0.2s ease;
    }

    .notification-modal.notification-modal-show {
        transform: scale(1);
        opacity: 1;
    }

    .notification-modal-content {
        padding: 30px;
        text-align: center;
    }

    .notification-modal-icon {
        font-size: 48px;
        margin-bottom: 20px;
    }

    .notification-modal-message {
        color: #333;
        font-size: 16px;
        line-height: 1.6;
        margin-bottom: 30px;
        white-space: pre-line;
    }

    .notification-modal-buttons {
        display: flex;
        gap: 10px;
        justify-content: center;
    }

    .notification-btn {
        padding: 12px 24px;
        border: none;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        min-width: 100px;
    }

    .notification-btn-cancel {
        background: #e9ecef;
        color: #495057;
    }

    .notification-btn-cancel:hover {
        background: #d3d6d8;
    }

    .notification-btn-confirm {
        background: #007BFF;
        color: white;
    }

    .notification-btn-confirm:hover {
        background: #0056b3;
    }

    /* Dark theme support */
    @media (prefers-color-scheme: dark) {
        .notification-toast {
            background: #2d2d2d;
        }

        .notification-content {
            color: #e0e0e0;
        }

        .notification-close {
            color: #aaa;
        }

        .notification-close:hover {
            color: #fff;
        }

        .notification-modal {
            background: #2d2d2d;
        }

        .notification-modal-message {
            color: #e0e0e0;
        }

        .notification-btn-cancel {
            background: #3d3d3d;
            color: #e0e0e0;
        }

        .notification-btn-cancel:hover {
            background: #4d4d4d;
        }
    }

    /* Mobile Responsive */
    @media (max-width: 768px) {
        .notification-container {
            top: 10px;
            right: 10px;
            left: 10px;
            max-width: none;
        }

        .notification-toast {
            padding: 14px 16px;
        }

        .notification-modal-content {
            padding: 20px;
        }

        .notification-modal-buttons {
            flex-direction: column;
        }

        .notification-btn {
            width: 100%;
        }
    }
`;
document.head.appendChild(style);

// Export für globale Nutzung
window.Notifications = Notifications;
