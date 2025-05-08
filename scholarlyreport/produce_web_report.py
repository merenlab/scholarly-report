#!/usr/bin/env python3

import re
import sys
import json
import argparse
import pandas as pd
import networkx as nx
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

class PublicationData:
    """Handles loading and processing of publication data"""

    def __init__(self, data_dir, excluded_journals=None):
        """Initialize with the directory containing publication data"""
        self.data_dir = Path(data_dir)
        self.authors = {}  # Dictionary of author info (from _info.csv)
        self.publications = {}  # Dictionary of publications by ID
        self.author_publications = defaultdict(list)  # Publications by author
        self.coauthor_network = nx.Graph()  # Graph for co-authorship network
        self.journal_mapping = {}  # Mapping from raw journal names to standardized names

        # figure out journal names to be excluded
        self.excluded_journals = []
        if excluded_journals:
            for journal in excluded_journals:
                self.excluded_journals.append(journal.lower())
            print(f"Excluding {len(self.excluded_journals)} journals...")

    def load_data(self):
        """Load all author and publication data from the directory"""
        print(f"Loading data from {self.data_dir}")

        # Get all CSV files in the directory
        info_files = list(self.data_dir.glob("*_info.csv"))
        pub_files = list(self.data_dir.glob("*_publications.csv"))

        if not info_files or not pub_files:
            print("Error: No data files found. Looking for *_info.csv and *_publications.csv")
            return False

        print(f"Found {len(info_files)} author info files and {len(pub_files)} publication files")

        # Load author info
        for info_file in info_files:
            self._load_author_info(info_file)

        # Load publications
        for pub_file in pub_files:
            self._load_publications(pub_file)

        # Build co-authorship network
        self._build_coauthor_network()

        return True

    def _load_author_info(self, info_file):
        """Load information about a single author"""
        try:
            author_df = pd.read_csv(info_file, sep='\t')
            if not author_df.empty:
                row = author_df.iloc[0]
                scholar_id = row.get('scholar_id') or Path(info_file).stem.replace('_info', '')
                self.authors[scholar_id] = {
                    'name': row.get('name', 'Unknown'),
                    'affiliation': row.get('affiliation', 'Unknown'),
                    'total_citations': row.get('total_citations', 0),
                    'h_index': row.get('h_index', 0),
                    'i10_index': row.get('i10_index', 0),
                    'publication_count': row.get('publication_count', 0),
                    'scholar_id': scholar_id
                }
                print(f"Loaded author: {self.authors[scholar_id]['name']}")
        except Exception as e:
            print(f"Error loading author info from {info_file}: {str(e)}")

    def _standardize_journal_name(self, journal_name):
        """Standardize journal name to fix capitalization and other inconsistencies"""
        if not journal_name or pd.isna(journal_name):
            return "Unknown"

        # Remove extra whitespace
        journal_name = journal_name.strip()

        # Check if we've already standardized this journal name
        if hasattr(self, 'journal_mapping') and journal_name in self.journal_mapping:
            return self.journal_mapping[journal_name]

        # Title case the journal name (capitalize first letter of each word)
        standardized = " ".join(word.capitalize() for word in journal_name.split())

        # prettier
        standardized = standardized.replace('And', 'and').replace('Of', 'of')

        # Store in mapping for future use
        if not hasattr(self, 'journal_mapping'):
            self.journal_mapping = {}
        self.journal_mapping[journal_name] = standardized

        return standardized

    def _load_publications(self, pub_file):
        """Load publications for a single author"""
        try:
            pubs_df = pd.read_csv(pub_file, sep='\t')
            if pubs_df.empty:
                return

            scholar_id = pubs_df['scholar_id'].iloc[0]
            excluded_pubs_count = 0

            # Process each publication
            for _, pub in pubs_df.iterrows():
                # get standardized journal name here before its too late
                journal_name = self._standardize_journal_name(pub.get('journal', ''))

                # skip if this journal is in the excluded list
                if self._is_journal_to_be_excluded(journal_name):
                    excluded_pubs_count += 1
                    continue

                pub_id = self._generate_publication_id(pub)

                # Store in publications dict if not already there
                if pub_id not in self.publications:
                    self.publications[pub_id] = {
                        'title': pub['title'],
                        'authors': pub['authors'],
                        'author_list': self._parse_authors(pub['authors']),
                        'venue': pub.get('venue', ''),
                        'journal': journal_name,
                        'volume': pub.get('volume', ''),
                        'issue': pub.get('issue', ''),
                        'year': int(pub['year']) if str(pub['year']).isdigit() else 0,
                        'citations': int(pub['citations']) if str(pub['citations']).isdigit() else 0,
                        'pub_url': pub.get('pub_url', ''),
                        'author_ids': [scholar_id]  # List of author IDs from our dataset
                    }
                else:
                    # If publication already exists, add this author to it
                    if scholar_id not in self.publications[pub_id]['author_ids']:
                        self.publications[pub_id]['author_ids'].append(scholar_id)

                # Add to author-publications mapping
                self.author_publications[scholar_id].append(pub_id)

            print(f"Loaded {len(pubs_df) - excluded_pubs_count} publications for {scholar_id} (excluded {excluded_pubs_count})")

        except Exception as e:
            print(f"Error loading publications from {pub_file}: {str(e)}")


    def _is_journal_to_be_excluded(self, journal_name):
        """Check if journal should be excluded based on patterns"""
        if not journal_name or not self.excluded_journals:
            return False

        # Convert to lowercase for case-insensitive matching
        journal_lower = journal_name.lower()

        # Check if any pattern is in the journal name
        for pattern in self.excluded_journals:
            if pattern in journal_lower:
                return True

        return False


    def _generate_publication_id(self, pub):
        """Generate a unique ID for a publication based on title and year"""
        title = pub['title'].lower()
        year = str(pub['year'])
        # Create simplified title by removing common words and characters
        simple_title = re.sub(r'[^\w\s]', '', title)
        simple_title = re.sub(r'\s+', '_', simple_title)
        return f"{year}_{simple_title[:50]}"  # Limit length

    def _parse_authors(self, author_string):
        """Parse author string into a list of author names"""
        if pd.isna(author_string) or not author_string:
            return []

        # Split author string - handles both comma-separated and "and" separated lists
        authors = []
        for name in re.split(r',\s*|\s+and\s+', author_string):
            if name and len(name) > 1:  # Avoid single-letter names or empty strings
                authors.append(name.strip())
        return authors

    def _build_coauthor_network(self):
        """Build network of co-authorship relationships"""
        print("Building co-authorship network...")

        # Add all authors to the graph
        for author_id, author_data in self.authors.items():
            self.coauthor_network.add_node(
                author_id,
                name=author_data['name'],
                citations=author_data['total_citations'],
                h_index=author_data['h_index']
            )

        # Process each publication to find co-authorship relationships
        for pub_id, pub_data in self.publications.items():
            author_ids = pub_data['author_ids']

            # Only create edges if there's more than one of our authors on the paper
            if len(author_ids) > 1:
                for i in range(len(author_ids)):
                    for j in range(i+1, len(author_ids)):
                        author1 = author_ids[i]
                        author2 = author_ids[j]

                        # Add edge or increment weight if it exists
                        if self.coauthor_network.has_edge(author1, author2):
                            self.coauthor_network[author1][author2]['weight'] += 1
                            self.coauthor_network[author1][author2]['publications'].append(pub_id)
                        else:
                            self.coauthor_network.add_edge(
                                author1,
                                author2,
                                weight=1,
                                publications=[pub_id]
                            )

        print(f"Co-authorship network created with {self.coauthor_network.number_of_nodes()} nodes and {self.coauthor_network.number_of_edges()} edges")

    def get_coauthorship_data(self):
        """Convert network to format for D3.js visualization"""
        nodes = []
        for node_id in self.coauthor_network.nodes():
            author_data = self.authors.get(node_id, {})
            pub_count = len(self.author_publications.get(node_id, []))

            nodes.append({
                'id': node_id,
                'name': author_data.get('name', 'Unknown'),
                'publications': int(pub_count),  # Convert to native Python int
                'citations': int(author_data.get('total_citations', 0)),  # Convert to native Python int
                'h_index': int(author_data.get('h_index', 0))  # Convert to native Python int
            })

        links = []
        for source, target, data in self.coauthor_network.edges(data=True):
            links.append({
                'source': source,
                'target': target,
                'weight': int(data['weight']),  # Convert to native Python int
                'publications': data['publications']
            })

        return {'nodes': nodes, 'links': links}

    def get_journal_stats(self):
        """Get publication statistics by journal"""
        journal_counts = Counter()
        journal_citations = Counter()

        for pub in self.publications.values():
            journal = pub.get('journal', 'Unknown')
            if journal:
                journal_counts[journal] += 1
                journal_citations[journal] += int(pub.get('citations', 0))

        # Calculate average citations per paper
        journal_stats = []
        for journal, count in journal_counts.most_common():
            journal_stats.append({
                'journal': journal,
                'publications': int(count),  # Convert to native Python int
                'citations': int(journal_citations[journal]),  # Convert to native Python int
                'avg_citations': float(round(journal_citations[journal] / count, 1))  # Convert to native Python float
            })

        return journal_stats

