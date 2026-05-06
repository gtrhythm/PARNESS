import { eventBus } from './event_bus.js';

export class AgentCatalog {
    constructor(containerSelector) {
        this.container = document.querySelector(containerSelector);
        this.modules = [];
        this.catalog = new Map();
        this.searchInput = document.getElementById('agent-search');
        this.catalogList = document.getElementById('agent-list');
        this._setupSearch();
    }

    _setupSearch() {
        if (this.searchInput) {
            this.searchInput.addEventListener('input', () => this._render(this.searchInput.value));
        }
    }

    async load() {
        try {
            const response = await fetch('/api/modules');
            if (!response.ok) throw new Error(`Failed to load modules: ${response.status}`);
            this.modules = await response.json();
            this._buildCatalog();
            this._render();
        } catch (e) {
            console.error('Failed to load agent catalog:', e);
        }
    }

    _buildCatalog() {
        this.catalog.clear();
        this.modules.forEach(mod => {
            const tags = mod.tags && mod.tags.length > 0 ? mod.tags : ['uncategorized'];
            const primaryTag = tags[0];
            if (!this.catalog.has(primaryTag)) this.catalog.set(primaryTag, []);
            this.catalog.get(primaryTag).push(mod);
        });
    }

    _render(filterText = '') {
        if (!this.catalogList) return;
        this.catalogList.innerHTML = '';
        const lowerFilter = filterText.toLowerCase();

        const tagOrder = ['core', 'crawler', 'parser', 'agent', 'filter', 'experiment',
                          'flow_control', 'knowledge_base', 'export', 'uncategorized'];

        const sortedTags = [...this.catalog.keys()].sort((a, b) => {
            const ai = tagOrder.indexOf(a);
            const bi = tagOrder.indexOf(b);
            return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
        });

        sortedTags.forEach(tag => {
            const mods = this.catalog.get(tag);
            const filtered = mods.filter(m =>
                !lowerFilter ||
                m.name.toLowerCase().includes(lowerFilter) ||
                m.display_name.toLowerCase().includes(lowerFilter) ||
                (m.description || '').toLowerCase().includes(lowerFilter)
            );
            if (filtered.length === 0) return;

            const groupTitle = document.createElement('div');
            groupTitle.className = 'agent-group-title';
            groupTitle.textContent = `${tag} (${filtered.length})`;
            this.catalogList.appendChild(groupTitle);

            filtered.forEach(mod => {
                const card = document.createElement('div');
                card.className = 'agent-card';
                card.draggable = true;
                card.dataset.moduleName = mod.name;

                const nameEl = document.createElement('div');
                nameEl.className = 'agent-card-name';
                nameEl.textContent = mod.display_name || mod.name;

                const descEl = document.createElement('div');
                descEl.className = 'agent-card-desc';
                descEl.textContent = mod.description || '';

                const tagsEl = document.createElement('div');
                tagsEl.className = 'agent-card-tags';
                (mod.tags || []).forEach(t => {
                    const tagSpan = document.createElement('span');
                    tagSpan.className = 'agent-tag';
                    tagSpan.textContent = t;
                    tagsEl.appendChild(tagSpan);
                });

                card.appendChild(nameEl);
                card.appendChild(descEl);
                card.appendChild(tagsEl);

                card.addEventListener('click', () => this._toggleDetail(mod.name, card));
                card.addEventListener('dragstart', (e) => this._onDragStart(e, mod));
                this.catalogList.appendChild(card);
            });
        });
    }

    async _toggleDetail(moduleName, cardEl) {
        const existing = cardEl.querySelector('.agent-card-detail');
        if (existing) { existing.remove(); return; }

        try {
            const response = await fetch(`/api/modules/${moduleName}`);
            if (!response.ok) return;
            const detail = await response.json();

            const detailEl = document.createElement('div');
            detailEl.className = 'agent-card-detail';

            const inputKeys = Object.keys(detail.input_schema || {});
            const outputKeys = Object.keys(detail.output_schema || {});

            let html = '';
            if (inputKeys.length > 0) {
                html += '<div style="margin-bottom:4px"><strong>Input:</strong></div>';
                inputKeys.forEach(k => {
                    html += `<div class="schema-field">${k}: ${detail.input_schema[k]}</div>`;
                });
            }
            if (outputKeys.length > 0) {
                html += '<div style="margin:4px 0"><strong>Output:</strong></div>';
                outputKeys.forEach(k => {
                    html += `<div class="schema-field">${k}: ${detail.output_schema[k]}</div>`;
                });
            }
            if (detail.upstream_compatible && detail.upstream_compatible.length > 0) {
                html += `<div style="margin-top:4px"><strong>Upstream:</strong> ${detail.upstream_compatible.join(', ')}</div>`;
            }
            if (detail.downstream_compatible && detail.downstream_compatible.length > 0) {
                html += `<div style="margin-top:2px"><strong>Downstream:</strong> ${detail.downstream_compatible.join(', ')}</div>`;
            }
            if (detail.depends_on && detail.depends_on.length > 0) {
                html += `<div style="margin-top:2px"><strong>Depends:</strong> ${detail.depends_on.join(', ')}</div>`;
            }

            detailEl.innerHTML = html;
            cardEl.appendChild(detailEl);
        } catch (e) {
            console.error('Failed to load module detail:', e);
        }
    }

    _onDragStart(event, mod) {
        event.dataTransfer.setData('application/json', JSON.stringify({
            type: 'catalog-module',
            module: mod
        }));
        event.dataTransfer.effectAllowed = 'copy';
        eventBus.emit('catalog:drag-start', { module: mod });
    }
}
