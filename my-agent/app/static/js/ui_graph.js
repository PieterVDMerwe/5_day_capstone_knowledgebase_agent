// Step 5.4: D3 Network Graph Visualization
async function loadGraph() {
    try {
        const res = await fetch('/api/graph');
        const data = await res.json();
        const graph = data.data;

        const container = document.getElementById('graph-container');
        container.innerHTML = ''; // Clear existing
        
        const placeholder = document.querySelector('#graph-panel .placeholder-text');
        if (placeholder) placeholder.style.display = 'none';

        const width = container.clientWidth;
        const height = container.clientHeight || window.innerHeight - 60; // 60 for header offset

        const svg = d3.select("#graph-container")
            .append("svg")
            .attr("width", width)
            .attr("height", height);

        const simulation = d3.forceSimulation(graph.nodes)
            .force("link", d3.forceLink(graph.links).id(d => d.id).distance(120))
            .force("charge", d3.forceManyBody().strength(-400))
            .force("center", d3.forceCenter(width / 2, height / 2));

        const link = svg.append("g")
            .attr("stroke", "var(--border)")
            .attr("stroke-opacity", 0.6)
            .selectAll("line")
            .data(graph.links)
            .join("line")
            .attr("stroke-width", 2);

        // Map groups to colors safely
        const color = d3.scaleOrdinal(d3.schemeCategory10);

        const node = svg.append("g")
            .attr("stroke", "#fff")
            .attr("stroke-width", 1.5)
            .selectAll("circle")
            .data(graph.nodes)
            .join("circle")
            .attr("r", 10)
            .attr("fill", d => color(d.group))
            .call(drag(simulation));

        node.append("title")
            .text(d => `${d.id} (${d.group})`);

        const labels = svg.append("g")
            .selectAll("text")
            .data(graph.nodes)
            .join("text")
            .text(d => d.id)
            .attr("font-size", "11px")
            .attr("fill", "var(--text-muted)")
            .attr("dx", 15)
            .attr("dy", 4)
            .style("pointer-events", "none");

        simulation.on("tick", () => {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node
                .attr("cx", d => d.x)
                .attr("cy", d => d.y);
                
            labels
                .attr("x", d => d.x)
                .attr("y", d => d.y);
        });

        function drag(simulation) {
            function dragstarted(event) {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                event.subject.fx = event.subject.x;
                event.subject.fy = event.subject.y;
            }
            function dragged(event) {
                event.subject.fx = event.x;
                event.subject.fy = event.y;
            }
            function dragended(event) {
                if (!event.active) simulation.alphaTarget(0);
                event.subject.fx = null;
                event.subject.fy = null;
            }
            return d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended);
        }
    } catch (err) {
        console.error("Failed to load graph:", err);
    }
}

// Global exposure for UI state to trigger reloads
window.loadGraph = loadGraph;

// Initial load
document.addEventListener("DOMContentLoaded", loadGraph);
window.addEventListener('resize', loadGraph);
