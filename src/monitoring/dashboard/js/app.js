import { APIClient } from './api_client.js';
import { WSClient } from './ws_client.js';
import { DAGRenderer } from './dag_renderer.js';
import { TimelineView } from './timeline_view.js';
import { NodeDetailPanel } from './node_detail.js';
import { EditorApp } from './editor_app.js';
import { eventBus } from './event_bus.js';

export class DashboardApp {
    constructor() {
        this.apiClient = new APIClient('');
        this.wsClient = null;
        this.dagRenderer = null;
        this.timelineView = null;
        this.nodeDetailPanel = null;
        this.editorApp = null;

        this.currentMode = 'monitor';
        this.currentSessionId = null;
        this.currentState = null;
        this.eventSource = null;
        this.refreshInterval = null;

        this.sessionSelect = document.getElementById('session-select');
        this.connectionStatus = document.getElementById('connection-status');
        this.lastUpdate = document.getElementById('last-update');
        this.closeNodeDetailBtn = document.getElementById('close-node-detail');

        this.statElements = {
            status: document.getElementById('stat-status'),
            iteration: document.getElementById('stat-iteration'),
            backtrack: document.getElementById('stat-backtrack'),
            completed: document.getElementById('stat-completed'),
            failed: document.getElementById('stat-failed'),
            duration: document.getElementById('stat-duration')
        };
    }

    async init() {
        this.dagRenderer = new DAGRenderer('#dag-container');
        this.timelineView = new TimelineView('#timeline-container');
        this.nodeDetailPanel = new NodeDetailPanel('#node-detail');

        this._setupControls();
        this._setupModeTabs();

        await this._loadSessions();

        this.setupEventListeners();

        this.editorApp = new EditorApp();
        this.editorApp.init();

        this._setupEditorEventBus();
    }

    _setupModeTabs() {
        const tabMonitor = document.getElementById('tab-monitor');
        const tabEditor = document.getElementById('tab-editor');

        tabMonitor.addEventListener('click', () => this._switchMode('monitor'));
        tabEditor.addEventListener('click', () => this._switchMode('editor'));
    }

    _switchMode(mode) {
        this.currentMode = mode;

        const tabMonitor = document.getElementById('tab-monitor');
        const tabEditor = document.getElementById('tab-editor');
        const monitorView = document.getElementById('monitor-view');
        const editorView = document.getElementById('editor-view');
        const monitorHeader = document.getElementById('monitor-header-center');
        const editorHeader = document.getElementById('editor-header-center');

        tabMonitor.classList.toggle('active', mode === 'monitor');
        tabEditor.classList.toggle('active', mode === 'editor');

        if (mode === 'monitor') {
            monitorView.style.display = '';
            editorView.style.display = 'none';
            monitorHeader.style.display = '';
            editorHeader.style.display = 'none';
        } else {
            monitorView.style.display = 'none';
            editorView.style.display = 'grid';
            monitorHeader.style.display = 'none';
            editorHeader.style.display = '';
            eventBus.emit('mode:editor-activated');
        }
    }

    _setupEditorEventBus() {
        eventBus.on('pipeline:run-started', ({ sessionId, pipelineName }) => {
            this._switchMode('monitor');
            this._loadSessions().then(() => {
                this.sessionSelect.value = sessionId;
                this.loadSession(sessionId);
            });
        });
    }

