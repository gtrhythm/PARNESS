export class WSClient {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
        this.ws = null;
        this.sessionId = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000;
        this.heartbeatInterval = null;
        this.messageHandler = null;
        this.connectHandler = null;
        this.disconnectHandler = null;
        this.isIntentionallyClosed = false;
    }

    connect(sessionId) {
        this.sessionId = sessionId;
        this.isIntentionallyClosed = false;
        this.reconnectAttempts = 0;
        this._establishConnection();
    }

    _establishConnection() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsURL = `${protocol}//${window.location.host}${this.baseURL}/ws/dag/${this.sessionId}`;
        
        this.ws = new WebSocket(wsURL);

        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            this._startHeartbeat();
            if (this.connectHandler) {
                this.connectHandler();
            }
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'heartbeat') {
                    return;
                }
                if (this.messageHandler) {
                    this.messageHandler(data);
                }
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        this.ws.onclose = () => {
            this._stopHeartbeat();
            if (this.disconnectHandler) {
                this.disconnectHandler();
            }
            if (!this.isIntentionallyClosed) {
                this._attemptReconnect();
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    _attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        
        console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`);
        
        setTimeout(() => {
            if (!this.isIntentionallyClosed) {
                this._establishConnection();
            }
        }, delay);
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

    disconnect() {
        this.isIntentionallyClosed = true;
        this._stopHeartbeat();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket is not connected');
        }
    }

    onMessage(callback) {
        this.messageHandler = callback;
    }

    onConnect(callback) {
        this.connectHandler = callback;
    }

    onDisconnect(callback) {
        this.disconnectHandler = callback;
    }

    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }
}
