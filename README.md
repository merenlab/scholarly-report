# Scholarly Reports for Institutes

The tools here are meant to solve a very annoying issue: preparing reports for departments or institutes that require to collect all the publication information from a number of authors. I implemented these tools to address that issue. It works with Google Scholar IDs.

What you see here works in two steps:

## Collecting author data

Author data are collected for each author one by one, and accumulate in an output directory. For instance, this command will collect information about ALL the publications for the author whose Google Scholar profile is [GtLLuxoAAAAJ](https://scholar.google.com/citations?user=GtLLuxoAAAAJ&hl=en), and store key files under the `SCHOLAR_DATA` directory:

```bash
python get-author-data GtLLuxoAAAAJ --output-dir SCHOLAR_DATA
```

But this is rarely useful, since reporting tasks require only a certain period. So you can get publications until a certain year:

```bash
# retrieve information for publications appeared in literature until 2021
python get-author-data GtLLuxoAAAAJ --max-year 2021 --output-dir SCHOLAR_DATA
```

Get those only appeared after a certain year:

```bash
# retrieve information for publications appeared in literature after 2023
python get-author-data GtLLuxoAAAAJ --max-year 2021 --output-dir SCHOLAR_DATA
```

Or within a period:

```bash
# retrieve information for publications appeared in literature after 2023
python get-author-data GtLLuxoAAAAJ --min-year 2020 --max-year 2024 --output-dir SCHOLAR_DATA
```

This will give you publications from this author ONLY in the year 2024:

```bash
# retrieve information for publications appeared in literature after 2023
python get-author-data GtLLuxoAAAAJ --min-year 2024 --max-year 2024 --output-dir SCHOLAR_DATA
```

This is handy since some people may have started later than the beginning of the reporting period, so by explicitly defining a window for each author is important for accurate reporting.

Remember, if you do this for many many authors and for many many years, you will eventually get blocked by Google since you are not supposed to scrape their web content just like that. I put a lot of controls for that to _not_ happen (such as random amount of waits between different requests so the program behaves like a normal user and without creating too much strain on poor Google servers), it may still happen, so you should keep an eye on the very useful output messages.

Once all authors are done, it is time to generate a report.

## Generating a report

Assuming the data have been accumulating in the directory `SCHOLAR_DATA`, you can run the second tool to produce a web report.

Running this will generate an output directory with all the web content:

```bash
python produce-web-report SCHOLAR_DATA --output-dir SCHOLAR_REPORT --institute-name ICBM
```

It is important to provide an institute name, otherwise the output will look very ugly.
