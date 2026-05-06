import { eventBus } from './event_bus.js';

export class ValidationEngine {
    constructor(moduleCatalog = null) {
        this.moduleCatalog = moduleCatalog;
    }

    validate(graph) {
        const errors = [];
        const warnings = [];

        const cycleResult = this._checkNoCycles(graph);
        if (!cycleResult.ok) errors.push(...cycleResult.messages);

        const depResult = this._checkDependencies(graph);
        if (!depResult.ok) errors.push(...depResult.messages);

        const typeResult = this._checkTypeCompatibility(graph);
        if (!typeResult.ok) errors.push(...typeResult.messages);

        const inputResult = this._checkRequiredInputs(graph);
        if (!inputResult.ok) errors.push(...inputResult.messages);

        const conflictResult = this._checkNoConflicts(graph);
        if (!conflictResult.ok) errors.push(...conflictResult.messages);

        const orphanResult = this._checkNoOrphans(graph);
        if (!orphanResult.ok) warnings.push(...orphanResult.messages);

        const routeResult = this._checkRoutes(graph);
        if (!routeResult.ok) warnings.push(...routeResult.messages);

        const result = {
            valid: errors.length === 0,
            errors,
            warnings
        };

        eventBus.emit('validation:completed', result);
        return result;
    }

    _checkNoCycles(graph) {
        const adj = new Map();
        const nodes = Array.from(graph.nodes.keys());
        nodes.forEach(id => adj.set(id, []));
        graph.edges.forEach(e => {
            if (adj.has(e.source)) {
                adj.get(e.source).push(e.target);
            }
        });

        const WHITE = 0, GRAY = 1, BLACK = 2;
        const color = new Map();
        nodes.forEach(id => color.set(id, WHITE));
        const messages = [];

        const dfs = (node) => {
            color.set(node, GRAY);
            for (const neighbor of (adj.get(node) || [])) {
                if (color.get(neighbor) === GRAY) {
                    messages.push({ check: 'noCycles', message: `Cycle detected involving node '${neighbor}'` });
                    return true;
                }
                if (color.get(neighbor) === WHITE && dfs(neighbor)) {
                    return true;
                }
            }
            color.set(node, BLACK);
            return false;
        };

        for (const node of nodes) {
            if (color.get(node) === WHITE) {
                dfs(node);
            }
        }

        return { ok: messages.length === 0, messages };
    }

    _checkDependencies(graph) {
        const nodeIds = new Set(graph.nodes.keys());
        const messages = [];

        graph.edges.forEach(e => {
            if (!nodeIds.has(e.source)) {
                messages.push({ check: 'dependencies', message: `Edge references unknown source node '${e.source}'` });
            }
            if (!nodeIds.has(e.target)) {
                messages.push({ check: 'dependencies', message: `Edge references unknown target node '${e.target}'` });
            }
        });

        return { ok: messages.length === 0, messages };
    }

    _checkTypeCompatibility(graph) {
        const messages = [];

        if (!this.moduleCatalog) {
            return { ok: true, messages };
        }

        graph.edges.forEach(e => {
            const sourceNode = graph.nodes.get(e.source);
            const targetNode = graph.nodes.get(e.target);
            if (!sourceNode || !targetNode) return;

            const sourceModule = this.moduleCatalog.get(sourceNode.type);
            const targetModule = this.moduleCatalog.get(targetNode.type);
            if (!sourceModule || !targetModule) return;

            const outputs = (sourceModule.outputs || []).map(o => o.type || o.name);
            const inputs = (targetModule.inputs || []).map(i => i.type || i.name);

            if (outputs.length > 0 && inputs.length > 0) {
                const compatible = outputs.some(o => inputs.includes(o));
                if (!compatible) {
                    messages.push({
                        check: 'typeCompatibility',
                        message: `Type mismatch: '${e.source}' outputs [${outputs.join(', ')}] but '${e.target}' expects [${inputs.join(', ')}]`
                    });
                }
            }
        });

        return { ok: messages.length === 0, messages };
    }

    _checkRequiredInputs(graph) {
        const messages = [];

        if (!this.moduleCatalog) {
            return { ok: true, messages };
        }

        const incomingEdges = new Map();
        graph.nodes.forEach((_, id) => incomingEdges.set(id, []));
        graph.edges.forEach(e => {
            if (incomingEdges.has(e.target)) {
                incomingEdges.get(e.target).push(e);
            }
        });

        graph.nodes.forEach((node, id) => {
            const module = this.moduleCatalog.get(node.type);
            if (!module) return;

            const requiredInputs = (module.inputs || []).filter(i => i.required);
            const incoming = incomingEdges.get(id) || [];
            if (requiredInputs.length > 0 && incoming.length < requiredInputs.length) {
                messages.push({
                    check: 'requiredInputs',
                    message: `Node '${id}' is missing required inputs (needs ${requiredInputs.length}, has ${incoming.length})`
                });
            }
        });

        return { ok: messages.length === 0, messages };
    }

    _checkNoConflicts(graph) {
        const messages = [];
        const edgeSet = new Set();

        graph.edges.forEach(e => {
            const key = `${e.source}->${e.target}`;
            if (edgeSet.has(key)) {
                messages.push({
                    check: 'noConflicts',
                    message: `Duplicate edge from '${e.source}' to '${e.target}'`
                });
            }
            edgeSet.add(key);
        });

        return { ok: messages.length === 0, messages };
    }

    _checkNoOrphans(graph) {
        const messages = [];
        if (graph.nodes.size <= 1) return { ok: true, messages };

        const connected = new Set();
        graph.edges.forEach(e => {
            connected.add(e.source);
            connected.add(e.target);
        });

        graph.nodes.forEach((_, id) => {
            if (!connected.has(id)) {
                messages.push({
                    check: 'noOrphans',
                    message: `Node '${id}' is not connected to any other node`
                });
            }
        });

        return { ok: messages.length === 0, messages };
    }

    _checkRoutes(graph) {
        const messages = [];

        graph.nodes.forEach((node, id) => {
            if (node.type === 'LOOP' || node.type === 'CONDITIONAL') {
                const routes = node.routes || {};
                if (!routes || Object.keys(routes).length === 0) {
                    messages.push({
                        check: 'routes',
                        message: `Node '${id}' of type '${node.type}' has no routes defined`
                    });
                }
            }
        });

        return { ok: messages.length === 0, messages };
    }
}
