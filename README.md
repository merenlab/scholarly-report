# Scholarly Activity Reports for Institutes

This software package is meant to solve a very annoying issue: preparing interactive reports for departments or institutes that are required to collect all the publication information from the members of their workforce during a specific period. By providing a bunch of Google Scholar IDs, you will get from this tool an interactive interface that allows you to track,

* The total number of yearly publications and citations,
* Collaboration network among scientists through shared co-authorships,
* Detailed insights into each author and their roles in papers they authored,
* Journals in which publications appear, etc.

I created this tool simply because we needed it for a reporting task, and wanted to describe it extensively here so you can use it, too. Please feel free to reach out to me via meren@hifmb.de if you need any help using it, and I will help you to setup and deploy it.

---

Please note that Google does *not* appreciate scraping of the content displayed on their web pages (including Google Scholar), and has implemented many mechanisms to prevent such use of their data. Scraping data for a handful of scientists for non-commercial interests is not the same thing with companies that scrape literally millions of pages for profit. But rules are rules. If you use this program nevertheless to summarize a very large number of profiles, there is a high likelihood that Google will catch you, and stop responding to your requests (which will *only* stop this program to continue working, and will not impact anything else with your relationship with Google services). That said, it is still doable with commercial solutions that can overcome those barriers. I included one of those solutions below in case you are really serious about doing this, but it *will* cost you some money. In my example I used ScraperAPI, but it is way more expensive than some other alternatives. It is likely that I will be the only user of this tool, so I don't want to waste too much time writing about things that other will not need, but if you are reading these lines and feel like this is what you need, let me know, and I will share my 2 cents with you regarding how to generate reports effectively.

# Installation

To install this package, follow the simple steps below.

## Create a conda environment

This will make sure the package will not interfere with any other libraries installed on your system. Open a new terminal and run the following commands:

```bash
# deactivate any conda environment you may be in
conda deactivate

# create a new conda environment for scholarly-report
conda create -y --name scholarly-report python=3.10

# activate that environment
conda activate scholarly-report
```

Now you can get a copy of the code, and install it into this new conda environment:

```bash
# make sure there is an appropriate directory
# somewhere to clone the project
mkdir -p ~/github/
cd ~/github/

# get a copy of the git repository
git clone https://github.com/merenlab/scholarly-report.git
cd scholarly-report

# install:
pip install -e .
```

If you are here, and running this command gives you a nice help menu rather than a command not found error, you are golden:

```bash
sc-get-author-data -h
```

Now you can jump to the Usage section below. But please keep in mind that every time you open a new terminal, you will have to run the following command to activate your conda environment:

```bash
conda activate scholarly-report
```

# Usage

The package does its work in two steps: (1) collecting author data, and (2) generating a report for all authors. The following sections explain the details for each step.

## Collecting author data

