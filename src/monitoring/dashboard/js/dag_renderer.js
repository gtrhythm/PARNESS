/* global d3 */

export class DAGRenderer {
    constructor(containerSelector) {
        this.container = document.querySelector(containerSelector);
        if (!this.container) {
            throw new Error(`Container ${containerSelector} not found`);
        }

        this.svg = d3.select('#dag-svg');
        this.width = 0;
        this.height = 0;
        this.nodes = [];
        this.edges = [];
        this.backtrackEdges = [];
        this.zoom = null;
        this.g = null;
        this.simulation = null;

        this.nodeWidth = 140;
        this.nodeHeight = 50;
        this.nodeSpacingX = 50;
        this.nodeSpacingY = 80;

        this._setupSVG();
        this._setupDefs();
    }

    _setupSVG() {
        this.zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {
                this.g.attr('transform', event.transform);
            });

        this.svg.call(this.zoom);

        this.g = this.svg.append('g');

        this.width = this.container.clientWidth;
        this.height = this.container.clientHeight;

        this.svg.attr('viewBox', `0 0 ${this.width} ${this.height}`);
    }

    _setupDefs() {
        const defs = this.svg.append('defs');

        defs.append('marker')
            .attr('id', 'arrowhead')
            .attr('viewBox', '-0 -5 10 10')
            .attr('refX', 8)
            .attr('refY', 0)
            .attr('orient', 'auto')
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .append('path')
            .attr('d', 'M 0,-5 L 10,0 L 0,5')
            .attr('class', 'edge-arrow');

        defs.append('marker')
            .attr('id', 'arrowhead-running')
            .attr('viewBox', '-0 -5 10 10')
            .attr('refX', 8)
            .attr('refY', 0)
            .attr('orient', 'auto')
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .append('path')
            .attr('d', 'M 0,-5 L 10,0 L 0,5')
            .attr('class', 'edge-arrow edge-running');

        defs.append('marker')
            .attr('id', 'arrowhead-backtrack')
            .attr('viewBox', '-0 -5 10 10')
            .attr('refX', 8)
            .attr('refY', 0)
            .attr('orient', 'auto')
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .append('path')
            .attr('d', 'M 0,-5 L 10,0 L 0,5')
            .attr('class', 'edge-arrow edge-backtrack');

        defs.append('marker')
            .attr('id', 'arrowhead-conditional')
            .attr('viewBox', '-0 -5 10 10')
            .attr('refX', 8)
            .attr('refY', 0)
            .attr('orient', 'auto')
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .append('path')
            .attr('d', 'M 0,-5 L 10,0 L 0,5')
            .attr('class', 'edge-arrow edge-conditional');
    }

    _buildGraph(state) {
        const nodes = {};
        const edges = [];
        const conditionalEdges = [];
        const backtrackEdges = [];

        const nodeStates = state?.nodes || {};
        if (!nodeStates || typeof nodeStates !== 'object') {
            return { nodes: [], edges: [], conditionalEdges: [], backtrackEdges: [] };
        }

        const explicitEdges = state?.edges || [];

        let index = 0;
        Object.entries(nodeStates).forEach(([nodeId, nodeState]) => {
            nodes[nodeId] = {
                id: nodeId,
                type: (nodeState.node_type || 'SEQUENTIAL').toUpperCase(),
                status: (nodeState.status || 'PENDING').toUpperCase(),
                depends_on: nodeState.depends_on || [],
                index: index++,
                x: 0,
                y: 0,
                started_at: nodeState.started_at,
                completed_at: nodeState.completed_at,
                duration_seconds: nodeState.duration_seconds,
                iteration_count: nodeState.iteration_count,
                score: nodeState.score,
                decision: nodeState.decision
            };
        });

        if (explicitEdges.length > 0) {
            explicitEdges.forEach(edge => {
                const sourceId = edge.from || edge.source;
                const targetId = edge.to || edge.target;
                if (!nodes[sourceId] || !nodes[targetId]) return;

                const edgeObj = {
                    source: sourceId,
                    target: targetId,
                    label: edge.label || ''
                };

                if (edge.backtrack) {
                    backtrackEdges.push(edgeObj);
                } else if (edge.label) {
                    conditionalEdges.push(edgeObj);
                } else {
                    edges.push(edgeObj);
                }
            });
        } else {
            Object.values(nodes).forEach(node => {
                if (node.depends_on && Array.isArray(node.depends_on)) {
                    node.depends_on.forEach(depId => {
                        if (nodes[depId]) {
                            edges.push({ source: depId, target: node.id, label: '' });
                        }
                    });
                }
            });
        }

        if (state.backtrack_history && state.backtrack_history.length > 0) {
            const seen = new Set();
            backtrackEdges.forEach(e => {
                seen.add(`${e.source}->${e.target}`);
            });
            state.backtrack_history.forEach(bt => {
                const from = bt.from_node;
                const to = bt.to_node;
                if (from && to && nodes[from] && nodes[to] && !seen.has(`${from}->${to}`)) {
                    backtrackEdges.push({
                        source: from,
                        target: to,
                        label: bt.reason || '',
                        iteration: bt.iteration
                    });
                    seen.add(`${from}->${to}`);
                }
            });
        }

        return {
            nodes: Object.values(nodes),
            edges,
            conditionalEdges,
            backtrackEdges
        };
    }

    _calculateLayout(graph) {
        const nodes = graph.nodes;
        if (!nodes || nodes.length === 0) return;

        const layoutEdges = [...(graph.edges || []), ...(graph.conditionalEdges || [])];
        const nodeMap = new Map(nodes.map(n => [n.id, n]));

        // === Phase 1: Layer assignment (longest path, cycle-safe) ===
        const layerOf = new Map();
        const stack = new Set();
        const getLayer = (id) => {
            if (layerOf.has(id)) return layerOf.get(id);
            if (stack.has(id)) return 0;
            stack.add(id);
            const nd = nodeMap.get(id);
            if (!nd) { stack.delete(id); return 0; }
            const deps = (nd.depends_on || []).filter(d => nodeMap.has(d) && !stack.has(d));
            const layer = deps.length === 0 ? 0 : 1 + Math.max(...deps.map(getLayer));
            layerOf.set(id, layer);
            stack.delete(id);
            return layer;
        };
        nodes.forEach(n => getLayer(n.id));

        const maxLayer = Math.max(...layerOf.values(), 0);
        const layers = Array.from({ length: maxLayer + 1 }, () => []);
        nodes.forEach(n => { n._layer = layerOf.get(n.id); layers[n._layer].push(n); });

        // === Phase 2: Barycenter crossing minimization (8 sweeps) ===
        layers.forEach(layer => layer.forEach((n, i) => { n._pos = i; }));

        for (let pass = 0; pass < 8; pass++) {
            const down = pass % 2 === 0;
            for (let step = 0; step <= maxLayer; step++) {
                const l = down ? step : maxLayer - step;
                if ((l === 0 && down) || (l === maxLayer && !down)) continue;
                const refL = down ? l - 1 : l + 1;
                if (refL < 0 || refL > maxLayer) continue;

                const refIdx = new Map(layers[refL].map((n, i) => [n.id, i]));
                layers[l].forEach(n => {
                    const nbrs = layoutEdges
                        .filter(e => down ? e.target === n.id && refIdx.has(e.source) : e.source === n.id && refIdx.has(e.target))
                        .map(e => down ? e.source : e.target);
                    n._bc = nbrs.length === 0
                        ? (n._pos ?? 999)
                        : nbrs.reduce((s, id) => s + (refIdx.get(id) ?? 0), 0) / nbrs.length;
                });
                layers[l].sort((a, b) => (a._bc ?? 0) - (b._bc ?? 0));
                layers[l].forEach((n, i) => { n._pos = i; });
            }
        }

        // === Phase 3: Coordinate assignment ===
        const layerGap = this.nodeWidth + this.nodeSpacingX;
        const nodeGap = this.nodeHeight + this.nodeSpacingY;
        const totalW = maxLayer * layerGap;
        const x0 = (this.width - totalW) / 2 + this.nodeWidth / 2;

        layers.forEach((layer, l) => {
            const h = Math.max(0, layer.length - 1) * nodeGap;
            const y0 = this.height / 2 - h / 2;
            layer.forEach((n, i) => {
                n.x = x0 + l * layerGap;
                n.y = y0 + i * nodeGap;
            });
        });

        // === Phase 4: Port assignment ===
        const outEdges = new Map();
        const inEdges = new Map();
        nodes.forEach(n => { outEdges.set(n.id, []); inEdges.set(n.id, []); });
        layoutEdges.forEach(e => {
            if (outEdges.has(e.source)) outEdges.get(e.source).push(e);
            if (inEdges.has(e.target)) inEdges.get(e.target).push(e);
        });

        outEdges.forEach((edges, nodeId) => {
            edges.sort((a, b) => {
                const aT = nodeMap.get(a.target);
                const bT = nodeMap.get(b.target);
                return (aT ? aT._pos + aT._layer * 1000 : 0) - (bT ? bT._pos + bT._layer * 1000 : 0);
            });
            const nd = nodeMap.get(nodeId);
            const cnt = edges.length;
            edges.forEach((e, i) => {
                const py = cnt <= 1 ? nd.y
                    : nd.y - this.nodeHeight * 0.38 + this.nodeHeight * 0.76 * i / (cnt - 1);
                e.sourcePort = { x: nd.x + this.nodeWidth / 2, y: py };
            });
        });

        inEdges.forEach((edges, nodeId) => {
            edges.sort((a, b) => {
                const aS = nodeMap.get(a.source);
                const bS = nodeMap.get(b.source);
                return (aS ? aS._pos + aS._layer * 1000 : 0) - (bS ? bS._pos + bS._layer * 1000 : 0);
            });
            const nd = nodeMap.get(nodeId);
            const cnt = edges.length;
            edges.forEach((e, i) => {
                const py = cnt <= 1 ? nd.y
                    : nd.y - this.nodeHeight * 0.38 + this.nodeHeight * 0.76 * i / (cnt - 1);
                e.targetPort = { x: nd.x - this.nodeWidth / 2, y: py };
            });
        });

        // === Phase 5: Edge routing with waypoints for long edges ===
        layoutEdges.forEach(edge => {
            const srcLayer = layerOf.get(edge.source) ?? 0;
            const tgtLayer = layerOf.get(edge.target) ?? 0;
            const span = tgtLayer - srcLayer;

            if (span <= 1) {
                edge.waypoints = [];
            } else {
                const sp = edge.sourcePort;
                const tp = edge.targetPort;
                const dy = tp.y - sp.y;
                const wps = [];
                for (let l = srcLayer + 1; l < tgtLayer; l++) {
                    const wx = x0 + l * layerGap;
                    const frac = (l - srcLayer) / span;
                    let wy = sp.y + dy * frac;
                    wy = this._findChannel(layers[l], wy);
                    wps.push({ x: wx, y: wy });
                }
                edge.waypoints = wps;
            }
        });

        // === Backtrack edges ===
        (graph.backtrackEdges || []).forEach(edge => {
            const src = nodeMap.get(edge.source);
            const tgt = nodeMap.get(edge.target);
            edge.sourcePort = src ? { x: src.x + this.nodeWidth / 2, y: src.y } : { x: 0, y: 0 };
            edge.targetPort = tgt ? { x: tgt.x - this.nodeWidth / 2 - 10, y: tgt.y } : { x: 0, y: 0 };
            edge.waypoints = [];
        });
    }

    _findChannel(layerNodes, preferredY) {
        if (!layerNodes || layerNodes.length === 0) return preferredY;
        const half = this.nodeHeight / 2 + 8;
        const sorted = [...layerNodes].sort((a, b) => a.y - b.y);

        let bestY = preferredY;
        let bestDist = Infinity;

        const above = sorted[0].y - half - 5;
        if (Math.abs(above - preferredY) < bestDist) { bestDist = Math.abs(above - preferredY); bestY = above; }

        for (let i = 0; i < sorted.length - 1; i++) {
            const gap = (sorted[i].y + half + sorted[i + 1].y - half) / 2;
            if (Math.abs(gap - preferredY) < bestDist) { bestDist = Math.abs(gap - preferredY); bestY = gap; }
        }

        const below = sorted[sorted.length - 1].y + half + 5;
        if (Math.abs(below - preferredY) < bestDist) { bestDist = Math.abs(below - preferredY); bestY = below; }

        return bestY;
    }

    _createRoutedPath(edge) {
        const sp = edge.sourcePort;
        const tp = edge.targetPort;
        if (!sp || !tp) return '';
        const wp = edge.waypoints || [];

        if (wp.length === 0) {
            const dy = Math.abs(tp.y - sp.y);
            if (dy < 3) return `M${sp.x},${sp.y}L${tp.x},${tp.y}`;
            const midX = (sp.x + tp.x) / 2;
            return `M${sp.x},${sp.y}L${midX},${sp.y}L${midX},${tp.y}L${tp.x},${tp.y}`;
        }

        let d = `M${sp.x},${sp.y}`;
        let curY = sp.y;
        for (const w of wp) {
            d += `L${w.x},${curY}L${w.x},${w.y}`;
            curY = w.y;
        }
        d += `L${tp.x},${curY}L${tp.x},${tp.y}`;
        return d;
    }

    _edgeLabelPos(edge) {
        const sp = edge.sourcePort;
        const tp = edge.targetPort;
        const wp = edge.waypoints || [];
        if (wp.length > 0) {
            const mid = wp[Math.floor(wp.length / 2)];
            return { x: mid.x, y: mid.y - 10 };
        }
        return { x: (sp.x + tp.x) / 2, y: (sp.y + tp.y) / 2 - 10 };
    }

    render(state) {
        const graph = this._buildGraph(state);
        this.nodes = graph.nodes;
        this.edges = graph.edges;
        this.conditionalEdges = graph.conditionalEdges || [];
        this.backtrackEdges = graph.backtrackEdges;

        this._calculateLayout(graph);

        this.g.selectAll('*').remove();

        const edgesGroup = this.g.append('g').attr('class', 'edges');
        const conditionalGroup = this.g.append('g').attr('class', 'conditional-edges');
        const backtrackGroup = this.g.append('g').attr('class', 'backtrack-edges');
        const labelsGroup = this.g.append('g').attr('class', 'edge-labels');
        const nodesGroup = this.g.append('g').attr('class', 'nodes');

        const nodeMap = new Map(this.nodes.map(n => [n.id, n]));

        this.edges.forEach(edge => {
            const s = nodeMap.get(edge.source);
            const t = nodeMap.get(edge.target);
            if (!s || !t) return;
            const isRunning = s.status === 'RUNNING' || t.status === 'RUNNING';
            edgesGroup.append('path')
                .attr('class', `edge ${isRunning ? 'edge-running' : ''}`)
                .attr('d', this._createRoutedPath(edge))
                .attr('marker-end', isRunning ? 'url(#arrowhead-running)' : 'url(#arrowhead)');
        });

        this.conditionalEdges.forEach(edge => {
            const s = nodeMap.get(edge.source);
            const t = nodeMap.get(edge.target);
            if (!s || !t) return;
            conditionalGroup.append('path')
                .attr('class', 'edge edge-conditional')
                .attr('d', this._createRoutedPath(edge))
                .attr('marker-end', 'url(#arrowhead-conditional)');
            if (edge.label) {
                const pos = this._edgeLabelPos(edge);
                labelsGroup.append('text')
                    .attr('x', pos.x).attr('y', pos.y)
                    .attr('class', 'edge-label').attr('text-anchor', 'middle')
                    .text(edge.label);
            }
        });

        this.backtrackEdges.forEach(edge => {
            const s = nodeMap.get(edge.source);
            const t = nodeMap.get(edge.target);
            if (!s || !t) return;
            backtrackGroup.append('path')
                .attr('class', 'backtrack-edge')
                .attr('d', this._createBacktrackPath(s, t))
                .attr('marker-end', 'url(#arrowhead-backtrack)');
            if (edge.label) {
                const cp = this._backtrackControlPoint(s, t);
                labelsGroup.append('text')
                    .attr('x', cp.x).attr('y', cp.y - 8)
                    .attr('class', 'edge-label edge-label-backtrack')
                    .attr('text-anchor', 'middle')
                    .text(edge.label);
            }
        });

        const nodeGroups = nodesGroup.selectAll('.node')
            .data(this.nodes)
            .enter()
            .append('g')
            .attr('class', d => `node node-${d.status.toLowerCase()} node-type-${d.type.toLowerCase()}`)
            .attr('transform', d => `translate(${d.x - this.nodeWidth / 2}, ${d.y - this.nodeHeight / 2})`)
            .style('cursor', 'pointer');

        nodeGroups.append('rect')
            .attr('class', 'node-rect')
            .attr('width', this.nodeWidth)
            .attr('height', this.nodeHeight)
            .attr('rx', d => this._getNodeRx(d.type))
            .attr('ry', d => this._getNodeRx(d.type))
            .attr('fill', d => this._getNodeColor(d.status));

        nodeGroups.append('text')
            .attr('class', 'node-label')
            .attr('x', this.nodeWidth / 2)
            .attr('y', this.nodeHeight / 2 - 8)
            .text(d => d.id.length > 18 ? d.id.substring(0, 16) + '...' : d.id);

        nodeGroups.append('text')
            .attr('class', 'node-label')
            .attr('x', this.nodeWidth / 2)
            .attr('y', this.nodeHeight / 2 + 12)
            .style('font-size', '10px')
            .style('fill', 'var(--color-bg-primary)')
            .text(d => d.status);

        nodeGroups.on('click', (event, d) => {
            event.stopPropagation();
            this.container.dispatchEvent(new CustomEvent('node-selected', { bubbles: true, detail: { nodeId: d.id } }));
        });

        nodeGroups.on('mouseenter', (event, d) => this._showTooltip(event, d));
        nodeGroups.on('mouseleave', () => this._hideTooltip());
    }

    _getNodeColor(status) {
        const colors = {
            'PENDING': 'var(--color-pending)',
            'RUNNING': 'var(--color-running)',
            'COMPLETED': 'var(--color-completed)',
            'FAILED': 'var(--color-failed)'
        };
        return colors[status] || colors['PENDING'];
    }

    _createBacktrackPath(source, target) {
        const sx = source.x + this.nodeWidth / 2;
        const sy = source.y;
        const tx = target.x - this.nodeWidth / 2 - 10;
        const ty = target.y;
        const dx = tx - sx;
        const offset = Math.max(Math.abs(dx) * 0.3, 50);
        const cpy = Math.min(sy, ty) - offset;
        return `M${sx},${sy} C${sx},${cpy} ${tx},${cpy} ${tx},${ty}`;
    }

    _getNodeRx(type) {
        switch ((type || '').toUpperCase()) {
            case 'DECISION': return 30;
            case 'CONDITIONAL': return 4;
            case 'ITERATIVE': return 16;
            default: return 8;
        }
    }

    _backtrackControlPoint(source, target) {
        const sx = source.x + this.nodeWidth / 2;
        const sy = source.y;
        const tx = target.x - this.nodeWidth / 2 - 10;
        const ty = target.y;
        const offset = Math.max(Math.abs(tx - sx) * 0.3, 50);
        const cpy = Math.min(sy, ty) - offset;
        return {
            x: (sx + tx) / 2,
            y: cpy
        };
    }

    _showTooltip(event, d) {
        const tooltip = document.getElementById('tooltip');
        let content = `<div class="tooltip-title">${d.id}</div>`;
        content += `<div class="tooltip-content">`;
        content += `Status: ${d.status}<br>`;
        if (d.duration_seconds) {
            content += `Duration: ${d.duration_seconds.toFixed(2)}s<br>`;
        }
        if (d.iteration_count !== undefined && d.iteration_count !== null) {
            content += `Iteration: ${d.iteration_count}`;
            if (d.score !== undefined && d.score !== null) {
                content += ` (score: ${d.score.toFixed(2)})`;
            }
            content += `<br>`;
        }
        content += `</div>`;
        
        tooltip.innerHTML = content;
        tooltip.classList.remove('hidden');
        
        const rect = tooltip.getBoundingClientRect();
        let left = event.pageX + 10;
        let top = event.pageY + 10;
        
        if (left + rect.width > window.innerWidth) {
            left = event.pageX - rect.width - 10;
        }
        if (top + rect.height > window.innerHeight) {
            top = event.pageY - rect.height - 10;
        }
        
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }

    _hideTooltip() {
        const tooltip = document.getElementById('tooltip');
        tooltip.classList.add('hidden');
    }

    update(state) {
        const graph = this._buildGraph(state);

        const newNodeIds = new Set(graph.nodes.map(n => n.id));
        const existingNodeIds = new Set(this.nodes.map(n => n.id));

        [...existingNodeIds].filter(id => !newNodeIds.has(id)).forEach(id => {
            this.g.selectAll(`.node`).filter(d => d.id === id).remove();
        });

        this.nodes = graph.nodes;
        this.edges = graph.edges;
        this.conditionalEdges = graph.conditionalEdges || [];
        this.backtrackEdges = graph.backtrackEdges;

        this._calculateLayout(graph);

        const nodeMap = new Map(this.nodes.map(n => [n.id, n]));

        this.g.selectAll('.node')
            .data(this.nodes, d => d.id)
            .attr('class', d => `node node-${d.status.toLowerCase()} node-type-${d.type.toLowerCase()}`)
            .attr('transform', d => `translate(${d.x - this.nodeWidth / 2}, ${d.y - this.nodeHeight / 2})`);

        this.g.selectAll('.node').select('rect')
            .attr('fill', d => this._getNodeColor(d.status))
            .attr('rx', d => this._getNodeRx(d.type))
            .attr('ry', d => this._getNodeRx(d.type));

        this.g.selectAll('.node').selectAll('text:nth-child(2)')
            .text(d => d.id.length > 18 ? d.id.substring(0, 16) + '...' : d.id);

        this.g.selectAll('.node').selectAll('text:nth-child(3)')
            .text(d => d.status);

        this.g.selectAll('.edge').remove();
        this.g.selectAll('.backtrack-edge').remove();
        this.g.selectAll('.edge-label').remove();

        const edgesGroup = this.g.select('.edges') || this.g.append('g').attr('class', 'edges');
        const conditionalGroup = this.g.select('.conditional-edges') || this.g.append('g').attr('class', 'conditional-edges');
        const backtrackGroup = this.g.select('.backtrack-edges') || this.g.append('g').attr('class', 'backtrack-edges');
        const labelsGroup = this.g.select('.edge-labels') || this.g.append('g').attr('class', 'edge-labels');

        this.edges.forEach(edge => {
            const s = nodeMap.get(edge.source);
            const t = nodeMap.get(edge.target);
            if (!s || !t) return;
            const isRunning = s.status === 'RUNNING' || t.status === 'RUNNING';
            edgesGroup.append('path')
                .attr('class', `edge ${isRunning ? 'edge-running' : ''}`)
                .attr('d', this._createRoutedPath(edge))
                .attr('marker-end', isRunning ? 'url(#arrowhead-running)' : 'url(#arrowhead)');
        });

        this.conditionalEdges.forEach(edge => {
            const s = nodeMap.get(edge.source);
            const t = nodeMap.get(edge.target);
            if (!s || !t) return;
            conditionalGroup.append('path')
                .attr('class', 'edge edge-conditional')
                .attr('d', this._createRoutedPath(edge))
                .attr('marker-end', 'url(#arrowhead-conditional)');
            if (edge.label) {
                const pos = this._edgeLabelPos(edge);
                labelsGroup.append('text')
                    .attr('x', pos.x).attr('y', pos.y)
                    .attr('class', 'edge-label').attr('text-anchor', 'middle')
                    .text(edge.label);
            }
        });

        this.backtrackEdges.forEach(edge => {
            const s = nodeMap.get(edge.source);
            const t = nodeMap.get(edge.target);
            if (!s || !t) return;
            backtrackGroup.append('path')
                .attr('class', 'backtrack-edge')
                .attr('d', this._createBacktrackPath(s, t))
                .attr('marker-end', 'url(#arrowhead-backtrack)');
            if (edge.label) {
                const cp = this._backtrackControlPoint(s, t);
                labelsGroup.append('text')
                    .attr('x', cp.x).attr('y', cp.y - 8)
                    .attr('class', 'edge-label edge-label-backtrack')
                    .attr('text-anchor', 'middle')
                    .text(edge.label);
            }
        });
    }

    clear() {
        this.g.selectAll('*').remove();
        this.nodes = [];
        this.edges = [];
        this.backtrackEdges = [];
    }

    zoomToFit() {
        if (!this.nodes || this.nodes.length === 0) return;

        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        this.nodes.forEach(node => {
            minX = Math.min(minX, node.x - this.nodeWidth / 2);
            maxX = Math.max(maxX, node.x + this.nodeWidth / 2);
            minY = Math.min(minY, node.y - this.nodeHeight / 2);
            maxY = Math.max(maxY, node.y + this.nodeHeight / 2);
        });

        const padding = 50;
        const graphWidth = maxX - minX + padding * 2;
        const graphHeight = maxY - minY + padding * 2;

        const scaleX = this.width / graphWidth;
        const scaleY = this.height / graphHeight;
        const scale = Math.min(scaleX, scaleY, 2);

        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;

        const transform = d3.zoomIdentity
            .translate(this.width / 2, this.height / 2)
            .scale(scale)
            .translate(-centerX, -centerY);

        this.svg.transition()
            .duration(500)
            .call(this.zoom.transform, transform);
    }

    zoomIn() {
        this.svg.transition().duration(300).call(this.zoom.scaleBy, 1.3);
    }

    zoomOut() {
        this.svg.transition().duration(300).call(this.zoom.scaleBy, 0.7);
    }
}
