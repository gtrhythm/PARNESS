export class APIClient {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
    }

    async getHealth() {
        const response = await fetch(`${this.baseURL}/health`);
        if (!response.ok) {
            throw new Error(`Health check failed: ${response.status}`);
        }
        return response.json();
    }

    async getDagStatuses() {
        const response = await fetch(`${this.baseURL}/api/dag/status`);
        if (!response.ok) {
            throw new Error(`Failed to get DAG statuses: ${response.status}`);
        }
        return response.json();
    }

    async getDagStatus(sessionId) {
        const response = await fetch(`${this.baseURL}/api/dag/status/${sessionId}`);
        if (!response.ok) {
            if (response.status === 404) {
                return null;
            }
            throw new Error(`Failed to get DAG status: ${response.status}`);
        }
        return response.json();
    }

    async getNodeStatus(sessionId, nodeId) {
        const response = await fetch(`${this.baseURL}/api/dag/nodes/${sessionId}/${nodeId}`);
        if (!response.ok) {
            if (response.status === 404) {
                return null;
            }
            throw new Error(`Failed to get node status: ${response.status}`);
        }
        return response.json();
    }

    async getGraphs() {
        const response = await fetch(`${this.baseURL}/api/dag/graphs`);
        if (!response.ok) {
            throw new Error(`Failed to get graphs: ${response.status}`);
        }
        return response.json();
    }

    createEventSource(sessionId) {
        return new EventSource(`${this.baseURL}/api/dag/events/${sessionId}`);
    }

    async getModules() {
        const response = await fetch(`${this.baseURL}/api/modules`);
        if (!response.ok) throw new Error(`Failed to get modules: ${response.status}`);
        return response.json();
    }

    async getModuleDetail(moduleName) {
        const response = await fetch(`${this.baseURL}/api/modules/${moduleName}`);
        if (!response.ok) {
            if (response.status === 404) return null;
            throw new Error(`Failed to get module detail: ${response.status}`);
        }
        return response.json();
    }

    async validatePipeline(pipelineDef) {
        const response = await fetch(`${this.baseURL}/api/pipeline/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pipelineDef),
        });
        if (!response.ok) throw new Error(`Validation failed: ${response.status}`);
        return response.json();
    }

    async runPipeline(pipelineDef) {
        const response = await fetch(`${this.baseURL}/api/pipeline/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pipelineDef),
        });
        if (!response.ok) throw new Error(`Run failed: ${response.status}`);
        return response.json();
    }

    async getTemplates() {
        const response = await fetch(`${this.baseURL}/api/pipeline/templates`);
        if (!response.ok) throw new Error(`Failed to get templates: ${response.status}`);
        return response.json();
    }

    async getTemplate(filename) {
        const response = await fetch(`${this.baseURL}/api/pipeline/templates/${filename}`);
        if (!response.ok) {
            if (response.status === 404) return null;
            throw new Error(`Failed to get template: ${response.status}`);
        }
        return response.json();
    }

    async saveTemplate(filename, pipelineDef) {
        const response = await fetch(`${this.baseURL}/api/pipeline/templates`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename, pipeline: pipelineDef }),
        });
        if (!response.ok) throw new Error(`Failed to save template: ${response.status}`);
        return response.json();
    }
}