Author data are collected for each author one by one, and accumulate in an output directory. For instance, this command will collect information about ALL the publications for the author whose Google Scholar profile is [GtLLuxoAAAAJ](https://scholar.google.com/citations?user=GtLLuxoAAAAJ&hl=en), and store key files under the `SCHOLARLY_DATA` directory:

```bash
sc-get-author-data GtLLuxoAAAAJ \
                   --output-dir SCHOLARLY_DATA
```

But this is rarely useful, since most reporting tasks require only a certain period, and trying to get all the publications regardless will make Google even more upset. So there are a few ways you can define a particular timeframe you are interested in. For instance, you can get publications until a certain year:

```bash
# retrieve information for publications appeared in literature until 2021
sc-get-author-data GtLLuxoAAAAJ \
                   --max-year 2021 \
                   --output-dir SCHOLARLY_DATA
```

Or only those that appeared after a certain year:

```bash
# retrieve information for publications appeared in literature after 2023
sc-get-author-data GtLLuxoAAAAJ \
                   --min-year 2023 \
                   --output-dir SCHOLARLY_DATA
```

Or those that were published within a period:

```bash
# retrieve information for publications appeared in literature after 2023
sc-get-author-data GtLLuxoAAAAJ \
                   --min-year 2020 \
                   --max-year 2024 \
                   --output-dir SCHOLARLY_DATA
```

Or from a single year (say, 2024):

```bash
# retrieve information for publications appeared in literature after 2023
sc-get-author-data GtLLuxoAAAAJ \
                   --min-year 2024 \
                   --max-year 2024 \
                   --output-dir SCHOLARLY_DATA
```

This is handy since some people may have started working at an institution later than the beginning of the reporting period, so by explicitly defining a window for each author could be important for accurate reporting.

Remember, if you do this for many many authors and for many many years, you will eventually get blocked by Google since you are not supposed to scrape their web content just like that. I put a lot of controls for that to _not_ happen (such as random amount of waits between different requests so the program behaves like a normal user and without creating too much strain on poor poor Google servers), but it may still happen, so you should keep an eye on the output messages.

### Using ScraperAPI for reliable data collection

If you're planning to collect data for many authors or experiencing issues with Google Scholar blocking your requests, you can use [ScraperAPI](https://www.scraperapi.com/) to make your data collection more reliable. ScraperAPI provides rotating proxies and handles anti-bot measures automatically.

To use ScraperAPI sign up for a ScraperAPI account at [scraperapi.com](https://www.scraperapi.com/), and get your API key from the dashboard. Once you have your API key, pass it to the program using the `--scraperapi-key` parameter:

```bash
sc-get-author-data GtLLuxoAAAAJ \
                   --min-year 2020 \
                   --max-year 2024 \
                   --output-dir SCHOLARLY_DATA \
                   --scraperapi-key "your_api_key_here"
```

**Note**: ScraperAPI is a paid service. Check their pricing plans to understand the costs. For small-scale usage, the free tier might be sufficient, but for large institutes with many authors, you may need a paid plan.

## Generating a report

Assuming the data have been accumulating in the directory `SCHOLARLY_DATA`, you can run the second tool to produce a web report.

Running this will generate an output directory with all the web content:

```bash
sc-produce-web-report SCHOLARLY_DATA \
                      --output-dir SCHOLARLY_REPORT \
                      --institute-name ICBM
```

It is important to provide a meaningful institute name (that's why if you don't do it, you will get an error).

Once your report is ready, you can simply open the `index.html` file in your browser. Just to simplify things, you can copy paste this command to your terminal, and copy the output path to your browser window:

```
ls $(pwd)/SCHOLARLY_REPORT/index.html
```

If you want to be fancier, you can also run a local server in the output directory as such,

```bash
cd SCHOLARLY_REPORT
python -m http.server 8000
```

And then visit this URL on your web browser:

[http://localhost:8000/](http://localhost:8000/)

There are multiple ways you can a local server in the output directory as such,

```bash
cd SCHOLARLY_REPORT
python -m http.server 8000
```

And then visiting this URL on your web browser:

[http://localhost:8000/](http://localhost:8000/)

Generating a report and viewing it is this easy. But there are multiple ways you will likely feel the need to improve your output such as by removing some 'journal names' from consideration, and by accommodating authors that appear in publications with multiple names, which are covered in the following sections.

### Journal names to exclude

Since Google Scholar collects everything, conference abstracts and other irrelevant entries really makes the report look quite crappy. To mitigate that you can create a flat text file to list 'unwanted journal names', and exclude them from the reporting using the following parameter:

```bash
sc-produce-web-report SCHOLARLY_DATA \
                      --output-dir SCHOLARLY_REPORT \
                      --institute-name ICBM \
                      --exclude-journals JOURNAL-NAMES-TO-EXCLUDE.txt
```

There should be a single journal name in each line of this file, and they don't have to be complete: the code will exclude "2024 Ocean Sciences Meeting" if you only put in "Ocean Sciences Meeting", or simply, "Meeting".

### Authors names to merge

Sometimes authors appear in publications under different name variations for various reasons (e.g., "A Murat Eren", "AM Eren", etc) which kind of ruins the reporting. The author aliases mechanism allows you to group these variations under a single canonical name for cleaner reporting.

To use author aliases and aggregate all versions of author names under a single one you can create a YAML file with author name mappings organized by Google Scholar ID. Here is an example file structure:

```yaml
GtLLuxoAAAAJ:
  - "A Murat Eren"
  - "AM Eren"
KenJWYwAAAAJ:
  - "Iliana B Baums"
  - "IB Baums"
  - "Iliana Baums"
```

After saving such a file (e.g., as `AUTHOR-ALIASES.yaml`) in your working directory, you can re-generate your report the following way:

```bash
sc-produce-web-report SCHOLARLY_DATA \
                      --output-dir SCHOLARLY_REPORT \
                      --institute-name ICBM \
                      --author-aliases AUTHOR-ALIASES.yaml
```

When provided, the program will use the author aliases file to automatically replace all occurrences of the aliases with the primary name throughout the report, making collaboration networks and author statistics more accurate and cleaner.

## An example run

Here is an example run (that is fully reproducible) and the resulting output I generated for 5 scientists at the ICBM just as an example:

```bash
GOOGLE_SCHOLAR_IDS="2bC6aPsAAAAJ 3ioz2B4AAAAJ 83LAYbIAAAAJ atQ-4b8AAAAJ bxXw-JUAAAAJ eogyTQUAAAAJ GtLLuxoAAAAJ hDRCDJwAAAAJ KenJWYwAAAAJ SRJug_AAAAAJ UJoAfkIAAAAJ UmlxKj4AAAAJ mim-jzwAAAAJ"

# populate the contents of SCHOLARY DATA directory
# for each Google Scholar profiles
for GSID in $GOOGLE_SCHOLAR_IDS
do
    sc-get-author-data $GSID \
                       --min-year 2023 \
                       --output-dir SCHOLARLY_DATA
done

# generate a file that contains unwanted journal
# names -- this is a fancy way to just reproduce
# this but you can create a text file in any way
# you wish
cat <<EOF > JOURNAL-NAMES-TO-EXCLUDE.txt
Ocean Sciences Meeting
Forb Diversity
Unknown
Interreg
Zfo-thesenpapier
US Patent
Conference Abstracts
Natur Und Recht
Oekom
Cordap
Congresso
Conference Series
Agu
Gfz Data Services
Goldschmidt
Egu25
Faktencheck Artenvielfalt
OSF
EOF

# Generate a report directory
sc-produce-web-report SCHOLARLY_DATA \
                      --output-dir SCHOLARLY_REPORT \
                      --exclude-journals JOURNAL-NAMES-TO-EXCLUDE.txt \
                      --institute-name ICBM
```

## Sharing the report with others

The output is a static, self-contained web page, thus you can simply 'zip' the output directory and send it to anyone and instruct them to open the index.html file in their browser. You can also upload the content to your web server directly, and visit the relevant URL. When you do that, you will see an interactive web page like this one here:

[https://merenlab.github.io/scholarly-report/](https://merenlab.github.io/scholarly-report/)
