#!/usr/bin/env python3

import os
import re
import sys
import time
import random
import argparse
import traceback
import pandas as pd

# All the selenium stuff
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC

# some dumb cases handled in a dumb way -- Google Scholar
# reports such weird text for these journals, this had to
# be done :(
journal_mapping = {'arxiv': 'arXiv',
                   'biorxiv': 'bioRxiv',
                   'medrxiv': 'medRxiv',
                   'g3': 'G3: Genes, Genomes, Genetics'}

class JournalParser:
    """Handles parsing and cleaning of journal information from Google Scholar"""

    @staticmethod
    def clean_journal_name(venue_info):
        """Extract just the journal name from the venue information"""

        if not venue_info:
            return ""

        # Some special cases
        venue_info_lower = venue_info.lower()
        for key in journal_mapping:
            if venue_info_lower.startswith(key):
                return journal_mapping[key]

        # Pattern to match volume/issue information
        volume_pattern = r'\s+\d+\s*(\(\d+\))?.*$'

        # Remove everything after the journal name
        journal_name = re.sub(volume_pattern, '', venue_info)

        # Another common pattern to try if the first one didn't work
        if journal_name == venue_info:
            journal_name = venue_info.split(',')[0] if ',' in venue_info else venue_info

        return journal_name.strip().rstrip(',')

    @staticmethod
    def parse_metadata(venue_info):
        """
        Parse journal metadata from venue information
        Returns a tuple of (journal_name, volume, issue)
        """
        journal_name = JournalParser.clean_journal_name(venue_info)

        # Extract volume
        volume_match = re.search(r'\s+(\d+)\s*(\(\d+\))?', venue_info)
        volume = volume_match.group(1) if volume_match else ""

        # Extract issue
        issue_match = re.search(r'\(\s*(\d+)\s*\)', venue_info)
        issue = issue_match.group(1) if issue_match else ""

        return journal_name, volume, issue


class Publication:
    """Represents a single academic publication"""

    def __init__(self, scholar_id, author_name, title, authors, venue_info, year, citations, pub_url):
        self.scholar_id = scholar_id
        self.author_name = author_name
        self.title = title
        self.authors = authors
        self.venue = venue_info
        self.year = year
        self.citations = citations
        self.pub_url = pub_url

        # Parse journal information
        self.journal, self.volume, self.issue = JournalParser.parse_metadata(venue_info)

    def to_dict(self):
        """Convert the publication to a dictionary for DataFrame creation"""
        return {
            "scholar_id": self.scholar_id,
            "author_name": self.author_name,
            "title": self.title,
            "authors": self.authors,
            "venue": self.venue,
            "journal": self.journal,
            "volume": self.volume,
            "issue": self.issue,
            "year": self.year,
            "citations": self.citations,
            "pub_url": self.pub_url
        }

    def __str__(self):
        return f"{self.title} ({self.year}) - {self.citations} citations"


class Author:
    """Represents a Google Scholar author profile"""

    def __init__(self, profile_id, name, affiliation="Unknown",
                 citations="0", h_index="0", i10_index="0"):
        self.profile_id = profile_id
        self.name = name
        self.affiliation = affiliation
        self.citations = citations
        self.h_index = h_index
        self.i10_index = i10_index
        self.publications = []
        self.min_year_filter = None
        self.max_year_filter = None

    def add_publication(self, publication):
        """Add a publication to this author"""
        self.publications.append(publication)

    def set_year_filters(self, min_year=None, max_year=None):
        """Set year filters"""
        self.min_year_filter = min_year
        self.max_year_filter = max_year

    def to_dict(self):
        """Convert author information to a dictionary"""
        result = {
            "scholar_id": self.profile_id,
            "name": self.name,
            "affiliation": self.affiliation,
            "total_citations": self.citations,
            "h_index": self.h_index,
            "i10_index": self.i10_index,
            "publication_count": getattr(self, 'pub_count', str(len(self.publications)))
        }

        if self.min_year_filter:
            result["min_year_filter"] = self.min_year_filter
        if self.max_year_filter:
            result["max_year_filter"] = self.max_year_filter

        return result

    def to_dataframe(self):
        """Convert publications to a DataFrame"""
        if not self.publications:
            return pd.DataFrame()

        return pd.DataFrame([pub.to_dict() for pub in self.publications])


