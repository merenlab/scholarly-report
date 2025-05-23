#!/usr/bin/env python3

import re
import sys
import json
import yaml
import math
import random
import argparse
import pandas as pd
import networkx as nx
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict


def load_author_aliases(yaml_file):
    """Load author aliases from a YAML file"""
    try:
        with open(yaml_file, 'r') as f:
            aliases = yaml.safe_load(f)

        # Convert to the format we'll use: {scholar_id: [list of alternative names]}
        aliases_dict = {}
        for scholar_id, names in aliases.items():
            if isinstance(names, list):
                aliases_dict[scholar_id] = names
            else:
                # Handle single string case
                aliases_dict[scholar_id] = [names]

        print(f"Loaded aliases for {len(aliases_dict)} authors from {yaml_file}")
        return aliases_dict
    except Exception as e:
        print(f"Error loading author aliases from {yaml_file}: {str(e)}")
        sys.exit(-1)


class PublicationData:
    """Handles loading and processing of publication data"""

    def __init__(self, data_dir, excluded_journals=None, author_aliases=None):
        """Initialize with the directory containing publication data"""
        self.data_dir = Path(data_dir)
        self.authors = {}  # Dictionary of author info (from _info.csv)
        self.publications = {}  # Dictionary of publications by ID
        self.author_publications = defaultdict(list)  # Publications by author
        self.coauthor_network = nx.Graph()  # Graph for co-authorship network
        self.journal_mapping = {}  # Mapping from raw journal names to standardized names
        self.author_aliases = author_aliases or {}  # Dictionary of author aliases

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

    def is_author_match(self, name, scholar_id):
        """
        Check if a name matches any alias for the given scholar ID

        This method checks:
        1. If the name matches the primary name in our dataset
        2. If the name matches any alias defined in the author_aliases dict
        3. Performs case-insensitive and whitespace-normalized matching
        """
        if not name or not scholar_id:
            return False

        # Normalize the name (lowercase, strip whitespace, normalize spacing)
        name_norm = ' '.join(name.lower().split())

        # Check if name matches the primary name in our dataset
        if scholar_id in self.authors:
            primary_name = ' '.join(self.authors[scholar_id]['name'].lower().split())
            if primary_name == name_norm:
                return True

        # Check if scholar_id is in aliases and if the name matches any alias
        if scholar_id in self.author_aliases:
            for alias in self.author_aliases[scholar_id]:
                alias_norm = ' '.join(alias.lower().split())
                if alias_norm == name_norm:
                    return True

        return False

    def _is_author_match(self, name, scholar_id):
        """Check if a name matches any alias for the given scholar ID"""
        if not name or not scholar_id:
            return False

        # Convert to lowercase for case-insensitive matching
        name_lower = name.lower()

        # Check if scholar_id is in aliases and if the name matches any alias
        if scholar_id in self.author_aliases:
            for alias in self.author_aliases[scholar_id]:
                if alias.lower() == name_lower:
                    return True

        # Also check against the author's name in our dataset
        if scholar_id in self.authors:
            if self.authors[scholar_id]['name'].lower() == name_lower:
                return True

        return False

    def _standardize_journal_name(self, journal_name):
        """Standardize journal name to fix capitalization and other inconsistencies"""
        if not journal_name or pd.isna(journal_name):
            return "Unknown"

        # Remove extra whitespace and normalize to lowercase for cache lookup
        journal_name = journal_name.strip()
        normalized_key = journal_name.lower()  # Use lowercase version as cache key

        # Check if we've already standardized this journal name (using normalized key)
        if hasattr(self, 'journal_mapping') and normalized_key in self.journal_mapping:
            return self.journal_mapping[normalized_key]

        # Split into words
        words = journal_name.split()
        standardized_words = []

        for word in words:
            # Skip empty words
            if not word:
                continue

            # Check if word has mixed case (e.g., "arXiv")
            has_mixed_case = any(c.isupper() for c in word[1:])

            if has_mixed_case:
                # Keep words with internal capitals as they are
                standardized_words.append(word)
            else:
                # Capitalize only if it's all lowercase or all uppercase
                standardized_words.append(word.capitalize())

        standardized = " ".join(standardized_words)

        # Now make it prettier
        standardized = standardized.replace(' And ', ' and ').replace(' Of ', ' of ').replace(' In ', ' in ')

        # Store in mapping for future use (using normalized key)
        if not hasattr(self, 'journal_mapping'):
            self.journal_mapping = {}
        self.journal_mapping[normalized_key] = standardized  # Use normalized key

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

                    # Update journal name if this version is "better" (i.e., not all caps like "FRONTIERS IN MARINE SCIENCE")
                    existing_journal = self.publications[pub_id]['journal']
                    if existing_journal.isupper() and not journal_name.isupper():
                        self.publications[pub_id]['journal'] = journal_name

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

    def __init__(self, data, output_dir, institute_name=None, author_aliases=None):
        """Initialize with publication data and output directory"""
        self.data = data
        self.institute_name = institute_name
        self.output_dir = Path(output_dir)
        self.authors_dir = self.output_dir / "authors"
        self.js_dir = self.output_dir / "js"
        self.css_dir = self.output_dir / "css"
        self.data_dir = self.output_dir / "data"
        self.author_aliases = author_aliases or {}

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

        # Generate individual journal detail pages
        self._generate_journal_detail_pages()

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

        /* Cuteries for sortable data tables */
        table.dataTable thead th {
            position: relative;
            cursor: pointer;
        }

        table.dataTable thead th.sorting:after,
        table.dataTable thead th.sorting_asc:after,
        table.dataTable thead th.sorting_desc:after {
            position: absolute;
            right: 8px;
            color: #999;
        }

        table.dataTable thead th.sorting:after {
            content: "⇕";
            opacity: 0.5;
        }

        table.dataTable thead th.sorting_asc:after {
            content: "↑";
        }

        table.dataTable thead th.sorting_desc:after {
            content: "↓";
        }

        table.dataTable thead th.sorting_asc,
        table.dataTable thead th.sorting_desc {
            background-color: #f8f9fa;
        }

        .dataTables_filter {
            margin-bottom: 10px;
        }

        .author-stats {
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            margin-bottom: 15px; /* Reduced from 20px to bring the rows closer */
        }

        .stat-box {
            flex: 1;
            min-width: 150px;
            background: white;
            padding: 12px; /* Slightly reduced from 15px */
            margin: 5px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
            text-align: center;
        }

        .author-stats:first-of-type .stat-box {
            background-color: #fff0f0;
        }

        .author-stats:last-of-type .stat-box {
            background-color: #f0f8ff;
        }

        .author-position {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }

        .first-author {
            background-color: #4CAF50; /* Green */
        }

        .last-author {
            background-color: #F44336; /* Red */
        }

        .middle-author {
            background-color: #9E9E9E; /* Gray */
        }

        .solo-author {
            background-color: #4CAF50; /* Green */
            border: 2px solid #303030; /* Dark border to distinguish from first author */
        }

        .pie-chart-container {
            display: inline-block;
            position: relative;
        }

        .pie-chart-container:hover::after {
            content: attr(title);
            position: absolute;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 5px;
            border-radius: 3px;
            z-index: 100;
            width: 200px;
            left: 50%;
            transform: translateX(-50%);
            top: 100%;
            text-align: left;
            white-space: pre-line;
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
                <h2 class="card-title">{self.institute_name} Overview</h2>
                <p>Between the years <b>{min_year} and {max_year}</b>, the <b>{total_authors}</b> reserchers of the {self.institute_name} included in this dataset poblished a total of <b>{total_publications}</b> articles in <a href="./journals.html">peer-reviewed journals or pre-print servers</a> that accumulated over <b>{total_citations}</b> citations collectively.</p>
            </div>

            <div class="card">
                <h2 class="card-title">Co-Authorship Network</h2>
                <p><small>You can click on a node to view more details about an author.</small></p>
                <div id="network" class="network-container"></div>
            </div>

            <div class="card">
                <h2 class="card-title">Total number of publications per year</h2>
                <p>This chart includes publications authored by the {total_authors} authors at the {self.institute_name}.
                <div style="height: 450px; position: relative; margin-bottom: 60px;">
                    <canvas id="yearly-publications-chart"></canvas>
                </div>
                <div style="clear: both; height: 60px;"></div>
            </div>

            <div class="card">
                <h2 class="card-title">Citation Trends</h2>
                <p>The total number of citations accumulated over the years by work published between {min_year} and {max_year} by the {total_authors} authors included in this report.
                <div style="height: 450px; position: relative; margin-bottom: 60px;">
                    <canvas id="citation-trends-chart"></canvas>
                </div>
                <div style="clear: both; height: 60px;"></div>
                <p>Please note that the citation counts will naturally plateau since most recent publications have not been out long enough to be cited from within other work. Thus this pattern alone does not suggest decreasing productivity or impact.
            </div>

            <div class="card">
                <h2 class="card-title">Researchers from the {self.institute_name} included in this report</h2>
                <table id="researchers-table" class="display">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th style="text-align: center;">Publications<br/>({min_year}-{max_year})</th>
                            <th style="text-align: center;">Authorship Roles<br/>({min_year}-{max_year})</th>
                            <th style="text-align: center;">Citations<br/>({min_year}-{max_year})</th>
                            <th style="text-align: center;">Avg. Citations<br/>({min_year}-{max_year})</th>
                            <th style="text-align: center;">h-index<br/>({min_year}-{max_year})</th>
                            <th style="text-align: center;">Citations<br/>(Lifetime)</th>
                            <th style="text-align: center;">h-index<br/>(Lifetime)</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        # Randomize the authors
        sorted_authors = list(self.data.authors.items())
        random.shuffle(sorted_authors)

        for author_id, author in sorted_authors:
            stats = author_stats[author_id]
            position_stats = self._calculate_author_position_stats(author_id)
            role_chart = self._generate_author_role_piechart(position_stats)

            html += f"""
                        <tr>
                            <td><a href="authors/{author_id}.html">{author.get('name', 'Unknown')}</a></td>
                            <td style="text-align: center;">{stats['pub_count']}</td>
                            <td style="text-align: center;">{role_chart}</td>
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

            // Initialize the researchers table with DataTables so we can sort things
            $('#researchers-table').DataTable({
                "paging": false,
                "info": false,
                "order": [],  // No initial sorting (keeps the random order)
                "columnDefs": [
                    { "type": "html", "targets": 0 }  // For proper sorting of name column with links
                ],
                "autoWidth": false,  // Prevent automatic width calculation
                "scrollX": true      // Add horizontal scrolling if needed
            });

        </script>
        """

        html += self._page_footer()

        with open(self.output_dir / "index.html", 'w') as f:
            f.write(html)

        print("Generated index page")


    def _calculate_author_position_stats(self, author_id):
        """Calculate authorship position statistics for an author"""
        stats = {
            'first': 0,
            'last': 0,
            'middle': 0,
            'solo': 0,
            'total': 0
        }

        # Get publication IDs for this author
        pub_ids = self.data.author_publications.get(author_id, [])

        for pub_id in pub_ids:
            if pub_id not in self.data.publications:
                continue

            pub = self.data.publications[pub_id]
            author_list = self.data._parse_authors(pub.get('authors', ''))

            if not author_list:
                continue

            # Find the position of the author in this publication
            position = self._find_author_position(author_list, author_id)

            if position is None:
                continue

            stats['total'] += 1

            if len(author_list) == 1:
                stats['solo'] += 1
            elif position == 0:
                stats['first'] += 1
            elif position == len(author_list) - 1:
                stats['last'] += 1
            else:
                stats['middle'] += 1

        return stats


    def _generate_author_role_piechart(self, stats, size=30):
        """Generate a small SVG pie chart showing author role distribution"""
        total = stats['total']
        if total == 0:
            return '<span>No data</span>'

        # Calculate percentages and angles
        first_pct = stats['first'] / total * 100
        last_pct = stats['last'] / total * 100
        middle_pct = stats['middle'] / total * 100
        solo_pct = stats['solo'] / total * 100

        # Convert percentages to angles (in radians)
        first_angle = stats['first'] / total * 2 * 3.14159
        last_angle = stats['last'] / total * 2 * 3.14159
        middle_angle = stats['middle'] / total * 2 * 3.14159
        solo_angle = stats['solo'] / total * 2 * 3.14159

        # Cumulative angles for drawing arcs
        angles = []
        cumulative = 0

        for role_angle in [first_angle, last_angle, middle_angle, solo_angle]:
            if role_angle > 0:
                angles.append((cumulative, cumulative + role_angle))
                cumulative += role_angle

        # Center coordinates and radius
        cx, cy = size/2, size/2
        radius = size/2 - 2  # Small margin

        # Generate SVG
        svg = f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">'

        # Generate pie slices
        colors = ['#4CAF50', '#F44336', '#9E9E9E', '#2196F3']  # green, red, gray, blue for first, last, middle, solo

        if total == 0:
            # If no data, draw an empty circle
            svg += f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="#eee" />'
        else:
            # Draw pie slices
            slice_index = 0
            for role, count in [('first', stats['first']), ('last', stats['last']),
                             ('middle', stats['middle']), ('solo', stats['solo'])]:
                if count == 0:
                    continue

                start_angle, end_angle = angles[slice_index]
                slice_index += 1

                # Calculate start and end points
                start_x = cx + radius * math.sin(start_angle)
                start_y = cy - radius * math.cos(start_angle)
                end_x = cx + radius * math.sin(end_angle)
                end_y = cy - radius * math.cos(end_angle)

                # Determine if this slice is more than half the pie
                large_arc = 1 if (end_angle - start_angle) > 3.14159 else 0

                # Draw the slice
                color = colors[['first', 'last', 'middle', 'solo'].index(role)]

                if count == total:
                    # If 100%, just draw a circle
                    svg += f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{color}" />'
                else:
                    # Draw a pie slice
                    svg += f'<path d="M {cx},{cy} L {start_x},{start_y} A {radius},{radius} 0 {large_arc},1 {end_x},{end_y} Z" fill="{color}" />'

        # Close SVG
        svg += '</svg>'

        # Add tooltip with percentages
        tooltip = f"First: {first_pct:.1f}%; Last: {last_pct:.1f}%; Middle: {middle_pct:.1f}%; Solo: {solo_pct:.1f}%"

        return f'<div class="pie-chart-container" title="{tooltip}">{svg}</div>'


    def _find_author_position(self, author_list, author_id):
        """
        Find the position of an author in the author list, considering aliases

        Returns:
        - The index position in author_list if found
        - None if the author isn't found
        """
        if not author_list or not author_id:
            return None

        # For debugging (uncomment if needed):
        # print(f"Finding position for {author_id} in list of {len(author_list)} authors")

        # Check each position in the author list
        for i, name in enumerate(author_list):
            # Check if the current name matches any alias for this author
            if self.data.is_author_match(name, author_id):
                return i

        # If we got here, no match was found
        return None

    def _is_author_match(self, name, author_id):
        """Check if a name matches any alias for the given author ID"""
        if not name or not author_id:
            return False

        # Convert to lowercase for case-insensitive matching
        name_lower = name.lower()

        # First check if the exact name from our authors dataset matches
        if author_id in self.data.authors:
            if self.data.authors[author_id]['name'].lower() == name_lower:
                return True

        # Then check against aliases if provided
        if self.author_aliases and author_id in self.author_aliases:
            for alias in self.author_aliases[author_id]:
                if alias.lower() == name_lower:
                    return True

        return False


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

        # Determine the year range for the author
        pub_years = [int(pub.get('year', 0)) for pub in publications if pub.get('year') and str(pub.get('year')).isdigit()]
        min_year = min(pub_years) if pub_years else "N/A"
        max_year = max(pub_years) if pub_years else "N/A"

        yearly_pubs = Counter()
        yearly_citations = Counter()
        journals = Counter()

        for pub in publications:
            year = int(pub.get('year', 0))
            yearly_pubs[year] += 1
            yearly_citations[year] += int(pub.get('citations', 0))
            journals[pub.get('journal', 'Unknown')] += 1


        # Since we have the data for publications, let's generate data for authorship positions
        # This will be missing co-first and co-senior authorships, for which I don't have a good
        # solution since such information is not tracked in publication records that reach to
        # Google Scholar
        authorship_positions = {
            'First Author': {'count': 0, 'citations': 0},
            'Last Author': {'count': 0, 'citations': 0},
            'Middle Author': {'count': 0, 'citations': 0},
            'Solo Author': {'count': 0, 'citations': 0}
        }

        for pub in publications:
            author_list = self.data._parse_authors(pub.get('authors', ''))
            citations = int(pub.get('citations', 0))

            # Skip if no authors found
            if not author_list:
                continue

            # Use our alias-aware method to find the author's position
            position = self._find_author_position(author_list, author_id)

            # Skip if author not found in list (which would be strange)
            if position is None:
                continue

            if len(author_list) == 1:
                # Solo-authored paper
                authorship_positions['Solo Author']['count'] += 1
                authorship_positions['Solo Author']['citations'] += citations
            elif position == 0:
                # First author
                authorship_positions['First Author']['count'] += 1
                authorship_positions['First Author']['citations'] += citations
            elif position == len(author_list) - 1:
                # Last author
                authorship_positions['Last Author']['count'] += 1
                authorship_positions['Last Author']['citations'] += citations
            else:
                # Middle author
                authorship_positions['Middle Author']['count'] += 1
                authorship_positions['Middle Author']['citations'] += citations

        # Let's figure out of all the co-authors of this author from our dataset
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

        # Extract and count ALL co-authors (i.e., not just those in our dataset) that
        # appear in the publications from this author
        all_coauthors = {}
        for pub in publications:
            author_list = self.data._parse_authors(pub.get('authors', ''))
            for coauthor in author_list:
                # Skip the author themselves (using our alias-aware matching)
                if self.data.is_author_match(coauthor, author_id):
                    continue

                # Standardize author name
                coauthor = ' '.join(p.lower().capitalize() for p in coauthor.split())

                # Author names with '-' character requires a little more attention
                if '-' in coauthor:
                    parts = coauthor.split('-')
                    c = [parts[0]]
                    for part in parts[1:]:
                        c.append(part[0].upper() + part[1:])
                    coauthor = '-'.join(c)

                # Update the counter
                all_coauthors[coauthor] = all_coauthors.get(coauthor, 0) + 1

        # Sort co-authors by frequency
        sorted_all_coauthors = sorted(all_coauthors.items(), key=lambda x: x[1], reverse=True)

        # Sort co-authors by number of shared publications
        coauthors.sort(key=lambda x: x['publications'], reverse=True)

        # Calculate the included-publications h-index (already doing this for the main table)
        citation_counts = sorted([int(pub.get('citations', 0)) for pub in publications], reverse=True)
        included_h_index = 0
        for i, citations in enumerate(citation_counts):
            if i+1 <= citations:
                included_h_index = i+1
            else:
                break

        # Calculate the included-publications i10-index
        included_i10_index = sum(1 for citations in citation_counts if citations >= 10)

        # Start the HTML page
        html += """<div class="container">"""

        ###########################################################################
        # Author stats card
        ###########################################################################
        html += f"""
            <div class="card">
                <h2 class="card-title">{name}</h2>

                <p>Overview of the period between <b>{min_year}</b> to <b>{max_year}</b>:

                <div class="author-stats">
                    <div class="stat-box">
                        <div class="stat-number">{total_pubs}</div>
                        <div class="stat-label">Publications<br/>(Selected Period)</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{total_citations}</div>
                        <div class="stat-label">Citations<br/>(Selected Period)</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{included_h_index}</div>
                        <div class="stat-label">h-index<br/>(Selected Period)</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{included_i10_index}</div>
                        <div class="stat-label">i10-index<br/>(Selected Period)</div>
                    </div>
                </div>

                <p>Lifetime overview:

                <div class="author-stats">
                    <div class="stat-box">
                        <div class="stat-number">{author_data.get('publication_count', 'N/A')}</div>
                        <div class="stat-label">Publications<br/>(Lifetime)</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{author_data.get('total_citations', 'N/A')}</div>
                        <div class="stat-label">Citations<br/>(Lifetime)</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{author_data.get('h_index', 'N/A')}</div>
                        <div class="stat-label">h-index<br/>(Lifetime)</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{author_data.get('i10_index', 'N/A')}</div>
                        <div class="stat-label">i10-index<br/>(Lifetime)</div>
                    </div>
                </div>

                <p><a href="https://scholar.google.com/citations?user={author_id}" target="_blank">View Google Scholar Profile</a></p>
            </div>
            """

        ###########################################################################
        # Publication trends
        ###########################################################################
        years = sorted(yearly_pubs.keys())
        if years:
            # Create JSON-friendly data to embed directly
            chart_years = list(map(str, years))
            chart_pub_counts = [yearly_pubs[y] for y in years]
            chart_citation_counts = [yearly_citations[y] for y in years]

            html += f"""
            <div class="card">
                <h2 class="card-title">Publication Trends</h2>
                <p>Trends for the period between <b>{min_year}</b> to <b>{max_year}</b>:
                <div style="height: 400px; position: relative; margin-bottom: 90px; overflow: visible;">
                    <canvas id="publication-chart"></canvas>
                </div>
                <!-- Add a clear div to force proper spacing -->
                <div style="clear: both; height: 60px;"></div>
            </div>
            """


        ###########################################################################
        # Co-authors table
        ###########################################################################
        if coauthors:
            html += f"""
            <div class="card">
                <h2 class="card-title">Co-Authors</h2>
                <p>This table only includes the co-authors of {name} from the {self.institute_name} that co-authored a publication with them between {min_year} and {max_year},
                and were included in the dataset. If you would like to see every single person person who have co-authored a publication with {name} within this period
                (regardless of whether they were included in the dataset), please see the "All Co-Authors" table below on this page.</p>
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

        ###########################################################################
        # Authorship position summary
        ###########################################################################
        html += f"""
        <div class="card">
            <h2 class="card-title">Summary of Author Role</h2>
            <p>The following table shows the distribution of publications by {name} between {min_year} and {max_year} with respect to
            their position in the list of authors. Please note that these data do not include co-first authorships and co-senior
            authorships since that information is unfortunately is not a part of the publication record and therefore lost at
            the Google Scholar level. Plus, author order is not always predictive of the role of a given author in a given
            publication, and the significance of these positions may differ from discipline to discipline.</p>
            <table id="authorship-table">
                <thead>
                    <tr>
                        <th>Position</th>
                        <th style="text-align:center;">Number of Publications</th>
                        <th style="text-align:center;">Percentage</th>
                        <th style="text-align:center;">Total Citations</th>
                        <th style="text-align:center;">Average Citations</th>
                    </tr>
                </thead>
                <tbody>
        """

        # Calculate total for percentage
        total_count = sum(pos['count'] for pos in authorship_positions.values())
        total_citations = sum(pos['citations'] for pos in authorship_positions.values())

        # Add rows in specific order
        for position in ['First Author', 'Last Author', 'Middle Author', 'Solo Author']:
            count = authorship_positions[position]['count']
            citations = authorship_positions[position]['citations']
            percentage = (count / total_count * 100) if total_count > 0 else 0
            avg_citations = (citations / count) if count > 0 else 0

            html += f"""
                    <tr>
                        <td>{position}</td>
                        <td style="text-align:center;">{count}</td>
                        <td style="text-align:center;">{percentage:.1f}%</td>
                        <td style="text-align:center;">{citations}</td>
                        <td style="text-align:center;">{avg_citations:.1f}</td>
                    </tr>
            """

        html += """
                </tbody>
            </table>
        </div>
        """

        # Top journals
        if journals:
            top_journals = journals.most_common(20)
            html += """
            <div class="card">
                <h2 class="card-title">Top Publication Venues</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Journal</th>
                            <th style="text-align:center;">Publications</th>
                        </tr>
                    </thead>
                    <tbody>
            """

            for journal, count in top_journals:
                html += f"""
                        <tr>
                            <td><a href="https://www.google.com/search?q={'+'.join(journal.split())}" target="_blank">{journal}</a></td>
                            <td style="text-align:center;">{count}</td>
                        </tr>
                """

            html += """
                    </tbody>
                </table>
            </div>
            """

        ###########################################################################
        # Bigass publications Table
        ###########################################################################
        html += f"""
            <div class="card">
                <h2 class="card-title">Publications</h2>
                <p>Showing {total_pubs} publications sorted by year (newest first):</p>

                <table id="publications-table" class="display">
                    <thead>
                        <tr>
                            <th>Year</th>
                            <th style="text-align: center;">P</th>
                            <th>Title</th>
                            <th>Journal</th>
                            <th style="text-align:center;">Citations</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for pub in publications:
            pub_url = pub.get('pub_url', '')
            title_with_link = f"<a href='{pub_url}' target='_blank'>{pub.get('title', 'Unknown Title')}</a>" if pub_url else pub.get('title', 'Unknown Title')

            # Determine author position
            author_list = self.data._parse_authors(pub.get('authors', ''))
            position_class = "middle-author"
            position_sort_value = 3

            if author_list:
                # Use a helper function to find the author's position considering aliases
                position = self._find_author_position(author_list, author_id)

                if position is not None:
                    if len(author_list) == 1:
                        position_class = "solo-author"
                        position_sort_value = 4
                    elif position == 0:
                        position_class = "first-author"
                        position_sort_value = 2
                    elif position == len(author_list) - 1:
                        position_class = "last-author"
                        position_sort_value = 3
                    else:
                        position_sort_value = 1

            # Just to make sure year and citations values will always be numeric
            year = pub.get('year', '')
            citations = pub.get('citations', 0)

            html += f"""
                        <tr>
                            <td>{year}</td>
                            <td style="text-align: center;" data-order="{position_sort_value}"><span class="author-position {position_class}" title="{position_class}"></span></td>
                            <td>{title_with_link}</td>
                            <td>{pub.get('journal', '')}</td>
                            <td style="text-align:center;">{citations}</td>
                        </tr>
            """

        html += """
                    </tbody>
                </table>
            </div>
        """

        ###########################################################################
        # Bigass "ALL COAUTHORS" table
        ###########################################################################
        html += f"""
        <div class="card">
            <h2 class="card-title">All Co-Authors</h2>
            <p>This table shows every single person who have co-authored a publication with {name} between {min_year} and {max_year}.
            If you would like to see the list of co-authors of {name} from the {self.institute_name} who appeared in this dataset,
            please see the section called "Co-Authors" instead.</p>
            <table id="all-coauthors-table" class="display">
                <thead>
                    <tr>
                        <th>Co-Author Name</th>
                        <th>Number of Publications</th>
                    </tr>
                </thead>
                <tbody>
        """

        for coauthor_name, pub_count in sorted_all_coauthors:
            html += f"""
                <tr>
                    <td><a href="https://www.google.com/search?q={'+'.join(coauthor_name.split())}+scholar" target="_blank">{coauthor_name}</a></td>
                    <td>{pub_count}</td>
                </tr>
            """

        html += """
                </tbody>
            </table>
        </div>
        """


        ###########################################################################
        # END OF PAGE
        ###########################################################################
        html += """</div>"""

        ###########################################################################
        # SCRIPTS
        ###########################################################################
        html += """
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

        # Embed JSON data directly (EMBARRASSING, BUT VERY EFFECTIVE)
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

        <!-- Continuing with other scripts -->
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
        <script>
            $(document).ready(function() {
                $('#publications-table').DataTable({
                    "paging": false,
                    "info": false,
                    "order": [[0, 'desc'], [3, 'desc']], // Default sort by year desc, then citations desc
                    "columnDefs": [
                        { "type": "html", "targets": 1 }, // For proper sorting of title column with links
                        { "type": "num", "targets": [0, 3] } // Numeric sorting for year and citations
                    ],
                    "autoWidth": false
                });
                $('#all-coauthors-table').DataTable({
                                "paging": false,
                                "info": false,
                                "order": [[1, 'desc']], // Default sort by publication count (desc)
                                "autoWidth": false
                });
            });
        </script>
        """


        html += self._page_footer()

        with open(self.authors_dir / f"{author_id}.html", 'w') as f:
            f.write(html)


    def _generate_journal_detail_pages(self):
        """Generate individual pages for each journal showing all publications"""
        journal_stats = self.data.get_journal_stats()
        journals_dir = self.output_dir / "journals"
        journals_dir.mkdir(exist_ok=True, parents=True)

        print(f"Generating detail pages for {len(journal_stats)} journals...")

        for journal_data in journal_stats:
            journal_name = journal_data['journal']
            self._generate_journal_detail_page(journal_name, journals_dir)

        print(f"Generated {len(journal_stats)} journal detail pages")

    def _generate_journal_detail_page(self, journal_name, journals_dir):
        """Generate a detailed page for a specific journal"""
        # Create a safe filename
        safe_filename = self._create_safe_filename(journal_name)

        # Get all publications for this journal
        journal_publications = []
        for pub_id, pub_data in self.data.publications.items():
            if pub_data.get('journal', 'Unknown').lower() == journal_name.lower():
                # Get author names for this publication from our dataset
                dataset_authors = []
                for author_id in pub_data.get('author_ids', []):
                    if author_id in self.data.authors:
                        dataset_authors.append({
                            'id': author_id,
                            'name': self.data.authors[author_id]['name']
                        })

                journal_publications.append({
                    'pub_data': pub_data,
                    'dataset_authors': dataset_authors
                })

        # Sort publications by year (newest first), then by citations (highest first)
        journal_publications.sort(key=lambda x: (-int(x['pub_data'].get('year', 0)), -int(x['pub_data'].get('citations', 0))))

        # Calculate statistics
        total_pubs = len(journal_publications)
        total_citations = sum(int(pub['pub_data'].get('citations', 0)) for pub in journal_publications)
        avg_citations = total_citations / total_pubs if total_pubs > 0 else 0

        # Get year range
        pub_years = [int(pub['pub_data'].get('year', 0)) for pub in journal_publications
                    if pub['pub_data'].get('year') and str(pub['pub_data'].get('year')).isdigit()]
        min_year = min(pub_years) if pub_years else "N/A"
        max_year = max(pub_years) if pub_years else "N/A"

        # Calculate author publication counts for this journal
        author_pub_counts = {}
        for pub_info in journal_publications:
            for author in pub_info['dataset_authors']:
                author_id = author['id']
                author_name = author['name']
                if author_id not in author_pub_counts:
                    author_pub_counts[author_id] = {
                        'name': author_name,
                        'count': 0
                    }
                author_pub_counts[author_id]['count'] += 1

        # Sort authors by publication count (highest first)
        sorted_authors = sorted(author_pub_counts.items(),
                               key=lambda x: x[1]['count'], reverse=True)

        # Generate HTML
        html = self._page_header(f"{journal_name} - Journal Details", active_page="journal_detail")

        html += f"""
        <div class="container">
            <div class="card">
                <h2 class="card-title">{journal_name}</h2>
                <p><a href="../journals.html">← Back to Journal Analysis</a></p>

                <div class="author-stats">
                    <div class="stat-box">
                        <div class="stat-number">{total_pubs}</div>
                        <div class="stat-label">Publications<br/>({min_year}-{max_year})</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{total_citations}</div>
                        <div class="stat-label">Total Citations</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{avg_citations:.1f}</div>
                        <div class="stat-label">Avg. Citations<br/>Per Paper</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{len(set(author['id'] for pub in journal_publications for author in pub['dataset_authors']))}</div>
                        <div class="stat-label">Authors from<br/>{self.institute_name}</div>
                    </div>
                </div>
            </div>
        """

        # Add authors who published in these journals
        author_pub_counts = ', '.join([f"""<a href="../authors/{author_id}.html">{author_data['name']}</a> (<b>{author_data['count']}</b>)""" for author_id, author_data in sorted_authors])
        html += f"""
            <div class="card">
                <h2 class="card-title">Authors of publications in {journal_name}</h2>
                <p>{author_pub_counts}.</p>
            </div>
        """

        # Add actual publications
        html += f"""
            <div class="card">
                <h2 class="card-title">Publications in {journal_name}</h2>
                <p>Showing all {total_pubs} publications from {self.institute_name} researchers published in this venue:</p>

                <table id="journal-publications-table" class="display">
                    <thead>
                        <tr>
                            <th>Year</th>
                            <th>Title</th>
                            <th>Authors from {self.institute_name}</th>
                            <th>All Authors</th>
                            <th style="text-align:center;">Citations</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for pub_info in journal_publications:
            pub = pub_info['pub_data']
            dataset_authors = pub_info['dataset_authors']

            # Create publication title with link if available
            pub_url = pub.get('pub_url', '')
            title_with_link = f"<a href='{pub_url}' target='_blank'>{pub.get('title', 'Unknown Title')}</a>" if pub_url else pub.get('title', 'Unknown Title')

            # Create links to dataset authors
            dataset_author_links = []
            for author in dataset_authors:
                dataset_author_links.append(f"<a href='../authors/{author['id']}.html'>{author['name']}</a>")
            dataset_authors_str = "; ".join(dataset_author_links) if dataset_author_links else "None"

            # All authors (truncated if too long)
            all_authors = pub.get('authors', 'Unknown')
            if len(all_authors) > 200:
                all_authors = all_authors[:200] + "..."

            year = pub.get('year', '')
            citations = pub.get('citations', 0)

            html += f"""
                        <tr>
                            <td>{year}</td>
                            <td>{title_with_link}</td>
                            <td>{dataset_authors_str}</td>
                            <td><small>{all_authors}</small></td>
                            <td style="text-align:center;">{citations}</td>
                        </tr>
            """

        html += """
                    </tbody>
                </table>
            </div>
        </div>

        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
        <script>
            $(document).ready(function() {
                $('#journal-publications-table').DataTable({
                    "paging": false,
                    "info": false,
                    "order": [[0, 'desc'], [4, 'desc']], // Default sort by year desc, then citations desc
                    "columnDefs": [
                        { "type": "html", "targets": [1, 2] }, // For proper sorting of columns with links
                        { "type": "num", "targets": [0, 4] } // Numeric sorting for year and citations
                    ],
                    "autoWidth": false,
                    "scrollX": true
                });
            });
        </script>
        """

        html += self._page_footer()

        # Write the file
        with open(journals_dir / f"{safe_filename}.html", 'w') as f:
            f.write(html)

    def _create_safe_filename(self, journal_name):
        """Create a safe filename from journal name"""
        import re
        # Remove/replace problematic characters
        safe_name = re.sub(r'[^\w\s-]', '', journal_name)
        safe_name = re.sub(r'[-\s]+', '-', safe_name)
        safe_name = safe_name.strip('-').lower()
        return safe_name[:50]  # Limit length

    def _generate_journal_page(self):
        """Generate page with journal statistics"""
        html = self._page_header("Journal Analysis", active_page="journals")

        journal_stats = self.data.get_journal_stats()

        html += """
        <div class="container">
            <div class="card">
                <h2 class="card-title">Journal Publication Analysis</h2>
                <p>This page shows statistics about publication venues in this dataset. Click on the publication count to see detailed information about publications in each journal.</p>

                <table id="journals-table" class="display">
                    <thead>
                        <tr>
                            <th>Journal</th>
                            <th style="text-align: center;">Publications</th>
                            <th style="text-align: center;">Citations</th>
                            <th style="text-align: center;">Avg. Citations Per Paper</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for journal in journal_stats:
            # Create safe filename for the detail page
            safe_filename = self._create_safe_filename(journal['journal'])


            html += f"""
                        <tr>
                            <td>{journal['journal']}</td>
                            <td style="text-align: center;" data-sort="{journal['publications']}"><a href="journals/{safe_filename}.html">{journal['publications']}</a></td>
                            <td style="text-align: center;">{journal['citations']}</td>
                            <td style="text-align: center;">{journal['avg_citations']}</td>
                        </tr>
            """

        html += """
                    </tbody>
                </table>
            </div>
        </div>
        """

        # Add JavaScript to initialize DataTables
        html += """
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
        <script>
            $(document).ready(function() {
                $('#journals-table').DataTable({
                    "paging": false,
                    "info": false,
                    "order": [[1, 'desc']],
                    "columnDefs": [
                        { "type": "num", "targets": 1 },
                        { "type": "num", "targets": [2, 3] }
                    ],
                    "autoWidth": false,
                    "scrollX": true
                });
            });
        </script>
        """

        html += self._page_footer()

        with open(self.output_dir / "journals.html", 'w') as f:
            f.write(html)

        print("Generated journal analysis page")


    def _page_header(self, title, active_page="index"):
        """Generate the common header for all pages"""

        # Calculate relative path prefix based on active page
        prefix = '..' if active_page in ['authors', 'journal_detail'] else '.'

        return f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <link rel="stylesheet" href="{prefix}/css/style.css">
            <link rel="stylesheet" href="https://cdn.datatables.net/1.11.5/css/jquery.dataTables.min.css">
            <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
            <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
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
                    <li><a href="{prefix}/index.html">Publications Overview</a></li>
                    <li><a href="{prefix}/journals.html">Journals Overview</a></li>
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
    parser.add_argument("--institute-name", type=str, required=True, help="The name of the institute that brings together all the people in the data directory (i.e., ICBM, or HIFMB, etc)")
    parser.add_argument("--author-aliases", type=str, help="Path to a YAML file containing author name aliases (alternative spellings of author names)")

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

    # Load author aliases if specified
    if args.author_aliases:
        author_aliases = load_author_aliases(args.author_aliases)
    else:
        author_aliases = {}

    # Load the data
    data = PublicationData(args.data_dir, excluded_journals=excluded_journals, author_aliases=author_aliases)
    if not data.load_data():
        print("Error: Failed to load data.")
        return 1

    # Generate the HTML site
    generator = HTMLGenerator(data, args.output_dir, args.institute_name, author_aliases=author_aliases)
    generator.generate_site()

    print(f"Visualization generated in {args.output_dir}")
    print(f"Open {args.output_dir}/index.html in your web browser to view the network.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
