/**
 * Telegram WebApp Helper
 * Handles authentication, theme, and native features
 */

class TelegramHelper {
  constructor() {
    this.webApp = null;
    this.initData = null;
    this.user = null;
    this.isReady = false;
  }

  init() {
    // Check if running inside Telegram
    if (window.Telegram && window.Telegram.WebApp) {
      this.webApp = window.Telegram.WebApp;
      
      try {
        this.webApp.ready();
        this.webApp.expand();
        
        // Enable closing confirmation if needed
        // this.webApp.enableClosingConfirmation();

        this.initData = this.webApp.initData;
        this.user = this.webApp.initDataUnsafe?.user || null;

        // Set theme
        this.applyTheme();

        // Listen for theme changes
        this.webApp.onEvent('themeChanged', () => this.applyTheme());

        // Handle viewport changes
        this.webApp.onEvent('viewportChanged', (e) => {
          document.documentElement.style.setProperty('--tg-viewport-height', `${e.height}px`);
        });

        this.isReady = true;
        console.log('Telegram WebApp initialized', {
          initDataLength: this.initData?.length,
          user: this.user,
          version: this.webApp.version,
          platform: this.webApp.platform
        });

        return true;
      } catch (err) {
        console.error('Failed to init Telegram WebApp', err);
        return false;
      }
    } else {
      console.warn('Not running inside Telegram WebApp');
      // For development, allow fallback
      this.isReady = false;
      return false;
    }
  }

  applyTheme() {
    if (!this.webApp) return;

    const theme = this.webApp.themeParams || {};
    const root = document.documentElement;

    // Apply Telegram theme variables
    Object.entries(theme).forEach(([key, value]) => {
      if (value) {
        root.style.setProperty(`--tg-theme-${key.replace(/_/g, '-')}`, value);
      }
    });

    // Set color scheme
    if (this.webApp.colorScheme) {
      root.setAttribute('data-theme', this.webApp.colorScheme);
    }
  }

  getInitData() {
    return this.initData || '';
  }

  getUser() {
    return this.user;
  }

  isInsideTelegram() {
    return !!this.webApp;
  }

  // Haptic feedback
  haptic(type = 'light') {
    try {
      if (this.webApp?.HapticFeedback) {
        switch (type) {
          case 'light':
            this.webApp.HapticFeedback.impactOccurred('light');
            break;
          case 'medium':
            this.webApp.HapticFeedback.impactOccurred('medium');
            break;
          case 'heavy':
            this.webApp.HapticFeedback.impactOccurred('heavy');
            break;
          case 'success':
            this.webApp.HapticFeedback.notificationOccurred('success');
            break;
          case 'error':
            this.webApp.HapticFeedback.notificationOccurred('error');
            break;
          case 'warning':
            this.webApp.HapticFeedback.notificationOccurred('warning');
            break;
          case 'selection':
            this.webApp.HapticFeedback.selectionChanged();
            break;
        }
      }
    } catch (e) {
      // Haptics not supported
    }
  }

  // MainButton
  showMainButton(text, onClick) {
    if (!this.webApp?.MainButton) return;
    this.webApp.MainButton.setText(text);
    this.webApp.MainButton.onClick(onClick);
    this.webApp.MainButton.show();
  }

  hideMainButton() {
    if (!this.webApp?.MainButton) return;
    this.webApp.MainButton.hide();
  }

  // BackButton
  showBackButton(onClick) {
    if (!this.webApp?.BackButton) return;
    this.webApp.BackButton.onClick(onClick);
    this.webApp.BackButton.show();
  }

  hideBackButton() {
    if (!this.webApp?.BackButton) return;
    this.webApp.BackButton.hide();
  }

  // Alerts
  showAlert(message) {
    if (this.webApp?.showAlert) {
      this.webApp.showAlert(message);
    } else {
      alert(message);
    }
  }

  showConfirm(message) {
    return new Promise((resolve) => {
      if (this.webApp?.showConfirm) {
        this.webApp.showConfirm(message, (confirmed) => resolve(confirmed));
      } else {
        resolve(confirm(message));
      }
    });
  }

  // Open link
  openLink(url) {
    if (this.webApp?.openLink) {
      this.webApp.openLink(url);
    } else {
      window.open(url, '_blank');
    }
  }

  // Close app
  close() {
    if (this.webApp?.close) {
      this.webApp.close();
    }
  }

  // Get auth headers for API calls
  getAuthHeaders() {
    const initData = this.getInitData();
    if (initData) {
      return {
        'X-Telegram-Init-Data': initData,
        'Authorization': `tma ${initData}`
      };
    }
    return {};
  }
}

// Global instance
const tg = new TelegramHelper();
window.tg = tg;
