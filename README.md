# Scholarly Reports for Institutes

This software package is meant to solve a very annoying issue: preparing interactive reports for departments or institutes that are required to collect all the publication information from the members of their workforce during a specific period. By providing a bunch of Google Scholar IDs, you will get from this tool an interactive interface that allows you to track,

* The total number of yearly publications and citations,
* Collaboration network among scientists through shared co-authorsipts,
* Journals in which publications appear, etc.

If you run into this software and are interested in using it for your own needs but not sure how to do it, please feel free to reach out to me via meren@hifmb.de and I will help you to setup and deploy it :)

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

Now you can get a copy of the code, and install it nto this new conda environment:

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

The package does its work in two steps: (1) collecting author data, and (2) generating a report for all authors. The following sections explain the deatils for each step.

## Collecting author data

Author data are collected for each author one by one, and accumulate in an output directory. For instance, this command will collect information about ALL the publications for the author whose Google Scholar profile is [GtLLuxoAAAAJ](https://scholar.google.com/citations?user=GtLLuxoAAAAJ&hl=en), and store key files under the `SCHOLARLY_DATA` directory:

```bash
sc-get-author-data GtLLuxoAAAAJ \
                   --output-dir SCHOLARLY_DATA
```

But this is rarely useful, since reporting tasks require only a certain period. So you can get publications until a certain year:

```bash
# retrieve information for publications appeared in literature until 2021
sc-get-author-data GtLLuxoAAAAJ \
                   --max-year 2021 \
                   --output-dir SCHOLARLY_DATA
```

Get those only appeared after a certain year:

```bash
# retrieve information for publications appeared in literature after 2023
sc-get-author-data GtLLuxoAAAAJ \
                   --min-year 2023 \
                   --output-dir SCHOLARLY_DATA
```

Or within a period:

```bash
# retrieve information for publications appeared in literature after 2023
sc-get-author-data GtLLuxoAAAAJ \
                   --min-year 2020 \
                   --max-year 2024 \
                   --output-dir SCHOLARLY_DATA
```

This will give you publications from this author ONLY in the year 2024:

```bash
# retrieve information for publications appeared in literature after 2023
sc-get-author-data GtLLuxoAAAAJ \
                   --min-year 2024 \
                   --max-year 2024 \
                   --output-dir SCHOLARLY_DATA
```

This is handy since some people may have started later than the beginning of the reporting period, so by explicitly defining a window for each author is important for accurate reporting.

Remember, if you do this for many many authors and for many many years, you will eventually get blocked by Google since you are not supposed to scrape their web content just like that. I put a lot of controls for that to _not_ happen (such as random amount of waits between different requests so the program behaves like a normal user and without creating too much strain on poor Google servers), it may still happen, so you should keep an eye on the very useful output messages.

Once all authors are done, it is time to generate a report.

## Generating a report

Assuming the data have been accumulating in the directory `SCHOLARLY_DATA`, you can run the second tool to produce a web report.

Running this will generate an output directory with all the web content:

```bash
sc-produce-web-report SCHOLARLY_DATA \
                      --output-dir SCHOLARLY_REPORT \
                      --institute-name ICBM
```

It is important to provide an institute name, otherwise the output will look very ugly.

Another thing that will certainly look ugly will be the _journal names_. Since Google Scholar collects everything, conference abstracts and other irrelevant entries really makes the report look quite crappy. If you want, you can creat a flat text file with 'unwanted journal names', and send it to this program to they are excluded from the reporting:

```bash
sc-produce-web-report SCHOLARLY_DATA \
                      --output-dir SCHOLARLY_REPORT \
                      --institute-name ICBM \
                      --exclude-journals JOURNAL-NAMES-TO-EXCLUDE.txt
```

There should be a single journal name in each line of this file, and they don't have to be complete. The code is smart enough to find "2024 Ocean Sciences Meeting" if you only put in "Ocean Sciences Meeting" or "Meeting".

So, once the output is ready, you can view it on your computer by first running a local server in the output directory as such,

```bash
cd SCHOLARLY_REPORT
python -m http.server 8000
```

And then visiting this URL on your web browser:

[http://localhost:8000/](http://localhost:8000/)

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
Society+ Space
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

Your web page is ready :) Read below to figure out how to view it.

### Upload it to a remote server

The resulting directory is a self-contained web page. If you have a web page, you can upload the content to your web server directly, and visit the relevant URL. When you do that, you will see an interactive web page like this one here:

[https://merenlab.github.io/scholarly-report/](https://merenlab.github.io/scholarly-report/)

### View it locally

Alternatively, you can run a mini Python web server in your output directory to visualize the contents of it using your browser. For that you can run the following commands:

```bash
# go into the output directory
cd SCHOLARLY_REPORT

# run the server
python -m http.server 8000
```

Now you can open your browser, and visit the URL [http://localhost:8000/](http://localhost:8000/) on your own computer, and you should see the following sections:

![image](https://github.com/user-attachments/assets/eb3c1fab-635b-4b0f-a06c-ca9f970b000f)

Total number of publications per year:

![image](https://github.com/user-attachments/assets/bf706ffb-632f-440a-81c2-4d7961eda726)

Citation trends for the papers included in this analysis (which depends on the number of Google Scholar profiles and the years of consideration, of course):

![image](https://github.com/user-attachments/assets/f321553d-5acf-4744-8c6d-77d723cd7223)

Co-authorship network resolved from shared publications (lol, Meren):

![image](https://github.com/user-attachments/assets/6c4de736-d6f6-4ef5-b48e-8ad5f2e3624b)

Some overall statistics for everyone considered (for the year period, and lifetime statistics so those who are responsible for reporting can use these data in any way they see fit):

![image](https://github.com/user-attachments/assets/ffb14a4e-513d-4206-8623-a0523099bbd7)

All author names are clickable. When you click one, you see some general statistics:

![image](https://github.com/user-attachments/assets/460a8d6b-fb2d-41fd-b899-33cb36f7dee3)

Publications from the period of interest:

![image](https://github.com/user-attachments/assets/f4b921ee-01a6-453f-a16e-9e7a37c549a3)

Co-authors from that period:

![image](https://github.com/user-attachments/assets/a5692d14-a963-4c7b-87e5-fc56141a7f83)

Personal trends for number of publications and citations:

![image](https://github.com/user-attachments/assets/9d8ebf03-003d-4105-a34d-aa5bd9af21d3)

And where do their publications appear:

![image](https://github.com/user-attachments/assets/57af34ca-23b0-4410-b048-d2481c36c46d)

Then there is the entire 'journals' page:

![image](https://github.com/user-attachments/assets/c3f423f6-02b6-4192-8276-d0a3bc00d11d)

This is a great page to find crappy journal names,  update `JOURNAL-NAMES-TO-EXCLUDE.txt`, and re-run the `sc-produce-web-report` command with the same parameters.