    _setupControls() {
        const zoomInBtn = document.getElementById('zoom-in');
        const zoomOutBtn = document.getElementById('zoom-out');
        const zoomFitBtn = document.getElementById('zoom-fit');

        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', () => this.dagRenderer.zoomIn());
        }
        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => this.dagRenderer.zoomOut());
        }
        if (zoomFitBtn) {
            zoomFitBtn.addEventListener('click', () => this.dagRenderer.zoomToFit());
        }
    }

    async _loadSessions() {
        try {
            const statuses = await this.apiClient.getDagStatuses();

            this.sessionSelect.innerHTML = '<option value="">-- Select Session --</option>';

            statuses.forEach(status => {
                const option = document.createElement('option');
                option.value = status.session_id;
                option.textContent = `${status.pipeline_name} (${status.session_id.substring(0, 8)}...)`;
                this.sessionSelect.appendChild(option);
            });

            if (statuses.length === 1) {
                this.sessionSelect.value = statuses[0].session_id;
                await this.loadSession(statuses[0].session_id);
            }
        } catch (error) {
            console.error('Failed to load sessions:', error);
        }
    }

    async loadSession(sessionId) {
        if (!sessionId) {
            return;
        }

        this._disconnect();

        this.currentSessionId = sessionId;

        try {
            const state = await this.apiClient.getDagStatus(sessionId);
            if (state) {
                this.currentState = state;
                this._renderAll(state);
                this._updateStats(state);
                this._startSSE();
                this._updateLastUpdate();
            }
        } catch (error) {
            console.error('Failed to load session:', error);
        }
    }

    _startSSE() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        this._setConnectionStatus('connecting');

        this.eventSource = this.apiClient.createEventSource(this.currentSessionId);

        this.eventSource.onopen = () => {
            this._setConnectionStatus('connected');
        };

        this.eventSource.onmessage = (event) => {
            try {
                const envelope = JSON.parse(event.data);
                if (envelope.event === 'state_update' && envelope.data) {
                    this.currentState = envelope.data;
                    this._updateAll(envelope.data);
                    this._updateStats(envelope.data);
                    this._updateLastUpdate();
                }
            } catch (error) {
                console.error('Failed to parse SSE message:', error);
            }
        };

        this.eventSource.onerror = () => {
            this._setConnectionStatus('disconnected');

            setTimeout(() => {
                if (this.currentSessionId) {
                    this._startSSE();
                }
            }, 5000);
        };
    }

    _disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }

        if (this.wsClient) {
            this.wsClient.disconnect();
            this.wsClient = null;
        }

        this._setConnectionStatus('disconnected');
    }

    _setConnectionStatus(status) {
        this.connectionStatus.className = `status-indicator ${status}`;
        const statusText = {
            'connected': 'Connected',
            'connecting': 'Connecting...',
            'disconnected': 'Disconnected'
        };
        this.connectionStatus.textContent = statusText[status] || status;
    }

    _updateLastUpdate() {
        const now = new Date();
        this.lastUpdate.textContent = `Last update: ${now.toLocaleTimeString()}`;
    }

    _renderAll(state) {
        this.dagRenderer.render(state);
        this.timelineView.render(state);
    }

    _updateAll(state) {
        this.dagRenderer.update(state);
        this.timelineView.update(state);
    }

    _updateStats(state) {
        if (!state) return;

        this.statElements.status.textContent = state.status || '-';
        this.statElements.status.className = `stat-value status-${(state.status || '').toLowerCase()}`;

        this.statElements.iteration.textContent = state.global_iteration !== undefined
            ? state.global_iteration.toString()
            : '-';

        this.statElements.backtrack.textContent = state.backtrack_count !== undefined
            ? state.backtrack_count.toString()
            : '-';

        let completedCount = 0;
        let failedCount = 0;
        if (state.nodes) {
            Object.values(state.nodes).forEach(node => {
                if (node.status === 'COMPLETED') completedCount++;
                if (node.status === 'FAILED') failedCount++;
            });
        }
        this.statElements.completed.textContent = completedCount.toString();
        this.statElements.failed.textContent = failedCount.toString();

        this.statElements.duration.textContent = state.duration_seconds
            ? `${state.duration_seconds.toFixed(1)}s`
            : '-';
    }

    setupEventListeners() {
        this.sessionSelect.addEventListener('change', (event) => {
            this.loadSession(event.target.value);
        });

        this.closeNodeDetailBtn.addEventListener('click', () => {
            this.nodeDetailPanel.hide();
        });

        document.addEventListener('node-selected', (event) => {
            this.handleNodeSelected(event);
        });

        window.addEventListener('resize', () => {
            if (this.currentState) {
                this.dagRenderer.render(this.currentState);
                this.timelineView.render(this.currentState);
            }
        });
    }

    handleNodeSelected(event) {
        const { nodeId } = event.detail || {};
        if (!nodeId || !this.currentState) {
            return;
        }

        this.nodeDetailPanel.show(nodeId, this.currentState);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const app = new DashboardApp();
    app.init().catch(error => {
        console.error('Failed to initialize dashboard:', error);
    });
});
