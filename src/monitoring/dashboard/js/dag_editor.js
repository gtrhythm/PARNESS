/* global d3 */
import { eventBus } from './event_bus.js';

export class EditorNode {
    constructor(id, moduleName, config = {}) {
        this.id = id;
        this.moduleName = moduleName;
        this.config = config;
        this.input_mapping = config.input_mapping || {};
        this.output_mapping = config.output_mapping || {};
        this.routes = config.routes || {};
        this.params = config.params || {};
        this.depends_on = config.depends_on || [];
        this.x = 0;
        this.y = 0;
    }

    toDict() {
        const d = {
            id: this.id,
            module: this.moduleName,
            depends_on: this.depends_on,
            params: this.params,
            input_mapping: this.input_mapping,
            output_mapping: this.output_mapping,
        };
        if (Object.keys(this.routes).length > 0) d.routes = this.routes;
        return d;
    }

    static fromDict(data) {
        const config = data.config || data;
        const node = new EditorNode(
            data.id,
            data.module || data.type,
            {
                ...config,
                input_mapping: data.input_mapping || config.input_mapping || {},
                output_mapping: data.output_mapping || config.output_mapping || {},
                routes: data.routes || config.routes || {},
                params: data.params || config.params || {},
                depends_on: data.depends_on || config.depends_on || [],
            }
        );
        return node;
    }
}

export class EditorEdge {
    constructor(source, target) {
        this.source = source;
        this.target = target;
    }

    toDict() {
        return { from: this.source, to: this.target };
    }

    static fromDict(data) {
        return new EditorEdge(data.from || data.source, data.to || data.target);
    }
}

export class EditorGraph {
    constructor(name = 'my_pipeline') {
        this.name = name;
        this.nodes = new Map();
        this.edges = [];
        this.config = {};
    }

    addNode(node) {
        this.nodes.set(node.id, node);
    }

    removeNode(nodeId) {
        this.nodes.delete(nodeId);
        this.edges = this.edges.filter(e => e.source !== nodeId && e.target !== nodeId);
        this.nodes.forEach(n => {
            n.depends_on = n.depends_on.filter(d => d !== nodeId);
        });
    }

    addEdge(edge) {
        const exists = this.edges.some(
            e => e.source === edge.source && e.target === edge.target
        );
        if (!exists) {
            this.edges.push(edge);
            const targetNode = this.nodes.get(edge.target);
            if (targetNode && !targetNode.depends_on.includes(edge.source)) {
                targetNode.depends_on.push(edge.source);
            }
        }
    }

    removeEdge(source, target) {
        this.edges = this.edges.filter(e => !(e.source === source && e.target === target));
        const targetNode = this.nodes.get(target);
        if (targetNode) {
            targetNode.depends_on = targetNode.depends_on.filter(d => d !== source);
        }
    }

    getNode(nodeId) {
        return this.nodes.get(nodeId);
    }

    toDict() {
        return {
            name: this.name,
            config: this.config,
            nodes: Array.from(this.nodes.values()).map(n => n.toDict()),
            edges: this.edges.map(e => e.toDict()),
        };
    }

    static fromDict(data) {
        const graph = new EditorGraph(data.name || 'my_pipeline');
        graph.config = data.config || {};
        (data.nodes || []).forEach(n => graph.addNode(EditorNode.fromDict(n)));
        (data.edges || []).forEach(e => graph.addEdge(EditorEdge.fromDict(e)));
        return graph;
    }
}

export class EditorDAGRenderer {
    constructor(containerSelector) {
        this.containerSelector = containerSelector;
        this.container = document.querySelector(containerSelector);
        this.graph = new EditorGraph();
        this._connecting = null;
        this._nodeIdCounter = 0;
        this.svg = null;
        this.g = null;
        this.zoom = null;
        this.nodeWidth = 160;
        this.nodeHeight = 60;
        this._initialized = false;
    }

    init() {
        if (this._initialized) return;
        if (!this.container) {
            console.error('Editor container not found:', this.containerSelector);
            return;
        }

        this.svg = d3.select(this.container).select('svg');
        if (this.svg.empty()) {
            this.svg = d3.select(this.container).append('svg');
        }
        this.svg.attr('width', '100%').attr('height', '100%');

        this.zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {
                this.g.attr('transform', event.transform);
            });

        this.svg.call(this.zoom);
        this.g = this.svg.append('g');

