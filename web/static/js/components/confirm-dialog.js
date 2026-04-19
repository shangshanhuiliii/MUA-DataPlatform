class ConfirmDialog {
    constructor() {
        this.overlay = null;
        this.isInitialized = false;
        this.callback = null;
    }

    init() {
        if (this.isInitialized) return;
        
        this.overlay = document.getElementById('confirm-dialog-overlay');
        if (!this.overlay) {
            console.error('Confirm dialog overlay not found');
            return;
        }
        
        // Close dialog when clicking outside
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.close(false);
            }
        });
        
        // Close dialog on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen()) {
                this.close(false);
            }
        });
        
        this.isInitialized = true;
    }

    isOpen() {
        return this.overlay && this.overlay.style.display !== 'none';
    }

    show(message, callback) {
        this.init();
        if (!this.overlay) return;

        this.callback = callback;
        
        // Set content
        const contentDiv = document.getElementById('confirm-dialog-content');
        if (contentDiv) {
            contentDiv.innerHTML = message;
        }

        // Show dialog
        this.overlay.style.display = 'flex';
        
        // Focus on confirm button for keyboard navigation
        setTimeout(() => {
            const confirmBtn = document.getElementById('confirm-dialog-confirm');
            if (confirmBtn) {
                confirmBtn.focus();
            }
        }, 100);
    }

    close(result) {
        if (!this.overlay) return;
        
        this.overlay.style.display = 'none';
        
        if (this.callback) {
            this.callback(result);
            this.callback = null;
        }
    }
}

// Create global instance
window.confirmDialog = new ConfirmDialog();

// Ensure initialization when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (window.confirmDialog) {
        window.confirmDialog.init();
        console.log('ConfirmDialog initialized');
    }
});
