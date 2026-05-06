import { eventBus } from './event_bus.js';

export class SessionState {
    constructor(sessionId, pipelineName, status = 'IDLE', lastActiveAt = null, currentState = null) {
        this.sessionId = sessionId;
        this.pipelineName = pipelineName;
        this.status = status;
        this.lastActiveAt = lastActiveAt || new Date().toISOString();
        this.currentState = currentState;
    }
}

export class SessionManager {
    constructor() {
        this.sessions = new Map();
        this.maxSessions = 10;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.baseReconnectDelay = 1000;
        this.heartbeatInterval = null;
    }

    async init() {
        await this._discoverSessions();
        this._connectGlobalWS();
    }

    async _discoverSessions() {
        try {
            const response = await fetch('/api/dag/status');
            if (!response.ok) {
                throw new Error(`Failed to discover sessions: ${response.status}`);
            }
            const statuses = await response.json();
            statuses.forEach(s => {
                const state = new SessionState(
                    s.session_id,
                    s.pipeline_name,
                    s.status,
                    s.last_active_at,
                    s
                );
                this.sessions.set(s.session_id, state);
            });
            eventBus.emit('sessions:discovered', Array.from(this.sessions.values()));
        } catch (e) {
            console.error('Session discovery failed:', e);
        }
    }

    _connectGlobalWS() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsURL = `${protocol}//${window.location.host}/ws/dag`;

        this.ws = new WebSocket(wsURL);

        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            this._startHeartbeat();
            eventBus.emit('session:ws-connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this._handleMessage(data);
            } catch (e) {
                console.error('Failed to parse WS message:', e);
            }
        };

        this.ws.onclose = () => {
            this._stopHeartbeat();
            eventBus.emit('session:ws-disconnected');
            this._scheduleReconnect();
        };

        this.ws.onerror = (error) => {
            console.error('Session WS error:', error);
        };
    }

    _handleMessage(data) {
        switch (data.type) {
            case 'state_update': {
                const session = this.sessions.get(data.session_id);
                if (session) {
                    session.currentState = data.state;
                    session.status = data.state?.status || session.status;
                    session.lastActiveAt = new Date().toISOString();
                    eventBus.emit('session:state-updated', { sessionId: data.session_id, state: data.state });
                }
                break;
            }
            case 'session_list': {
                if (Array.isArray(data.sessions)) {
                    data.sessions.forEach(s => {
                        if (!this.sessions.has(s.session_id)) {
                            this.sessions.set(s.session_id, new SessionState(
                                s.session_id,
                                s.pipeline_name,
                                s.status,
                                s.last_active_at
                            ));
                        }
                    });
                    eventBus.emit('sessions:updated', Array.from(this.sessions.values()));
                }
                break;
            }
            case 'heartbeat':
                break;
            default:
                console.warn('Unknown WS message type:', data.type);
        }
    }

    _scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max WS reconnect attempts reached');
            return;
        }
        this.reconnectAttempts++;
        const delay = this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        setTimeout(() => this._connectGlobalWS(), delay);
    }

    _startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 25000);
    }

    _stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    _send(payload) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(payload));
        } else {
            console.warn('Session WS not connected');
        }
    }

    subscribe(sessionId) {
        this._send({ type: 'subscribe', session_id: sessionId });
    }

    unsubscribe(sessionId) {
        this._send({ type: 'unsubscribe', session_id: sessionId });
    }

    cancelRun(sessionId) {
        this._send({ type: 'cancel_run', session_id: sessionId });
    }

    updateConfig(sessionId, config) {
        this._send({ type: 'update_config', session_id: sessionId, config });
    }

    openSession(sessionId, pipelineName) {
        if (this.sessions.size >= this.maxSessions) {
            const oldest = this.sessions.keys().next().value;
            this.closeSession(oldest);
        }
        const state = new SessionState(sessionId, pipelineName);
        this.sessions.set(sessionId, state);
        this.subscribe(sessionId);
        eventBus.emit('session:opened', state);
        return state;
    }

    closeSession(sessionId) {
        this.unsubscribe(sessionId);
        this.sessions.delete(sessionId);
        eventBus.emit('session:closed', { sessionId });
    }

    disconnect() {
        this._stopHeartbeat();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}
