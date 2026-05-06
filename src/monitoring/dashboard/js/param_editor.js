import { eventBus } from './event_bus.js';

export class ParamEditor {
    constructor(containerSelector) {
        this.panel = document.querySelector(containerSelector);
        this.panelTitle = document.getElementById('param-panel-title');
        this.panelContent = document.getElementById('param-panel-content');
        this.closeBtn = document.getElementById('close-param-panel');
        this.currentNodeId = null;
        this.currentNode = null;
        this._subscriptions = [];
        this._setupSubscriptions();
        this._setupClose();
    }

    _setupSubscriptions() {
        this._subscriptions.push(
            eventBus.on('editor:node-double-clicked', (data) => {
                this.currentNodeId = data.nodeId;
            })
        );
    }

    _setupClose() {
        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => this.hide());
        }
    }

    show(node) {
        this.currentNode = node;
        this.currentNodeId = node.id;
        this._renderForm(node);
        if (this.panel) this.panel.style.display = 'block';
    }

    hide() {
        this.currentNode = null;
        this.currentNodeId = null;
        if (this.panel) this.panel.style.display = 'none';
    }

    _renderForm(node) {
        if (!this.panelContent) return;
        this.panelContent.innerHTML = '';

        if (this.panelTitle) {
            this.panelTitle.textContent = node.id || 'Properties';
        }

        this._renderSection('Basic Config', {
            'Node ID': node.id || '',
            'Module': node.moduleName || '',
            'Timeout': node.timeout || 0,
        }, 'basic');

        this._renderSection('Input Mapping', node.inputMapping || node.input_mapping || {}, 'input_mapping');
        this._renderSection('Output Mapping', node.outputMapping || node.output_mapping || {}, 'output_mapping');
        this._renderSection('Routes', node.routes || {}, 'routes');
        this._renderSection('Params', node.params || {}, 'params');

        const applyBtn = document.createElement('button');
        applyBtn.className = 'btn-apply';
        applyBtn.textContent = 'Apply';
        applyBtn.addEventListener('click', () => {
            eventBus.emit('node:config-changed', {
                nodeId: this.currentNodeId,
                config: this._collectValues()
            });
        });
        this.panelContent.appendChild(applyBtn);
    }

    _renderSection(title, fields, sectionKey) {
        const keys = Object.keys(fields);
        if (keys.length === 0 && sectionKey !== 'input_mapping' && sectionKey !== 'routes') return;

        const section = document.createElement('div');
        section.className = 'param-section';

        const sectionTitle = document.createElement('div');
        sectionTitle.className = 'param-section-title';
        sectionTitle.textContent = title;
        section.appendChild(sectionTitle);

        keys.forEach(key => {
            const value = fields[key];
            const row = document.createElement('div');
            row.className = 'param-row';

            const label = document.createElement('span');
            label.className = 'param-label';
            label.textContent = key;

            const input = document.createElement('input');
            input.className = 'param-input';
            input.type = 'text';
            input.value = this._formatValue(value);
            input.dataset.section = sectionKey;
            input.dataset.key = key;

            row.appendChild(label);
            row.appendChild(input);
            section.appendChild(row);
        });

        if (sectionKey === 'input_mapping' || sectionKey === 'output_mapping' || sectionKey === 'routes' || sectionKey === 'params') {
            const addBtn = document.createElement('button');
            addBtn.className = 'btn-add-mapping';
            addBtn.textContent = `+ Add ${sectionKey === 'routes' ? 'route' : 'mapping'}`;
            addBtn.addEventListener('click', () => {
                const row = document.createElement('div');
                row.className = 'param-row';

                const keyInput = document.createElement('input');
                keyInput.className = 'param-input';
                keyInput.type = 'text';
                keyInput.placeholder = 'key';
                keyInput.dataset.section = sectionKey;
                keyInput.dataset.key = '__new__';

                const valInput = document.createElement('input');
                valInput.className = 'param-input';
                valInput.type = 'text';
                valInput.placeholder = 'value';

                row.appendChild(keyInput);
                row.appendChild(valInput);
                section.insertBefore(row, addBtn);
            });
            section.appendChild(addBtn);
        }

        this.panelContent.appendChild(section);
    }

    _formatValue(value) {
        if (value === null || value === undefined) return '';
        if (typeof value === 'object') return JSON.stringify(value);
        return String(value);
    }

    _collectValues() {
        if (!this.panelContent) return {};
        const result = {};
        const inputs = this.panelContent.querySelectorAll('.param-input');
        inputs.forEach(input => {
            const section = input.dataset.section;
            const key = input.dataset.key;
            if (!section || !key) return;
            if (!result[section]) result[section] = {};
            let value = input.value;
            try { value = JSON.parse(value); } catch {}
            result[section][key] = value;
        });
        return result;
    }

    destroy() {
        this._subscriptions.forEach(unsub => unsub());
        this._subscriptions = [];
    }
}