class GoogleScholarScraper:
    """Main scraper class for Google Scholar profiles"""

    def __init__(self, headless=True):
        """Initialize the scraper with browser configuration"""
        self.options = Options()

        if headless:
            self.options.add_argument("--headless")

        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

        self.driver = None
        self.wait = None

    def _init_driver(self):
        """Initialize the webdriver"""
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=self.options
        )
        self.wait = WebDriverWait(self.driver, 10)

    def _cleanup(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.wait = None

    def _get_author_info(self, profile_id):
        """Extract author information from profile page"""
        url = f"https://scholar.google.com/citations?user={profile_id}&hl=en"
        print(f"Accessing URL: {url}")
        self.driver.get(url)
        time.sleep(5)  # Initial wait for page to load

        # Get author name
        author_name = self.driver.find_element(By.ID, "gsc_prf_in").text.replace('.', '')
        print(f"Found profile for: {author_name}")

        # Get affiliation
        try:
            affiliation = self.driver.find_element(By.CLASS_NAME, "gsc_prf_il").text
        except:
            affiliation = "Not found"

        # Get citation statistics
        try:
            citation_stats = self.driver.find_elements(By.CLASS_NAME, "gsc_rsb_std")
            citations = citation_stats[0].text if len(citation_stats) > 0 else "0"
            h_index = citation_stats[2].text if len(citation_stats) > 2 else "0"
            i10_index = citation_stats[4].text if len(citation_stats) > 4 else "0"
        except:
            citations, h_index, i10_index = "0", "0", "0"

        print(f"Citations: {citations}, h-index: {h_index}, i10-index: {i10_index}")

        return Author(profile_id, author_name, affiliation, citations, h_index, i10_index)

    def _show_more_publications(self):
        """Click 'Show More' button to reveal more publications"""
        show_more_attempts = 0
        while show_more_attempts < 10:  # Limit attempts to avoid infinite loop
            try:
                show_more = self.wait.until(EC.element_to_be_clickable((By.ID, "gsc_bpf_more")))
                if not show_more.is_displayed() or not show_more.is_enabled():
                    print("No more 'Show More' button visible")
                    break
                show_more.click()
                print("Clicked 'Show More'")
                time.sleep(5)  # Wait for content to load
                show_more_attempts += 1
            except Exception as e:
                print(f"No more publications to load or error: {str(e)}")
                break

    def _get_publication_details(self, pub_element, author, i, total_count):
        """Extract and process details for a single publication"""
        try:
            # Extract basic info from the publication row
            title_element = pub_element.find_element(By.CSS_SELECTOR, "a.gsc_a_at")
            title = title_element.text
            pub_link = title_element.get_attribute("href")

            # Get author and venue information
            info_elements = pub_element.find_elements(By.CSS_SELECTOR, "div.gs_gray")
            authors_venue = info_elements[0].text if len(info_elements) > 0 else "N/A"
            venue_info = info_elements[1].text if len(info_elements) > 1 else "N/A"

            # Extract year
            year_element = pub_element.find_element(By.CSS_SELECTOR, "td.gsc_a_y")
            year = year_element.text.strip()

            # Skip if year is not a valid digit or outside filter range
            if not year.isdigit():
                print(f"Skipping publication with invalid year ('{year}'): {title[:30]}...")
                return None

            if ((author.min_year_filter and int(year) < author.min_year_filter) or
                (author.max_year_filter and int(year) > author.max_year_filter)):
                print(f"Skipping publication from {year} (outside year range): {title[:30]}...")
                return None

            # Get citation count
            citation_element = pub_element.find_element(By.CSS_SELECTOR, "td.gsc_a_c")
            citations = citation_element.text.replace('*', '').strip()
            citations = "0" if not citations else citations

            # Default author format from main page
            full_authors = authors_venue

            # Visit publication detail page to get complete information
            if pub_link:
                full_authors = self._visit_publication_page(pub_link, title, full_authors, venue_info)

            # Create publication object
            publication = Publication(
                author.profile_id, author.name, title, full_authors,
                venue_info, year, citations, pub_link
            )

            # Log progress
            if i < 3 or i % 10 == 0:  # Print first few and occasional updates
                print(f"Processed {i+1}/{total_count}: {title[:30]}... ({year}) - {citations} citations")
                print(f"  Journal: '{publication.journal}', Volume: {publication.volume}, Issue: {publication.issue}")
                print(f"  Authors: {full_authors[:50]}{'...' if len(full_authors) > 50 else ''}")

            return publication

        except Exception as e:
            print(f"Error extracting publication {i}: {str(e)}")
            traceback.print_exc()
            return None

    def _visit_publication_page(self, pub_link, title, default_authors, venue_info):
        """Visit publication detail page to get full author list and better venue info"""
        full_authors = default_authors

        try:
            print(f"Getting full details for: {title[:30]}...")

            # Add a small random delay to avoid detection
            time.sleep(random.uniform(5.0, 10.0))

            # Open publication page in a new window
            self.driver.execute_script(f"window.open('{pub_link}', '_blank');")
            self.driver.switch_to.window(self.driver.window_handles[1])
            time.sleep(4)

            try:
                # Try to find the full author list in the popup
                author_elements = self.driver.find_elements(By.CSS_SELECTOR, ".gsc_oci_value")
                if author_elements and len(author_elements) > 0:
                    # The first value field usually contains the authors
                    full_authors = author_elements[0].text

                # Check if we need to try an alternative selector
                alternative_authors = self.driver.find_elements(By.CSS_SELECTOR, "#gsc_oci_title_authors .gsc_oci_value")
                if alternative_authors and len(alternative_authors) > 0:
                    full_authors = alternative_authors[0].text
            except Exception as e:
                print(f"Could not find full details in popup: {e}")

            # Close the publication window and switch back to the main window
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
        except Exception as e:
            print(f"Error accessing publication details: {e}")
            # If there are multiple windows open, make sure we get back to the main one
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[0])

        return full_authors

    def scrape_profile(self, profile_id, min_year=None, max_year=None):
        """Scrape a Google Scholar profile by ID"""
        try:
            self._init_driver()

            # Get author information
            author = self._get_author_info(profile_id)
            author.set_year_filters(min_year, max_year)

            # Load all publications
            self._show_more_publications()

            # Now that all publications are loaded, get the total count
            try:
                # Count all publications on the page now that they're fully loaded
                pub_elements = self.driver.find_elements(By.CSS_SELECTOR, "tr.gsc_a_tr")
                author.pub_count = str(len(pub_elements))
                print(f"Publication count: {author.pub_count}")
            except Exception as e:
                print(f"Error getting publication count: {str(e)}")
                author.pub_count = "0"
                print("Set author pub count to 0 :/")

            # Process each publication
            for i, pub_element in enumerate(pub_elements):
                publication = self._get_publication_details(pub_element, author, i, len(pub_elements))
                if publication:
                    author.add_publication(publication)

            # Log results
            if min_year or max_year:
                year_range = f"from {min_year if min_year else 'earliest'} to {max_year if max_year else 'latest'}"
                print(f"Filtered to {len(author.publications)} publications {year_range}")

            return author

        except Exception as e:
            print(f"Error during scraping: {str(e)}")
            traceback.print_exc()
            return None

        finally:
            self._cleanup()