class HTMLGenerator:
    """Generates HTML content for the scholarly network visualization"""

    def __init__(self, data, output_dir, institute_name=None):
        """Initialize with publication data and output directory"""
        self.data = data
        self.institute_name = institute_name
        self.output_dir = Path(output_dir)
        self.authors_dir = self.output_dir / "authors"
        self.js_dir = self.output_dir / "js"
        self.css_dir = self.output_dir / "css"
        self.data_dir = self.output_dir / "data"

    def generate_site(self):
        """Generate the complete website"""
        print(f"Generating site in {self.output_dir}")

        # Create directory structure
        self._create_directories()

        # Generate the static assets (CSS, JS, etc.)
        self._generate_assets()

        # Generate data files
        self._generate_data_files()

        # Generate index page with network visualization
        self._generate_index_page()

        # Generate individual author pages
        self._generate_author_pages()

        # Generate journal analysis page
        self._generate_journal_page()

        print("Website generation complete!")

    def _create_directories(self):
        """Create the necessary directory structure"""
        directories = [
            self.output_dir,
            self.authors_dir,
            self.js_dir,
            self.css_dir,
            self.data_dir
        ]

        for directory in directories:
            directory.mkdir(exist_ok=True, parents=True)

        print(f"Created directory structure in {self.output_dir}")

    def _generate_assets(self):
        """Generate CSS and JavaScript files"""
        # CSS
        css_content = """
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
            background-color: #f8f9fa;
        }

        a:link,
        a:visited {
          color: #3b5aff; /* or specify an exact color */
          text-decoration: inherit; /* optional if you want same underline style */
        }

        .container {
            width: 90%;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            background-color: #343a40;
            color: white;
            padding: 1rem 0;
            text-align: center;
            margin-bottom: 2rem;
        }

        h1 {
            margin: 0;
        }

        nav {
            background-color: #dbdbdb;
            padding: 10px 0;
        }

        nav ul {
            list-style: none;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
        }

        nav li {
            margin: 0 15px;
        }

        nav a {
            color: white;
            text-decoration: none;
            font-weight: 500;
            font-size: 16px;
            transition: color 0.3s;
        }

        nav a:hover {
            color: #17a2b8;
        }

        .card {
            background: white;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
            padding: 20px;
            margin-bottom: 30px; /* Increased from 20px */
        }

        .card-title {
            margin-top: 0;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
            color: #343a40;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }

        table th, table td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }

        table th {
            background-color: #f8f9fa;
            font-weight: bold;
        }

        table tr:hover {
            background-color: #f1f1f1;
        }

        .network-container {
            width: 100%;
            height: 600px;
            border: 1px solid #ddd;
            margin-bottom: 20px;
            overflow: hidden;
            min-width: 300px; /* Ensure minimum width */
            position: relative; /* For error messages */
        }

        .tooltip {
            position: absolute;
            padding: 10px;
            background-color: rgba(0, 0, 0, 0.8);
            color: white;
            border-radius: 5px;
            pointer-events: none;
            font-size: 14px;
            z-index: 1000;
        }

        .author-stats {
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }

        .stat-box {
            flex: 1;
            min-width: 150px;
            background: white;
            padding: 15px;
            margin: 5px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
            text-align: center;
        }

        .stat-number {
            font-size: 24px;
            font-weight: bold;
            margin: 10px 0;
            color: #17a2b8;
        }

        .stat-label {
            font-size: 14px;
            color: #6c757d;
        }

        footer {
            text-align: center;
            padding: 20px;
            background-color: #343a40;
            color: white;
            margin-top: 40px;
        }
        """

        with open(self.css_dir / "style.css", 'w') as f:
            f.write(css_content)

        # JavaScript for network visualization
        network_js = """
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
        """

        with open(self.js_dir / "network.js", 'w') as f:
            f.write(network_js)

        print("Generated CSS and JavaScript assets")

    def _generate_data_files(self):
        """Generate JSON data files for visualizations"""
        # Network data
        network_data = self.data.get_coauthorship_data()
        with open(self.data_dir / "network.json", 'w') as f:
            json.dump(network_data, f, indent=2)

        # Journal stats
        journal_stats = self.data.get_journal_stats()
        with open(self.data_dir / "journals.json", 'w') as f:
            json.dump(journal_stats, f, indent=2)

        print("Generated data files")

    def _generate_index_page(self):
        """Generate the index page with network visualization"""
        html = self._page_header("Scholarly Data Visualization", active_page="index")

        # Get network data to embed directly
        network_data = self.data.get_coauthorship_data()
        network_json = json.dumps(network_data)

        # Calculate total stats for summary
        total_publications = len(self.data.publications)
        total_authors = len(self.data.authors)

        # Calculate total citations for publications in the dataset
        total_citations = sum(int(pub.get('citations', 0)) for pub in self.data.publications.values())

        # Find min and max years
        all_years = [int(pub.get('year', 0)) for pub in self.data.publications.values()
                    if pub.get('year') and str(pub.get('year')).isdigit()]
        min_year = min(all_years) if all_years else 0
        max_year = max(all_years) if all_years else 0

        # Publications per year data
        pubs_per_year = {}
        for pub in self.data.publications.values():
            year = pub.get('year')
            if year and str(year).isdigit():
                year = int(year)
                pubs_per_year[year] = pubs_per_year.get(year, 0) + 1

        # Sorted years for chart
        chart_years = sorted(pubs_per_year.keys())
        chart_pub_counts = [pubs_per_year[year] for year in chart_years]

        # Calculate more detailed author stats
        author_stats = {}
        for author_id, author_data in self.data.authors.items():
            # Get publications for this author in our dataset
            pub_ids = self.data.author_publications.get(author_id, [])
            included_pubs = [self.data.publications[pub_id] for pub_id in pub_ids if pub_id in self.data.publications]

            # Count publications
            pub_count = len(included_pubs)

            # Calculate citations for included publications only
            included_citations = sum(int(pub.get('citations', 0)) for pub in included_pubs)

            # Calculate h-index for included publications
            citation_counts = sorted([int(pub.get('citations', 0)) for pub in included_pubs], reverse=True)
            included_h_index = 0
            for i, citations in enumerate(citation_counts):
                if i+1 <= citations:
                    included_h_index = i+1
                else:
                    break

            # Store stats
            author_stats[author_id] = {
                'pub_count': pub_count,
                'included_citations': included_citations,
                'included_h_index': included_h_index,
                'lifetime_citations': int(author_data.get('total_citations', 0)),
                'lifetime_h_index': int(author_data.get('h_index', 0))
            }

        html += f"""
        <div class="container">
            <div class="card">
                <h2 class="card-title">Overview</h2>
                <p>Between <b>{min_year} and {max_year}</b>, a total of <b>{total_publications}</b> articles have been published in peer-reviewed journals or pre-print servers by <b>{total_authors}</b> authors that accumulated over <b>{total_citations}</b> citations.</p>
            </div>

            <div class="card">
                <h2 class="card-title">Total number of publications per year</h2>
                <p>This chart includes publications authored by the {total_authors} authors at the {self.institute_name}.
                <div style="height: 400px; position: relative; margin-bottom: 60px;">
                    <canvas id="yearly-publications-chart"></canvas>
                </div>
                <div style="clear: both; height: 60px;"></div>
            </div>

            <div class="card">
                <h2 class="card-title">Citation Trends</h2>
                <p>The total number of citations accumulated over the years by work published between {min_year} and {max_year} by the {total_authors} authors included in this report.
                <div style="height: 400px; position: relative; margin-bottom: 60px;">
                    <canvas id="citation-trends-chart"></canvas>
                </div>
                <div style="clear: both; height: 60px;"></div>
            </div>

            <div class="card">
                <h2 class="card-title">Co-Authorship Network</h2>
                <p>This network represents co-authorship relationships between researchers.
                   Node size indicates number of publications, node color represents h-index,
                   and edge thickness shows number of co-authored publications.</p>
                <div id="network" class="network-container"></div>
                <p><small>Click on a node to view more details about an author.</small></p>
            </div>

            <div class="card">
                <h2 class="card-title">Researchers from the {self.institute_name} included in this report</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th style="text-align: center;">Publications<br/>({min_year}-{max_year})</th>
                            <th style="text-align: center;">Citations<br/>({min_year}-{max_year})</th>
                            <th style="text-align: center;">Avg. Citations<br/>({min_year}-{max_year})</th>
                            <th style="text-align: center;">h-index<br/>({min_year}-{max_year})</th>
                            <th style="text-align: center;">Citations<br/>(Lifetime)</th>
                            <th style="text-align: center;">h-index<br/>(Lifetime)</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        # Add author rows sorted by citation count
        sorted_authors = sorted(
            self.data.authors.items(),
            key=lambda x: int(x[1].get('total_citations', 0)),
            reverse=True
        )

        for author_id, author in sorted_authors:
            stats = author_stats[author_id]
            html += f"""
                        <tr>
                            <td><a href="authors/{author_id}.html">{author.get('name', 'Unknown')}</a></td>
                            <td style="text-align: center;">{stats['pub_count']}</td>
                            <td style="text-align: center;">{stats['included_citations']}</td>
                            <td style="text-align: center;">{stats['included_citations'] / stats['pub_count']:.1f}</td>
                            <td style="text-align: center;">{stats['included_h_index']}</td>
                            <td style="text-align: center;">{stats['lifetime_citations']}</td>
                            <td style="text-align: center;">{stats['lifetime_h_index']}</td>
                        </tr>
            """

        html += """
                    </tbody>
                </table>
            </div>
        </div>

        <script src="https://d3js.org/d3.v7.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js@3.7.1/dist/chart.min.js"></script>
        <script src="js/network.js"></script>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                // Embed data directly in JavaScript instead of fetching
                const networkData = """

        html += network_json

        html += """;
                createNetwork(networkData, 'network');

                // Publications per year chart
                const pubYears = """

        html += json.dumps([str(y) for y in chart_years])

        html += """;
                const pubCounts = """

        html += json.dumps(chart_pub_counts)

        html += """;

                const pubChart = new Chart(
                    document.getElementById('yearly-publications-chart'),
                    {
                        type: 'bar',
                        data: {
                            labels: pubYears,
                            datasets: [{
                                label: 'Publications',
                                data: pubCounts,
                                backgroundColor: 'rgba(54, 162, 235, 0.7)',
                                borderColor: 'rgba(54, 162, 235, 1)',
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: true,
                            plugins: {
                                title: {
                                    display: true,
                                    text: 'Number of Publications by Year'
                                },
                                legend: {
                                    display: false
                                }
                            },
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    title: {
                                        display: true,
                                        text: 'Publication Count'
                                    }
                                },
                                x: {
                                    title: {
                                        display: true,
                                        text: 'Year'
                                    }
                                }
                            }
                        }
                    }
                );

                // Cumulative citation trends
                const citYears = """

        # Calculate cumulative citations by year
        cit_by_year = {}
        for pub in self.data.publications.values():
            year = pub.get('year')
            citations = int(pub.get('citations', 0))
            if year and str(year).isdigit():
                year = int(year)
                cit_by_year[year] = cit_by_year.get(year, 0) + citations

        # Create cumulative data
        cum_years = sorted(cit_by_year.keys())
        cum_citations = []
        running_total = 0
        for year in cum_years:
            running_total += cit_by_year[year]
            cum_citations.append(running_total)

        html += json.dumps([str(y) for y in cum_years])

        html += """;
                const cumCitations = """

        html += json.dumps(cum_citations)

        html += """;

                const citChart = new Chart(
                    document.getElementById('citation-trends-chart'),
                    {
                        type: 'line',
                        data: {
                            labels: citYears,
                            datasets: [{
                                label: 'Cumulative Citations',
                                data: cumCitations,
                                fill: true,
                                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                                borderColor: 'rgba(255, 99, 132, 1)',
                                borderWidth: 2,
                                tension: 0.1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: true,
                            plugins: {
                                title: {
                                    display: true,
                                    text: 'Cumulative Citations Over Time'
                                }
                            },
                            scales: {
                                y: {
                                    beginAtZero: true,
                                    title: {
                                        display: true,
                                        text: 'Total Citations'
                                    }
                                },
                                x: {
                                    title: {
                                        display: true,
                                        text: 'Year'
                                    }
                                }
                            }
                        }
                    }
                );
            });
        </script>
        """

        html += self._page_footer()

        with open(self.output_dir / "index.html", 'w') as f:
            f.write(html)

        print("Generated index page")


    def _generate_author_pages(self):
        """Generate individual pages for each author"""
        for author_id, author_data in self.data.authors.items():
            self._generate_author_page(author_id, author_data)

        print(f"Generated {len(self.data.authors)} author pages")

    def _generate_author_page(self, author_id, author_data):
        """Generate page for a single author"""
        name = author_data.get('name', 'Unknown Author')

        html = self._page_header(f"{name} - Scholar Profile", active_page="authors")

        # Get publication data for this author
        pub_ids = self.data.author_publications.get(author_id, [])
        publications = [self.data.publications[pub_id] for pub_id in pub_ids if pub_id in self.data.publications]

        # Sort by year (newest first), then by citations (highest first)
        publications.sort(key=lambda x: (-int(x.get('year', 0)), -int(x.get('citations', 0))))

        # Calculate statistics
        total_pubs = len(publications)
        total_citations = sum(int(p.get('citations', 0)) for p in publications)
        yearly_pubs = Counter()
        yearly_citations = Counter()
        journals = Counter()

        for pub in publications:
            year = int(pub.get('year', 0))
            yearly_pubs[year] += 1
            yearly_citations[year] += int(pub.get('citations', 0))
            journals[pub.get('journal', 'Unknown')] += 1

        # List of co-authors from our dataset
        coauthors = []
        for neighbor_id in self.data.coauthor_network.neighbors(author_id):
            neighbor_data = self.data.authors.get(neighbor_id, {})
            edge_data = self.data.coauthor_network.get_edge_data(author_id, neighbor_id)
            coauthors.append({
                'id': neighbor_id,
                'name': neighbor_data.get('name', 'Unknown'),
                'publications': edge_data.get('weight', 0),
                'shared_pub_ids': edge_data.get('publications', [])
            })

        # Sort co-authors by number of shared publications
        coauthors.sort(key=lambda x: x['publications'], reverse=True)

        # Generate the HTML
        html += f"""
        <div class="container">
            <div class="card">
                <h2 class="card-title">{name}</h2>
                <p>{author_data.get('affiliation', '')}</p>

                <div class="author-stats">
                    <div class="stat-box">
                        <div class="stat-number">{total_pubs}</div>
                        <div class="stat-label">Publications</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{total_citations}</div>
                        <div class="stat-label">Citations</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{author_data.get('h_index', 0)}</div>
                        <div class="stat-label">h-index</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{author_data.get('i10_index', 0)}</div>
                        <div class="stat-label">i10-index</div>
                    </div>
                </div>

                <p><a href="https://scholar.google.com/citations?user={author_id}" target="_blank">View Google Scholar Profile</a></p>
            </div>

            <div class="card">
                <h2 class="card-title">Publications</h2>
                <p>Showing {total_pubs} publications sorted by year (newest first):</p>

                <table>
                    <thead>
                        <tr>
                            <th>Year</th>
                            <th>Title</th>
                            <th>Journal</th>
                            <th>Citations</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for pub in publications:
            pub_url = pub.get('pub_url', '')
            title_with_link = f"<a href='{pub_url}' target='_blank'>{pub.get('title', 'Unknown Title')}</a>" if pub_url else pub.get('title', 'Unknown Title')

            html += f"""
                        <tr>
                            <td>{pub.get('year', '')}</td>
                            <td>{title_with_link}</td>
                            <td>{pub.get('journal', '')}</td>
                            <td>{pub.get('citations', 0)}</td>
                        </tr>
            """

        html += """
                    </tbody>
                </table>
            </div>
        """

        # Only show co-authors section if there are any
        if coauthors:
            html += """
            <div class="card">
                <h2 class="card-title">Co-Authors</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Shared Publications</th>
                        </tr>
                    </thead>
                    <tbody>
            """

            for coauthor in coauthors:
                html += f"""
                            <tr>
                                <td><a href="{coauthor['id']}.html">{coauthor['name']}</a></td>
                                <td>{coauthor['publications']}</td>
                            </tr>
                """

            html += """
                    </tbody>
                </table>
            </div>
            """

        # Publication trends
        years = sorted(yearly_pubs.keys())
        if years:
            # Create JSON-friendly data to embed directly
            chart_years = list(map(str, years))
            chart_pub_counts = [yearly_pubs[y] for y in years]
            chart_citation_counts = [yearly_citations[y] for y in years]

            html += """
            <div class="card">
                <h2 class="card-title">Publication Trends</h2>
                <div style="height: 400px; position: relative; margin-bottom: 90px; overflow: visible;">
                    <canvas id="publication-chart"></canvas>
                </div>
                <!-- Add a clear div to force proper spacing -->
                <div style="clear: both; height: 60px;"></div>
            </div>

            <script src="https://cdn.jsdelivr.net/npm/chart.js@3.7.1/dist/chart.min.js"></script>
            <script>
                document.addEventListener('DOMContentLoaded', function() {
                    console.log('Setting up publication chart');
                    const canvas = document.getElementById('publication-chart');
                    if (!canvas) {
                        console.error('Canvas element not found');
                        return;
                    }

                    // Direct data embedding
                    const chartLabels = """

            # Embed JSON data directly
            html += json.dumps(chart_years)

            html += """;
                    const pubData = """

            html += json.dumps(chart_pub_counts)

            html += """;
                    const citData = """

            html += json.dumps(chart_citation_counts)

            html += """;

                    console.log('Chart data:', {
                        labels: chartLabels,
                        pubData: pubData,
                        citData: citData
                    });

                    try {
                        const chart = new Chart(canvas, {
                            type: 'bar',
                            data: {
                                labels: chartLabels,
                                datasets: [{
                                    label: 'Publications',
                                    data: pubData,
                                    backgroundColor: 'rgba(54, 162, 235, 0.5)',
                                    borderColor: 'rgba(54, 162, 235, 1)',
                                    borderWidth: 1
                                }, {
                                    label: 'Citations',
                                    data: citData,
                                    yAxisID: 'y1',
                                    type: 'line',
                                    backgroundColor: 'rgba(255, 99, 132, 0.5)',
                                    borderColor: 'rgba(255, 99, 132, 1)',
                                    borderWidth: 1
                                }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: true,
                                layout: {
                                    padding: {
                                        top: 10,
                                        right: 10,
                                        bottom: 30,
                                        left: 10
                                    }
                                },
                                plugins: {
                                    legend: {
                                        position: 'top',
                                        align: 'start',
                                        labels: {
                                            boxWidth: 15,
                                            padding: 10,
                                            font: {
                                                size: 12
                                            }
                                        }
                                    }
                                },
                                scales: {
                                    y: {
                                        beginAtZero: true,
                                        title: {
                                            display: true,
                                            text: 'Publications'
                                        }
                                    },
                                    y1: {
                                        beginAtZero: true,
                                        position: 'right',
                                        title: {
                                            display: true,
                                            text: 'Citations'
                                        },
                                        grid: {
                                            drawOnChartArea: false
                                        }
                                    }
                                }
                            }
                        });
                        console.log('Chart created successfully');
                    } catch (error) {
                        console.error('Error creating chart:', error);
                    }
                });
            </script>
            """

        # Top journals
        if journals:
            top_journals = journals.most_common(10)
            html += """
            <div class="card">
                <h2 class="card-title">Top Publication Venues</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Journal</th>
                            <th>Publications</th>
                        </tr>
                    </thead>
                    <tbody>
            """

            for journal, count in top_journals:
                html += f"""
                        <tr>
                            <td>{journal}</td>
                            <td>{count}</td>
                        </tr>
                """

            html += """
                    </tbody>
                </table>
            </div>
            """

        html += """
        </div>
        """

        html += self._page_footer()

        with open(self.authors_dir / f"{author_id}.html", 'w') as f:
            f.write(html)


    def _generate_journal_page(self):
        """Generate page with journal statistics"""
        html = self._page_header("Journal Analysis", active_page="journals")

        journal_stats = self.data.get_journal_stats()

        html += """
        <div class="container">
            <div class="card">
                <h2 class="card-title">Journal Publication Analysis</h2>
                <p>This page shows statistics about publication venues in this dataset.</p>

                <table>
                    <thead>
                        <tr>
                            <th>Journal</th>
                            <th>Publications</th>
                            <th>Citations</th>
                            <th>Avg. Citations Per Paper</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        # Sort journals by publication count
        for journal in sorted(journal_stats, key=lambda x: x['publications'], reverse=True):
            html += f"""
                        <tr>
                            <td>{journal['journal']}</td>
                            <td>{journal['publications']}</td>
                            <td>{journal['citations']}</td>
                            <td>{journal['avg_citations']}</td>
                        </tr>
            """

        html += """
                    </tbody>
                </table>
            </div>
        </div>
        """

        html += self._page_footer()

        with open(self.output_dir / "journals.html", 'w') as f:
            f.write(html)

        print("Generated journal analysis page")


    def _page_header(self, title, active_page="index"):
        """Generate the common header for all pages"""

        # Calculate relative path prefix based on active page
        prefix = '..' if active_page == 'authors' else '.'

        return f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <link rel="stylesheet" href="{prefix}/css/style.css">
            <!-- Add debug console output -->
            <script>
                console.log("Page loaded: {title}");
                console.log("Active page: {active_page}");
                console.log("Using prefix: {prefix}");
            </script>
        </head>
        <body>
            <header>
                <h1>Scholarly Data For Scientists at the {self.institute_name}</h1>
            </header>

            <nav>
                <ul>
                    <li><a href="{prefix}/index.html">Overview</a></li>
                    <li><a href="{prefix}/journals.html">Journals</a></li>
                </ul>
            </nav>
        """

    def _page_footer(self):
        """Generate the common footer for all pages"""

        return f"""
            <footer>
                <p><small>Meren updated this on {datetime.now().strftime('%Y-%m-%d')}</small></p>
            </footer>
        </body>
        </html>
        """


