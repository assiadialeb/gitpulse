/**
 * Toast notification system
 */

class ToastManager {
    constructor() {
        this.container = document.getElementById('toast-container');
        this.template = document.getElementById('toast-template');
    }

    show(message, type = 'info', duration = 5000) {
        if (!this.container || !this.template) {
            console.warn('Toast container or template not found');
            return;
        }

        // Clone the template
        const toast = this.template.content.cloneNode(true);
        const toastElement = toast.querySelector('.toast-item');
        const toastContent = toastElement.querySelector('div');
        const messageElement = toastElement.querySelector('.toast-message');
        const iconElement = toastElement.querySelector('.toast-icon');

        // Set message
        messageElement.textContent = message;

        // Set type-specific styling and icon
        this.setToastType(toastContent, iconElement, type);

        // Add to container
        this.container.appendChild(toastElement);

        // Animate in
        requestAnimationFrame(() => {
            toastElement.classList.remove('opacity-0', 'translate-x-full');
            toastElement.classList.add('opacity-100', 'translate-x-0');
        });

        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                this.hide(toastElement);
            }, duration);
        }

        return toastElement;
    }

    setToastType(contentElement, iconElement, type) {
        // Remove existing type classes
        contentElement.classList.remove('toast-success', 'toast-error', 'toast-warning', 'toast-info');
        iconElement.classList.remove('toast-icon-success', 'toast-icon-error', 'toast-icon-warning', 'toast-icon-info');

        // Add type-specific classes
        contentElement.classList.add(`toast-${type}`);
        iconElement.classList.add(`toast-icon-${type}`);

        // Set icon
        const iconPath = this.getIconPath(type);
        iconElement.innerHTML = iconPath;
    }

    getIconPath(type) {
        const icons = {
            success: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>',
            error: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>',
            warning: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.268 16.5c-.77.833.192 2.5 1.732 2.5z"></path>',
            info: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>'
        };
        return icons[type] || icons.info;
    }

    hide(toastElement) {
        if (!toastElement) return;

        // Animate out
        toastElement.classList.add('opacity-0', 'translate-x-full');
        toastElement.classList.remove('opacity-100', 'translate-x-0');

        // Remove after animation
        setTimeout(() => {
            if (toastElement.parentNode) {
                toastElement.parentNode.removeChild(toastElement);
            }
        }, 300);
    }

    success(message, duration) {
        return this.show(message, 'success', duration);
    }

    error(message, duration) {
        return this.show(message, 'error', duration);
    }

    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }

    info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// Global toast instance
window.toast = new ToastManager();

// Auto-show Django messages as toasts
document.addEventListener('DOMContentLoaded', function() {
    const messages = document.querySelectorAll('.alert');
    messages.forEach(message => {
        const messageText = message.querySelector('span')?.textContent || message.textContent;
        let type = 'info';
        
        if (message.classList.contains('alert-success')) type = 'success';
        else if (message.classList.contains('alert-error')) type = 'error';
        else if (message.classList.contains('alert-warning')) type = 'warning';
        
        // Show as toast
        window.toast.show(messageText, type, 6000);
        
        // Remove original message
        message.remove();
    });
});
