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

        // Container for all zoomable elements
        const g = svg.append("g");

        // Add Zoom capabilities
        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => {
                g.attr("transform", event.transform);
            });
        
        svg.call(zoom);

        const simulation = d3.forceSimulation(graph.nodes)
            .force("link", d3.forceLink(graph.links).id(d => d.id).distance(150))
            .force("charge", d3.forceManyBody().strength(-500))
            .force("center", d3.forceCenter(width / 2, height / 2));

        // Draw Links
        const link = g.append("g")
            .attr("stroke", "var(--border)")
            .attr("stroke-opacity", 0.6)
            .selectAll("line")
            .data(graph.links)
            .join("line")
            .attr("stroke-width", 2);

        // Map groups to colors safely
        const color = d3.scaleOrdinal(d3.schemeCategory10);

        // Map groups to emoji icons
        const iconMap = {
            "Character": "👤",
            "Location": "🏰",
            "Item": "🗡️",
            "Faction": "🛡️",
            "Event": "🔥",
            "Species": "🐺"
        };

        // Draw Node Groups
        const node = g.append("g")
            .selectAll("g")
            .data(graph.nodes)
            .join("g")
            .call(drag(simulation));

        // Background Circle
        node.append("circle")
            .attr("r", 16)
            .attr("fill", d => color(d.group))
            .attr("stroke", "#fff")
            .attr("stroke-width", 2)
            .style("cursor", "pointer");

        // Node Icon
        node.append("text")
            .text(d => iconMap[d.group] || "📄")
            .attr("font-size", "16px")
            .attr("text-anchor", "middle")
            .attr("dy", "5px")
            .style("pointer-events", "none");

        // Text Label
        node.append("text")
            .text(d => d.id)
            .attr("font-size", "12px")
            .attr("fill", "var(--text-color)")
            .attr("dx", 22)
            .attr("dy", 4)
            .style("pointer-events", "none")
            .style("text-shadow", "1px 1px 2px var(--bg-color)"); // Make text readable over links

        node.append("title")
            .text(d => `${d.id} (${d.group})`);

        node.on("dblclick", (event, d) => {
            event.stopPropagation();
            // Check if we are in a popup window
            if (window.opener && window.opener.loadEntityIntoEditor) {
                window.opener.loadEntityIntoEditor(d.id);
            } else if (window.loadEntityIntoEditor) {
                window.loadEntityIntoEditor(d.id);
            }
        });

        // Cache for list view
        window.allNodes = graph.nodes;
        if (document.getElementById('list-container') && document.getElementById('list-container').style.display === 'flex' && window.renderList) {
            window.renderList();
        }

        simulation.on("tick", () => {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            // Move the entire node group using translate instead of updating cx/cy
            node.attr("transform", d => `translate(${d.x},${d.y})`);
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