def main():
    parser = argparse.ArgumentParser(description="Generate HTML visualization from Google Scholar data")
    parser.add_argument("data_dir", help="Directory containing Google Scholar data files (*_info.csv and *_publications.csv)")
    parser.add_argument("--output-dir", "-o", default="scholar_viz", help="Output directory for HTML files")
    parser.add_argument("--exclude-journals", type=str, help="Path to a text file that cointains journal names to exclude (one per line)")
    parser.add_argument("--institute-name", type=str, help="The name of the institute that brings together all the people in the data directory (i.e., ICBM, or HIFMB, etc)")

    args = parser.parse_args()

    # If the user specified a list of journals to exclude, work with them:
    excluded_journals = []
    if args.exclude_journals:
        try:
            with open(args.exclude_journals, 'r') as f:
                file_journals = [line.strip() for line in f if line.strip()]
                excluded_journals.extend(file_journals)
        except Exception as e:
            print(f"Error reading exclusion file: {e}")

    # Load the data
    data = PublicationData(args.data_dir, excluded_journals=excluded_journals)
    if not data.load_data():
        print("Error: Failed to load data.")
        return 1

    # Generate the HTML site
    generator = HTMLGenerator(data, args.output_dir, args.institute_name)
    generator.generate_site()

    print(f"Visualization generated in {args.output_dir}")
    print(f"Open {args.output_dir}/index.html in your web browser to view the network.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
