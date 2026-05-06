import { eventBus } from './event_bus.js';

export class TabManager {
    constructor(containerSelector) {
        this.container = document.querySelector(containerSelector);
        this.tabs = new Map();
        this.activeTabId = null;
        this.tabBar = null;
        this.tabContent = null;
        this._setupDOM();
    }

    _setupDOM() {
        this.tabBar = document.createElement('div');
        this.tabBar.className = 'tab-bar';
        this.tabContent = document.createElement('div');
        this.tabContent.className = 'tab-content';
        this.container.appendChild(this.tabBar);
        this.container.appendChild(this.tabContent);
    }

    createTab(sessionId, pipelineName) {
        const tabId = `tab-${sessionId}`;
        if (this.tabs.has(tabId)) {
            this.switchTab(tabId);
            return tabId;
        }

        const tabButton = document.createElement('div');
        tabButton.className = 'tab-button';
        tabButton.dataset.tabId = tabId;

        const label = document.createElement('span');
        label.className = 'tab-label';
        label.textContent = `${pipelineName} (${sessionId.substring(0, 8)}...)`;

        const closeBtn = document.createElement('span');
        closeBtn.className = 'tab-close';
        closeBtn.textContent = '×';
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.closeTab(tabId);
        });

        tabButton.appendChild(label);
        tabButton.appendChild(closeBtn);
        tabButton.addEventListener('click', () => this.switchTab(tabId));
        this.tabBar.appendChild(tabButton);

        const content = document.createElement('div');
        content.className = 'tab-pane';
        content.dataset.tabId = tabId;

        const dagContainer = document.createElement('div');
        dagContainer.className = 'dag-container';
        dagContainer.id = `dag-${sessionId}`;

        const stats = document.createElement('div');
        stats.className = 'tab-stats';
        stats.id = `stats-${sessionId}`;

        const nodeDetail = document.createElement('div');
        nodeDetail.className = 'node-detail-panel hidden';
        nodeDetail.id = `node-detail-${sessionId}`;

        content.appendChild(dagContainer);
        content.appendChild(stats);
        content.appendChild(nodeDetail);
        this.tabContent.appendChild(content);

        this.tabs.set(tabId, {
            tabId,
            sessionId,
            pipelineName,
            button: tabButton,
            content,
            dagContainer,
            stats,
            nodeDetail
        });

        this.switchTab(tabId);
        return tabId;
    }

    switchTab(tabId) {
        if (!this.tabs.has(tabId)) return;

        this.tabs.forEach((tab, id) => {
            const isActive = id === tabId;
            tab.button.classList.toggle('active', isActive);
            tab.content.classList.toggle('active', isActive);
        });

        this.activeTabId = tabId;
        const tab = this.tabs.get(tabId);
        eventBus.emit('tab:switched', { tabId, sessionId: tab.sessionId });
    }

    closeTab(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;

        tab.button.remove();
        tab.content.remove();
        this.tabs.delete(tabId);

        eventBus.emit('session:closed', { sessionId: tab.sessionId });

        if (this.activeTabId === tabId) {
            const remaining = Array.from(this.tabs.keys());
            if (remaining.length > 0) {
                this.switchTab(remaining[remaining.length - 1]);
            } else {
                this.activeTabId = null;
            }
        }
    }

    getActiveTab() {
        if (!this.activeTabId) return null;
        return this.tabs.get(this.activeTabId) || null;
    }

    getTabBySession(sessionId) {
        const tabId = `tab-${sessionId}`;
        return this.tabs.get(tabId) || null;
    }
}
