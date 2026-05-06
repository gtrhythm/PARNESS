class EventBus {
    constructor() { this._handlers = {}; }
    on(event, handler) {
        (this._handlers[event] ||= []).push(handler);
        return () => this.off(event, handler);
    }
    off(event, handler) {
        this._handlers[event] = (this._handlers[event] || []).filter(h => h !== handler);
    }
    emit(event, data) {
        (this._handlers[event] || []).forEach(h => { try { h(data); } catch(e) { console.error(e); } });
    }
}
export const eventBus = new EventBus();
