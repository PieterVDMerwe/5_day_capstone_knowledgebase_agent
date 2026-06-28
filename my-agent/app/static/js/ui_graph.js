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

        const showEmpty = document.getElementById('toggle-empty-btn') ? document.getElementById('toggle-empty-btn').checked : true;
        
        let filteredNodes = graph.nodes;
        if (!showEmpty) {
            filteredNodes = graph.nodes.filter(n => !n.is_empty);
        }
        
        const nodeIds = new Set(filteredNodes.map(n => n.id));
        const filteredLinks = graph.links.filter(l => nodeIds.has(l.source) && nodeIds.has(l.target));

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

        const simulation = d3.forceSimulation(filteredNodes)
            .force("link", d3.forceLink(filteredLinks).id(d => d.id).distance(150))
            .force("charge", d3.forceManyBody().strength(-500))
            .force("center", d3.forceCenter(width / 2, height / 2));

        // Draw Links
        const link = g.append("g")
            .attr("stroke", "var(--border)")
            .attr("stroke-opacity", 0.6)
            .selectAll("line")
            .data(filteredLinks)
            .join("line")
            .attr("stroke-width", 2);

        // Map groups to colors safely
        const color = d3.scaleOrdinal(d3.schemeCategory10);

        // Map groups to Material Symbols
        const iconMap = {
            "Character": "person",
            "Location": "castle",
            "Item": "swords",
            "Faction": "shield",
            "Event": "local_fire_department",
            "Species": "pets",
            "General": "description"
        };

        // Draw Node Groups
        const node = g.append("g")
            .selectAll("g")
            .data(filteredNodes)
            .join("g")
            .call(drag(simulation));

        // Silhouette Icon (Material Symbol as the only shape)
        node.append("text")
            .attr("class", "material-symbols-outlined")
            .text(d => iconMap[d.group] || "description")
            .attr("font-size", "28px")
            .attr("fill", d => d.is_empty ? "#888888" : "var(--accent)")
            .attr("text-anchor", "middle")
            .attr("dy", "10px") // Adjust for larger font size
            .style("opacity", d => d.is_empty ? 0.65 : 1)
            .style("cursor", "pointer");

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
document.addEventListener("DOMContentLoaded", () => {
    loadGraph();
    const toggleBtn = document.getElementById('toggle-empty-btn');
    if (toggleBtn) {
        toggleBtn.addEventListener('change', loadGraph);
    }
});
window.addEventListener('resize', loadGraph);
