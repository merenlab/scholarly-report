
            function createNetwork(data, containerId) {
                console.log("Creating network with data:", data);

                // Set up dimensions and SVG
                const container = document.getElementById(containerId);
                if (!container) {
                    console.error("Container not found:", containerId);
                    return;
                }

                const width = container.offsetWidth;
                const height = container.offsetHeight;

                // Add padding to keep nodes away from edges
                const padding = 50;  // Added padding value

                // Check if data is valid
                if (!data || !data.nodes || !data.links || data.nodes.length === 0) {
                    console.error("Invalid data for network visualization", data);
                    container.innerHTML = '<p style="color:red">Invalid data for network visualization</p>';
                    return;
                }

                console.log(`Creating network with ${data.nodes.length} nodes and ${data.links.length} links`);

                // Clear any existing content
                container.innerHTML = '';

                // Create SVG element
                const svg = d3.select(container).append("svg")
                    .attr("width", width)
                    .attr("height", height);

                // Create tooltip
                const tooltip = d3.select("body").append("div")
                    .attr("class", "tooltip")
                    .style("opacity", 0);

                // Add a weak positioning force for unconnected nodes
                // This will help keep them closer to the center
                const positioning = d3.forceRadial(Math.min(width, height) * 0.3, width / 2, height / 2)
                    .strength(node => {
                        // Apply stronger positioning for isolated nodes
                        return getNodeConnections(node, data.links) === 0 ? 0.2 : 0.01;
                    });

                // Create a force simulation with modified parameters
                const simulation = d3.forceSimulation(data.nodes)
                    .force("link", d3.forceLink(data.links).id(d => d.id).distance(100))
                    .force("charge", d3.forceManyBody().strength(-300))
                    .force("center", d3.forceCenter(width / 2, height / 2))
                    .force("collision", d3.forceCollide().radius(d => computeNodeRadius(d) + 15))  // Increased collision radius
                    .force("positioning", positioning);  // Added positioning force

                // Create the links
                const link = svg.append("g")
                    .selectAll("line")
                    .data(data.links)
                    .enter().append("line")
                    .attr("stroke", "#999")
                    .attr("stroke-opacity", 0.6)
                    .attr("stroke-width", d => Math.sqrt(d.weight) * 1.5);

                // Create the nodes
                const node = svg.append("g")
                    .selectAll("circle")
                    .data(data.nodes)
                    .enter().append("circle")
                    .attr("r", computeNodeRadius)
                    .attr("fill", d => colorByMetric(d))
                    .call(drag(simulation))
                    .on("mouseover", function(event, d) {
                        tooltip.transition()
                            .duration(200)
                            .style("opacity", .9);
                        tooltip.html(`<strong>${d.name}</strong><br>
                                    Publications: ${d.publications}<br>
                                    Citations: ${d.citations}<br>
                                    h-index: ${d.h_index}`)
                            .style("left", (event.pageX + 10) + "px")
                            .style("top", (event.pageY - 28) + "px");
                    })
                    .on("mouseout", function() {
                        tooltip.transition()
                            .duration(500)
                            .style("opacity", 0);
                    })
                    .on("click", function(event, d) {
                        window.location.href = `authors/${d.id}.html`;
                    });

                // Add node labels
                const label = svg.append("g")
                    .selectAll("text")
                    .data(data.nodes)
                    .enter().append("text")
                    .attr("font-size", 12)
                    .attr("dx", d => computeNodeRadius(d) + 5)  // Position label based on node size
                    .attr("dy", ".35em")
                    .text(d => d.name)
                    .style("pointer-events", "none");

                // Add simulation ticking with boundary constraints
                simulation.on("tick", () => {
                    link
                        .attr("x1", d => d.source.x)
                        .attr("y1", d => d.source.y)
                        .attr("x2", d => d.target.x)
                        .attr("y2", d => d.target.y);

                    // Constrain nodes within padding
                    node
                        .attr("cx", d => d.x = Math.max(padding + computeNodeRadius(d),
                                            Math.min(width - padding - computeNodeRadius(d), d.x)))
                        .attr("cy", d => d.y = Math.max(padding + computeNodeRadius(d),
                                            Math.min(height - padding - computeNodeRadius(d), d.y)));

                    // Position labels with the node
                    label
                        .attr("x", d => d.x)
                        .attr("y", d => d.y);
                });

                // Helper function to compute node radius based on publications
                function computeNodeRadius(d) {
                    return Math.max(5, Math.min(25, 5 + Math.sqrt(d.publications) * 2));
                }

                // Helper function to color nodes based on citations
                function colorByMetric(d) {
                    const colorScale = d3.scaleSequential(d3.interpolateBlues)
                        .domain([0, d3.max(data.nodes, n => n.h_index || 0) || 10]);
                    return colorScale(d.h_index || 0);
                }

                // Helper function to count connections for a node
                function getNodeConnections(node, links) {
                    return links.filter(link =>
                        link.source.id === node.id || link.target.id === node.id
                    ).length;
                }

                // Helper function for drag behavior
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
            }
        