        const defs = this.svg.append('defs');
        defs.append('marker')
            .attr('id', 'editor-arrowhead')
            .attr('viewBox', '-0 -5 10 10')
            .attr('refX', 8)
            .attr('refY', 0)
            .attr('orient', 'auto')
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .append('path')
            .attr('d', 'M 0,-5 L 10,0 L 0,5')
            .attr('fill', '#64748b');

        this._setupDrop();
        this._setupDblClick();
        this._renderEditor();
        this._initialized = true;
    }

    _setupDrop() {
        this.container.addEventListener('dragover', (event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'copy';
        });

        this.container.addEventListener('drop', (event) => {
            event.preventDefault();
            try {
                const data = JSON.parse(event.dataTransfer.getData('application/json'));
                if (data.type === 'catalog-module') {
                    const rect = this.container.getBoundingClientRect();
                    const point = d3.pointer(event, this.g.node());
                    const transform = d3.zoomTransform(this.svg.node());
                    const x = (point[0] - transform.x) / transform.k;
                    const y = (point[1] - transform.y) / transform.k;
                    this._addNodeFromCatalog(data.module, x, y);
                }
            } catch (e) {
                console.error('Drop handling failed:', e);
            }
        });
    }

    _setupDblClick() {
        this.svg.on('dblclick', (event) => {
            const target = event.target;
            const nodeGroup = d3.select(target.closest('.editor-node'));
            if (!nodeGroup.empty()) {
                const nodeId = nodeGroup.datum()?.id;
                if (nodeId) {
                    eventBus.emit('editor:node-double-clicked', { nodeId });
                }
            }
        });
    }

    _addNodeFromCatalog(moduleData, x, y) {
        this._nodeIdCounter++;
        const nodeId = `${moduleData.name}_${this._nodeIdCounter}`;
        const node = new EditorNode(nodeId, moduleData.name, {
            params: {},
            input_mapping: {},
            output_mapping: {},
            routes: {},
            depends_on: [],
        });
        node.x = x;
        node.y = y;
        this.graph.addNode(node);
        this._renderEditor();
        eventBus.emit('editor:graph-changed', { graph: this.graph });
    }

    addNode(moduleName, config = {}) {
        this._nodeIdCounter++;
        const nodeId = `${moduleName}_${this._nodeIdCounter}`;
        const node = new EditorNode(nodeId, moduleName, config);
        const existing = Array.from(this.graph.nodes.values());
        node.x = 100 + (existing.length % 4) * 240;
        node.y = 100 + Math.floor(existing.length / 4) * 160;
        this.graph.addNode(node);
        this._renderEditor();
        eventBus.emit('editor:graph-changed', { graph: this.graph });
        return node;
    }

    removeNode(nodeId) {
        this.graph.removeNode(nodeId);
        this._renderEditor();
        eventBus.emit('editor:graph-changed', { graph: this.graph });
    }

    addEdge(source, target) {
        const edge = new EditorEdge(source, target);
        this.graph.addEdge(edge);
        this._renderEditor();
        eventBus.emit('editor:graph-changed', { graph: this.graph });
    }

    removeEdge(source, target) {
        this.graph.removeEdge(source, target);
        this._renderEditor();
        eventBus.emit('editor:graph-changed', { graph: this.graph });
    }

    _renderEditor() {
        if (!this.g) return;

        this.g.selectAll('*').remove();

        const nodes = Array.from(this.graph.nodes.values());
        const edges = this.graph.edges;

        const edgesGroup = this.g.append('g').attr('class', 'edges');
        const nodesGroup = this.g.append('g').attr('class', 'nodes');

        edges.forEach(edge => {
            const sourceNode = this.graph.nodes.get(edge.source);
            const targetNode = this.graph.nodes.get(edge.target);
            if (!sourceNode || !targetNode) return;

            const sx = sourceNode.x + this.nodeWidth;
            const sy = sourceNode.y + this.nodeHeight / 2;
            const tx = targetNode.x;
            const ty = targetNode.y + this.nodeHeight / 2;
            const midX = (sx + tx) / 2;

            edgesGroup.append('path')
                .attr('class', 'edge')
                .attr('d', `M ${sx},${sy} C ${midX},${sy} ${midX},${ty} ${tx},${ty}`)
                .attr('fill', 'none')
                .attr('stroke', '#64748b')
                .attr('stroke-width', 2)
                .attr('marker-end', 'url(#editor-arrowhead)');
        });

        const nodeGroups = nodesGroup.selectAll('.editor-node')
            .data(nodes, d => d.id)
            .enter()
            .append('g')
            .attr('class', 'editor-node')
            .attr('transform', d => `translate(${d.x}, ${d.y})`)
            .style('cursor', 'grab');

        nodeGroups.append('rect')
            .attr('width', this.nodeWidth)
            .attr('height', this.nodeHeight)
            .attr('rx', 8)
            .attr('ry', 8)
            .attr('fill', '#1e293b')
            .attr('stroke', '#3b82f6')
            .attr('stroke-width', 2);

        nodeGroups.append('text')
            .attr('x', this.nodeWidth / 2)
            .attr('y', 22)
            .attr('text-anchor', 'middle')
            .attr('fill', '#f1f5f9')
            .attr('font-size', '12px')
            .attr('font-weight', 'bold')
            .text(d => d.id.length > 16 ? d.id.substring(0, 14) + '..' : d.id);

        nodeGroups.append('text')
            .attr('x', this.nodeWidth / 2)
            .attr('y', 42)
            .attr('text-anchor', 'middle')
            .attr('fill', '#94a3b8')
            .attr('font-size', '10px')
            .text(d => d.moduleName);

        const drag = d3.drag()
            .on('start', (event, d) => {
                d3.select(event.sourceEvent.target.closest('.editor-node'))
                    .style('cursor', 'grabbing');
            })
            .on('drag', (event, d) => {
                d.x += event.dx;
                d.y += event.dy;
                d3.select(event.sourceEvent.target.closest('.editor-node'))
                    .attr('transform', `translate(${d.x}, ${d.y})`);
                this._updateEdges(edgesGroup);
            })
            .on('end', (event, d) => {
                d3.select(event.sourceEvent.target.closest('.editor-node'))
                    .style('cursor', 'grab');
            });

        nodeGroups.call(drag);

        nodeGroups.append('circle')
            .attr('class', 'port port-out')
            .attr('cx', this.nodeWidth)
            .attr('cy', this.nodeHeight / 2)
            .attr('r', 6)
            .attr('fill', '#3b82f6')
            .attr('stroke', '#1e293b')
            .attr('stroke-width', 2)
            .style('cursor', 'crosshair')
            .on('mousedown', (event, d) => {
                event.stopPropagation();
                this._connecting = { source: d.id };
            });

        nodeGroups.append('circle')
            .attr('class', 'port port-in')
            .attr('cx', 0)
            .attr('cy', this.nodeHeight / 2)
            .attr('r', 6)
            .attr('fill', '#22c55e')
            .attr('stroke', '#1e293b')
            .attr('stroke-width', 2)
            .style('cursor', 'crosshair')
            .on('mouseup', (event, d) => {
                if (this._connecting && this._connecting.source !== d.id) {
                    this.addEdge(this._connecting.source, d.id);
                }
                this._connecting = null;
            });

        this.svg.on('mouseup', () => {
            this._connecting = null;
        });

        nodeGroups.append('text')
            .attr('x', this.nodeWidth + 10)
            .attr('y', this.nodeHeight / 2 + 4)
            .attr('fill', '#64748b')
            .attr('font-size', '9px')
            .text('out');

        nodeGroups.append('text')
            .attr('x', -20)
            .attr('y', this.nodeHeight / 2 + 4)
            .attr('fill', '#64748b')
            .attr('font-size', '9px')
            .text('in');
    }

    _updateEdges(edgesGroup) {
        edgesGroup.selectAll('path').each((d, i, els) => {
            const edge = this.graph.edges[i];
            if (!edge) return;
            const sourceNode = this.graph.nodes.get(edge.source);
            const targetNode = this.graph.nodes.get(edge.target);
            if (sourceNode && targetNode) {
                const sx = sourceNode.x + this.nodeWidth;
                const sy = sourceNode.y + this.nodeHeight / 2;
                const tx = targetNode.x;
                const ty = targetNode.y + this.nodeHeight / 2;
                const midX = (sx + tx) / 2;
                d3.select(els[i])
                    .attr('d', `M ${sx},${sy} C ${midX},${sy} ${midX},${ty} ${tx},${ty}`);
            }
        });
    }

    loadGraph(graphData) {
        this.graph = EditorGraph.fromDict(graphData);
        const nodes = Array.from(this.graph.nodes.values());
        nodes.forEach((n, i) => {
            if (n.x === 0 && n.y === 0) {
                n.x = 100 + (i % 4) * 240;
                n.y = 100 + Math.floor(i / 4) * 160;
            }
        });
        this._renderEditor();
    }

    toDict() {
        return this.graph.toDict();
    }
}
