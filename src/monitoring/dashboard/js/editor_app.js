import { eventBus } from './event_bus.js';
import { SessionManager } from './session_manager.js';
import { TabManager } from './tab_manager.js';
import { AgentCatalog } from './agent_catalog.js';
import { EditorDAGRenderer } from './dag_editor.js';
import { ParamEditor } from './param_editor.js';
import { ValidationEngine } from './validation_engine.js';
import { PipelineRunner } from './pipeline_runner.js';
import { APIClient } from './api_client.js';

export class EditorApp {
    constructor() {
        this.apiClient = new APIClient('');
        this.sessionManager = null;
        this.tabManager = null;
        this.agentCatalog = null;
        this.dagRenderer = null;
        this.paramEditor = null;
        this.validationEngine = null;
        this.pipelineRunner = null;
        this._subscriptions = [];
    }

    async init() {
        this.agentCatalog = new AgentCatalog('#agent-catalog');
        this.dagRenderer = new EditorDAGRenderer('#editor-dag-container');
        this.paramEditor = new ParamEditor('#param-panel');
        this.validationEngine = new ValidationEngine();
        this.pipelineRunner = new PipelineRunner(this.apiClient);

        this._wireEventBus();

        await this.agentCatalog.load();

        this.validationEngine.moduleCatalog = this.agentCatalog.catalog;

        this._setupToolbar();

        eventBus.on('mode:editor-activated', () => {
            this.dagRenderer.init();
        });
    }

    _wireEventBus() {
        this._subscriptions.push(
            eventBus.on('editor:node-double-clicked', (data) => {
                if (this.dagRenderer.graph && this.dagRenderer.graph.nodes) {
                    const node = this.dagRenderer.graph.nodes.get(data.nodeId);
                    if (node) {
                        this.paramEditor.show(node);
                    }
                }
            })
        );

        this._subscriptions.push(
            eventBus.on('editor:graph-changed', () => {
                if (this.dagRenderer.graph) {
                    const result = this.validationEngine.validate(this.dagRenderer.graph);
                    this._updateValidationStatus(result);
                }
            })
        );

        this._subscriptions.push(
            eventBus.on('node:config-changed', () => {
                if (this.dagRenderer.graph) {
                    const result = this.validationEngine.validate(this.dagRenderer.graph);
                    this._updateValidationStatus(result);
                }
            })
        );

        this._subscriptions.push(
            eventBus.on('pipeline:run-started', () => {
                this._setRunStatus('running');
            })
        );
    }

    _setupToolbar() {
        const validateBtn = document.getElementById('btn-validate');
        if (validateBtn) {
            validateBtn.addEventListener('click', () => {
                if (this.dagRenderer.graph) {
                    const result = this.validationEngine.validate(this.dagRenderer.graph);
                    this._updateValidationStatus(result);
                }
            });
        }

        const runBtn = document.getElementById('btn-run');
        if (runBtn) {
            runBtn.addEventListener('click', () => {
                if (this.dagRenderer.graph) {
                    this.pipelineRunner.submitPipeline(this.dagRenderer.graph);
                }
            });
        }

        const exportBtn = document.getElementById('btn-export');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => {
                this._exportYaml();
            });
        }

        const importBtn = document.getElementById('btn-import');
        const yamlInput = document.getElementById('yaml-file-input');
        if (importBtn && yamlInput) {
            importBtn.addEventListener('click', () => yamlInput.click());
            yamlInput.addEventListener('change', (e) => this._importYaml(e));
        }
    }

    _exportYaml() {
        if (!this.dagRenderer.graph) return;
        const dict = this.dagRenderer.graph.toDict();
        const jsonStr = JSON.stringify(dict, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${dict.name || 'pipeline'}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }

    _importYaml(event) {
        const file = event.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const data = JSON.parse(e.target.result);
                if (this.dagRenderer.graph) {
                    this.dagRenderer.graph.fromDict(data);
                    this.dagRenderer.render(data);
                    eventBus.emit('editor:graph-changed', { graph: this.dagRenderer.graph });
                }
            } catch (err) {
                console.error('Import failed:', err);
            }
        };
        reader.readAsText(file);
        event.target.value = '';
    }

    _updateValidationStatus(result) {
        const statusEl = document.getElementById('validation-status');
        if (!statusEl) return;

        if (result.valid) {
            statusEl.className = 'validation-status valid';
            statusEl.textContent = `Valid (${result.warnings.length} warnings)`;
        } else {
            statusEl.className = 'validation-status invalid';
            statusEl.textContent = `Invalid (${result.errors.length} errors)`;
        }
    }

    _setRunStatus(status) {
        const statusEl = document.getElementById('validation-status');
        if (!statusEl) return;
        const labels = { running: 'Running...', submitted: 'Submitted', error: 'Error' };
        statusEl.textContent = labels[status] || status;
    }

    destroy() {
        this._subscriptions.forEach(unsub => unsub());
        this._subscriptions = [];
        if (this.sessionManager) this.sessionManager.destroy();
    }
}
