export class NodeDetailPanel {
    constructor(panelSelector) {
        this.panel = document.querySelector(panelSelector);
        if (!this.panel) {
            throw new Error(`Panel ${panelSelector} not found`);
        }

        this.currentNodeId = null;
        this._setupCollapsibles();
    }

    _setupCollapsibles() {
        const collapsibles = this.panel.querySelectorAll('[data-toggle="collapse"]');
        collapsibles.forEach(header => {
            header.addEventListener('click', () => {
                const targetId = header.getAttribute('data-target');
                const content = this.panel.querySelector(targetId);
                const icon = header.querySelector('.toggle-icon');
                
                if (content.classList.contains('collapsed')) {
                    content.classList.remove('collapsed');
                    if (icon) icon.textContent = '-';
                } else {
                    content.classList.add('collapsed');
                    if (icon) icon.textContent = '+';
                }
            });
        });
    }

    show(nodeId, state) {
        this.currentNodeId = nodeId;
        this._populate(nodeId, state);
        this.panel.classList.remove('hidden');
    }

    hide() {
        this.currentNodeId = null;
        this.panel.classList.add('hidden');
    }

    update(state) {
        if (this.currentNodeId) {
            this._populate(this.currentNodeId, state);
        }
    }

    _populate(nodeId, state) {
        if (!state || !state.nodes || !state.nodes[nodeId]) {
            return;
        }

        const node = state.nodes[nodeId];

        this._setText('detail-node-id', node.node_id || nodeId);
        this._setText('detail-node-type', node.node_type || '-');
        this._setText('detail-status', node.status || '-');
        this._setStatusClass('detail-status', node.status);
        this._setText('detail-duration', node.duration_seconds ? `${node.duration_seconds.toFixed(2)}s` : '-');

        const iterationSection = document.getElementById('iteration-section');
        if (node.iteration_count !== undefined && node.iteration_count !== null) {
            iterationSection.classList.remove('hidden');
            this._setText('detail-iteration-count', node.iteration_count.toString());
            this._setText('detail-max-iterations', node.max_iterations ? node.max_iterations.toString() : '-');
            this._setText('detail-score', node.score !== undefined && node.score !== null ? node.score.toFixed(4) : '-');
            this._setText('detail-decision', node.decision || '-');
        } else {
            iterationSection.classList.add('hidden');
        }

        const historySection = document.getElementById('iteration-history-section');
        const historyList = document.getElementById('iteration-history-list');
        if (node.iteration_history && node.iteration_history.length > 0) {
            historySection.classList.remove('hidden');
            historyList.innerHTML = '';
            
            node.iteration_history.forEach((snapshot, index) => {
                const item = document.createElement('div');
                item.className = 'iteration-item';
                
                let details = `Iteration ${snapshot.iteration}`;
                if (snapshot.duration_seconds) {
                    details += ` - ${snapshot.duration_seconds.toFixed(2)}s`;
                }
                if (snapshot.score !== undefined && snapshot.score !== null) {
                    details += ` - score: ${snapshot.score.toFixed(4)}`;
                }
                if (snapshot.decision) {
                    details += ` - ${snapshot.decision}`;
                }
                
                item.innerHTML = `
                    <div class="iteration-item-header">
                        <span>${details}</span>
                    </div>
                    ${snapshot.started_at ? `<div class="iteration-item-details">Started: ${new Date(snapshot.started_at).toLocaleString()}</div>` : ''}
                    ${snapshot.completed_at ? `<div class="iteration-item-details">Completed: ${new Date(snapshot.completed_at).toLocaleString()}</div>` : ''}
                `;
                historyList.appendChild(item);
            });
        } else {
            historySection.classList.add('hidden');
        }

        const agentSection = document.getElementById('agent-progress-section');
        const agentProgressEl = document.getElementById('detail-agent-progress');
        if (node.agent_progress && Object.keys(node.agent_progress).length > 0) {
            agentSection.classList.remove('hidden');
            agentProgressEl.textContent = JSON.stringify(node.agent_progress, null, 2);
        } else {
            agentSection.classList.add('hidden');
        }

        const outputsSection = document.getElementById('outputs-section');
        const outputsEl = document.getElementById('detail-outputs');
        if (node.outputs && node.outputs.length > 0) {
            outputsSection.classList.remove('hidden');
            outputsEl.innerHTML = '';
            node.outputs.forEach(output => {
                const outputDiv = document.createElement('div');
                outputDiv.className = `agent-output output-type-${output.display_type || 'text'}`;
                outputDiv.innerHTML = this._renderOutput(output);
                outputsEl.appendChild(outputDiv);
            });
        } else {
            outputsSection.classList.add('hidden');
        }

        const errorSection = document.getElementById('error-section');
        if (node.error_message || node.error_traceback) {
            errorSection.classList.remove('hidden');
            this._setText('detail-error-message', node.error_message || '-');
            this._setText('detail-error-traceback', node.error_traceback || '-');
        } else {
            errorSection.classList.add('hidden');
        }

        this._setText('detail-depends-on', node.depends_on && node.depends_on.length > 0 
            ? node.depends_on.join(', ') 
            : '-');
    }

    _setText(selector, text) {
        const el = document.getElementById(selector);
        if (el) {
            el.textContent = text;
        }
    }

    _setStatusClass(selector, status) {
        const el = document.getElementById(selector);
        if (el) {
            el.className = 'detail-value';
            if (status) {
                el.classList.add(`status-${status.toLowerCase()}`);
            }
        }
    }

    _renderOutput(output) {
        const timestamp = output.timestamp ? new Date(output.timestamp).toLocaleString() : '';
        const header = `<div class="output-header"><span class="output-type-badge">${output.display_type || 'text'}</span><span class="output-timestamp">${timestamp}</span></div>`;
        
        let content = '';
        switch (output.display_type) {
            case 'code':
                content = `<pre class="output-content code-block">${this._escapeHtml(output.content)}</pre>`;
                break;
            case 'html':
                content = `<div class="output-content html-content">${output.content}</div>`;
                break;
            case 'json':
                try {
                    const formatted = JSON.stringify(JSON.parse(output.content), null, 2);
                    content = `<pre class="output-content json-block">${this._escapeHtml(formatted)}</pre>`;
                } catch {
                    content = `<pre class="output-content json-block">${this._escapeHtml(output.content)}</pre>`;
                }
                break;
            case 'table':
                content = `<div class="output-content table-content">${output.content}</div>`;
                break;
            case 'image':
                content = `<div class="output-content image-content"><img src="${output.content}" alt="Agent output" /></div>`;
                break;
            default:
                content = `<div class="output-content text-block">${this._escapeHtml(output.content)}</div>`;
        }
        
        return header + content;
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
