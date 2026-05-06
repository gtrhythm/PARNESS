import { eventBus } from './event_bus.js';
import { ValidationEngine } from './validation_engine.js';

export class PipelineRunner {
    constructor(apiClient) {
        this.apiClient = apiClient;
        this.validationEngine = new ValidationEngine();
    }

    async submitPipeline(editorGraph) {
        const validationResult = this.validationEngine.validate(editorGraph);
        if (!validationResult.valid) {
            eventBus.emit('pipeline:validation-failed', validationResult);
            return { success: false, errors: validationResult.errors };
        }

        const graphDict = editorGraph.toDict();

        const confirmed = window.confirm(
            `Submit pipeline with ${Object.keys(graphDict.nodes).length} nodes and ${graphDict.edges.length} edges?`
        );
        if (!confirmed) {
            return { success: false, cancelled: true };
        }

        eventBus.emit('pipeline:run-started', { graph: graphDict });

        try {
            const response = await fetch('/api/pipeline/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(graphDict)
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Pipeline submission failed: ${response.status} - ${errorText}`);
            }

            const result = await response.json();
            eventBus.emit('pipeline:run-submitted', result);
            return { success: true, data: result };
        } catch (e) {
            console.error('Pipeline submission error:', e);
            eventBus.emit('pipeline:run-error', { error: e.message });
            return { success: false, error: e.message };
        }
    }
}