class ScholarDataManager:
    """Manages saving and loading of Google Scholar data"""

    @staticmethod
    def save_author_info(author, output_dir="."):
        """Save author information to a CSV file"""
        if not author:
            return False

        author_df = pd.DataFrame([author.to_dict()])
        author_file = os.path.join(output_dir, f"{author.profile_id}_info.csv")
        author_df.to_csv(author_file, index=False, sep='\t')
        print(f"Author information saved to {author_file}")
        return True

    @staticmethod
    def save_publications(author, output_dir="."):
        """Save publications to a CSV file"""
        if not author or not author.publications:
            return False

        df = author.to_dataframe()
        output_file = os.path.join(output_dir, f"{author.profile_id}_publications.csv")
        df.to_csv(output_file, index=False, sep='\t')
        print(f"Publications data saved to {output_file}")
        return True


def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Scrape Google Scholar profile by ID')
    parser.add_argument('scholar_id', type=str, help='Google Scholar Profile ID')
    parser.add_argument('--min-year', type=int, help='Minimum publication year to include')
    parser.add_argument('--max-year', type=int, help='Maximum publication year to include')
    parser.add_argument('--output-dir', '-o', type=str, default=".",
                        help='Directory to save output files (default: current directory)')
    parser.add_argument('--no-headless', action='store_true',
                        help='Run browser in visible mode (not headless)')

    args = parser.parse_args()

    # Create output directory if it doesn't exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        print(f"Created output directory: {args.output_dir}")

    # Create year range description for output
    year_coverage = ""
    if args.min_year or args.max_year:
        if args.min_year and not args.max_year:
            year_coverage = f" (publications from {args.min_year} onwards)"
        elif not args.min_year and args.max_year:
            year_coverage = f" (publications before {args.max_year})"
        else:
            year_coverage = f" (publications between {args.min_year} and {args.max_year})"

    print(f"Starting Google Scholar scraping for ID: {args.scholar_id}{year_coverage}")

    # Create and run the scraper
    scraper = GoogleScholarScraper(headless=not args.no_headless)
    author = scraper.scrape_profile(args.scholar_id, args.min_year, args.max_year)

    if author and author.publications:
        print("\nAuthor Information:")
        for key, value in author.to_dict().items():
            print(f"{key}: {value}")

        print(f"\nFound {len(author.publications)} publications")

        # Save data
        ScholarDataManager.save_author_info(author, args.output_dir)
        ScholarDataManager.save_publications(author, args.output_dir)
        return 0
    else:
        print("Failed to retrieve data")
        return 1


if __name__ == "__main__":
    sys.exit(main())
