/* global d3 */

export class TimelineView {
    constructor(containerSelector) {
        this.container = document.querySelector(containerSelector);
        if (!this.container) {
            throw new Error(`Container ${containerSelector} not found`);
        }

        this.svg = d3.select('#timeline-svg');
        this.width = 0;
        this.height = 0;
        this.margin = { top: 30, right: 30, bottom: 40, left: 120 };
        this.g = null;
        this.xScale = null;
        this.yScale = null;

        this._setupSVG();
    }

    _setupSVG() {
        this.width = this.container.clientWidth;
        this.height = this.container.clientHeight;

        this.svg.attr('viewBox', `0 0 ${this.width} ${this.height}`);

        this.g = this.svg.append('g')
            .attr('transform', `translate(${this.margin.left}, ${this.margin.top})`);

        this.xScale = d3.scaleTime().range([0, this._getInnerWidth()]);
        this.yScale = d3.scaleBand().range([0, this._getInnerHeight()]).padding(0.3);
    }

    _getInnerWidth() {
        return this.width - this.margin.left - this.margin.right;
    }

    _getInnerHeight() {
        return this.height - this.margin.top - this.margin.bottom;
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

    _buildTimelineData(state) {
        if (!state || !state.nodes) {
            return [];
        }

        const nodes = state.nodes;
        const startTime = state.started_at ? new Date(state.started_at) : new Date();
        const now = new Date();

        return Object.entries(nodes).map(([nodeId, node]) => {
            const nodeStart = node.started_at ? new Date(node.started_at) : startTime;
            const nodeEnd = node.completed_at ? new Date(node.completed_at) : (node.started_at ? now : null);

            return {
                id: nodeId,
                status: node.status || 'PENDING',
                startTime: nodeStart,
                endTime: nodeEnd,
                duration: node.duration_seconds || null
            };
        }).filter(d => d.startTime);
    }

    render(state) {
        const data = this._buildTimelineData(state);

        this.g.selectAll('*').remove();

        if (data.length === 0) {
            this._renderEmpty();
            return;
        }

        const allTimes = data.flatMap(d => [d.startTime, d.endTime].filter(t => t));
        const timeExtent = d3.extent(allTimes);
        
        if (timeExtent[0] === timeExtent[1]) {
            timeExtent[0] = new Date(timeExtent[0].getTime() - 60000);
            timeExtent[1] = new Date(timeExtent[1].getTime() + 60000);
        }

        this.xScale.domain(timeExtent);

        const sortedData = [...data].sort((a, b) => {
            if (a.startTime.getTime() !== b.startTime.getTime()) {
                return a.startTime.getTime() - b.startTime.getTime();
            }
            return a.id.localeCompare(b.id);
        });

        this.yScale.domain(sortedData.map(d => d.id));

        this._renderXAxis();
        this._renderYAxis();
        this._renderBars(sortedData);
        this._renderCurrentTimeLine();
    }

    _renderEmpty() {
        this.g.append('text')
            .attr('x', this._getInnerWidth() / 2)
            .attr('y', this._getInnerHeight() / 2)
            .attr('text-anchor', 'middle')
            .attr('fill', 'var(--color-text-secondary)')
            .text('No timeline data available');
    }

    _renderXAxis() {
        const xAxis = d3.axisBottom(this.xScale)
            .ticks(8)
            .tickFormat(d3.timeFormat('%H:%M:%S'));

        this.g.append('g')
            .attr('class', 'timeline-axis x-axis')
            .attr('transform', `translate(0, ${this._getInnerHeight()})`)
            .call(xAxis);
    }

    _renderYAxis() {
        this.g.append('g')
            .attr('class', 'timeline-axis y-axis')
            .call(d3.axisLeft(this.yScale));
    }

    _renderBars(data) {
        const barHeight = this.yScale.bandwidth();

        const bars = this.g.selectAll('.timeline-bar')
            .data(data)
            .enter()
            .append('rect')
            .attr('class', 'timeline-bar')
            .attr('x', d => this.xScale(d.startTime))
            .attr('y', d => this.yScale(d.id))
            .attr('width', 0)
            .attr('height', barHeight)
            .attr('fill', d => this._getNodeColor(d.status))
            .style('cursor', 'pointer');

        bars.transition()
            .duration(500)
            .attr('width', d => {
                if (!d.endTime) {
                    const currentX = this.xScale(new Date());
                    return Math.max(0, currentX - this.xScale(d.startTime));
                }
                return Math.max(0, this.xScale(d.endTime) - this.xScale(d.startTime));
            });

        bars.on('click', (event, d) => {
            const customEvent = new CustomEvent('node-selected', {
                bubbles: true,
                detail: { nodeId: d.id }
            });
            this.container.dispatchEvent(customEvent);
        });

        bars.append('title')
            .text(d => `${d.id}\nStatus: ${d.status}${d.duration ? `\nDuration: ${d.duration.toFixed(2)}s` : ''}`);
    }

    _renderCurrentTimeLine() {
        const now = new Date();
        const x = this.xScale(now);

        if (x >= 0 && x <= this._getInnerWidth()) {
            this.g.append('line')
                .attr('class', 'current-time-line')
                .attr('x1', x)
                .attr('y1', 0)
                .attr('x2', x)
                .attr('y2', this._getInnerHeight());
        }
    }

    update(state) {
        const data = this._buildTimelineData(state);

        if (data.length === 0) {
            this.render(state);
            return;
        }

        const allTimes = data.flatMap(d => [d.startTime, d.endTime].filter(t => t));
        const timeExtent = d3.extent(allTimes);
        
        if (timeExtent[0] === timeExtent[1]) {
            timeExtent[0] = new Date(timeExtent[0].getTime() - 60000);
            timeExtent[1] = new Date(timeExtent[1].getTime() + 60000);
        }

        this.xScale.domain(timeExtent);

        const sortedData = [...data].sort((a, b) => {
            if (a.startTime.getTime() !== b.startTime.getTime()) {
                return a.startTime.getTime() - b.startTime.getTime();
            }
            return a.id.localeCompare(b.id);
        });

        this.yScale.domain(sortedData.map(d => d.id));

        this.g.selectAll('.x-axis').remove();
        this._renderXAxis();

        this.g.selectAll('.timeline-bar')
            .data(sortedData, d => d.id)
            .attr('fill', d => this._getNodeColor(d.status))
            .transition()
            .duration(300)
            .attr('x', d => this.xScale(d.startTime))
            .attr('width', d => {
                if (!d.endTime) {
                    const currentX = this.xScale(new Date());
                    return Math.max(0, currentX - this.xScale(d.startTime));
                }
                return Math.max(0, this.xScale(d.endTime) - this.xScale(d.startTime));
            });

        this.g.selectAll('.current-time-line').remove();
        this._renderCurrentTimeLine();
    }
}
