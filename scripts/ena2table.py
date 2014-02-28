'''
cgat_script_template.py
=============================================

:Author: 
:Release: $Id$
:Date: |today|
:Tags: Python

Purpose
-------

Usage
-----

Example::

   python cgat_script_template.py --help

Type::

   python cgat_script_template.py --help

for command line help.

Documentation
-------------

taxid:
    human: 9606
    mouse: 10090

Controlled vocabularies:

library_type:

    GENOMIC (Genomic DNA (includes PCR products from genomic DNA))
    TRANSCRIPTOMIC (Transcription products or non genomic DNA (EST, cDNA, RT-PCR, 
                    screened libraries))
    METAGENOMIC (Mixed material from metagenome)
    METATRANSCRIPTOMIC (Transcription products from community targets)
    SYNTHETIC (Synthetic DNA)
    VIRAL RNA (Viral RNA)
    OTHER (Other, unspecified, or unknown library source material)

library_selection:

    RANDOM (Random selection by shearing or other method)
    PCR (Source material was selected by designed primers)
    RANDOM PCR (Source material was selected by randomly generated primers)
    RT-PCR (Source material was selected by reverse transcription PCR)
    HMPR (Hypo-methylated partial restriction digest)
    MF (Methyl Filtrated)
    repeat fractionation (replaces: CF-S, CF-M, CF-H, CF-T)
    size fractionation
    MSLL (Methylation Spanning Linking Library)
    cDNA (complementary DNA)
    ChIP (Chromatin immunoprecipitation)
    MNase (Micrococcal Nuclease (MNase) digestion)
    DNAse (Deoxyribonuclease (MNase) digestion)
    Hybrid Selection (Selection by hybridization in array or solution)
    Reduced Representation (Reproducible genomic subsets, often generated by 
                            restriction fragment size selection, containing a 
                            manageable number of loci to facilitate re-sampling)
    Restriction Digest (DNA fractionation using restriction enzymes)
    5-methylcytidine antibody (Selection of methylated DNA fragments using an 
                antibody raised against 5-methylcytosine or 5-methylcytidine (m5C))
    MBD2 protein methyl-CpG binding domain (Enrichment by methyl-CpG binding domain)
    CAGE (Cap-analysis gene expression)
    RACE (Rapid Amplification of cDNA Ends)
    MDA (Multiple displacement amplification)
    padlock probes capture method (to be used in conjuction with Bisulfite-Seq)
    other (Other library enrichment, screening, or selection process)
    unspecified (Library enrichment, screening, or selection is not specified)

Command line options
--------------------

'''

import os
import sys
import re
import optparse
import urllib2
import urllib
import collections
import xml.etree.ElementTree as ET

import CGAT.Experiment as E
import CGAT.IOTools as IOTools
from Bio import Entrez

# mapping various combinations of library_source and selection
# to an experiment type
MAP_CODE2DESIGN = \
    {
        ("CAGE", "TRANSCRIPTOMIC"): 'CAGE',
        ("ChIP", "GENOMIC"): "ChIP-Seq",
        ("DNase", "GENOMIC"): "DNase-Seq",
        ("Hybrid Selection", "GENOMIC"): "Exome-Seq",
        ("cDNA", "TRANSCRIPTOMIC"): "RNA-Seq",
        ("PCR", "GENOMIC"): "Genome-Seq",
    }

# all other:
# ChIP    OTHER   45
# ChIP    TRANSCRIPTOMIC  17
# DNase   TRANSCRIPTOMIC  133
# "Hybrid Selection"      TRANSCRIPTOMIC  8
# "MBD2 protein methyl-CpG binding domain"        GENOMIC 238
# MDA     GENOMIC 340
# MNase   GENOMIC 316
# PCR     GENOMIC 1829
# PCR     METAGENOMIC     56
# PCR     OTHER   12
# PCR     SYNTHETIC       8
# PCR     TRANSCRIPTOMIC  73
# RACE    TRANSCRIPTOMIC  4
# RANDOM  GENOMIC 51129
# RANDOM  METAGENOMIC     158
# RANDOM  METATRANSCRIPTOMIC      2
# RANDOM  "NON GENOMIC"   37
# RANDOM  OTHER   55
# RANDOM  TRANSCRIPTOMIC  751
# "RANDOM PCR"    GENOMIC 172
# "RANDOM PCR"    TRANSCRIPTOMIC  41
# RT-PCR  GENOMIC 3
# RT-PCR  "NON GENOMIC"   8
# RT-PCR  TRANSCRIPTOMIC  126
# "Reduced Representation"        GENOMIC 442
# "Restriction Digest"    GENOMIC 87
# cDNA    GENOMIC 63
# cDNA    METATRANSCRIPTOMIC      2
# cDNA    "NON GENOMIC"   73
# cDNA    OTHER   431
# other   GENOMIC 2845
# other   METAGENOMIC     16
# other   OTHER   306
# other   SYNTHETIC       2756
# other   TRANSCRIPTOMIC  428
# "padlock probes capture method" GENOMIC 61
# "size fractionation"    GENOMIC 121
# "size fractionation"    METAGENOMIC     8
# "size fractionation"    OTHER   2
# "size fractionation"    TRANSCRIPTOMIC  1303
# unspecified     GENOMIC 5138
# unspecified     OTHER   50
# unspecified     SYNTHETIC       14
# unspecified     TRANSCRIPTOMIC  337


def main(argv=None):
    """script main.

    parses command line options in sys.argv, unless *argv* is given.
    """

    if not argv:
        argv = sys.argv

    # setup command line parser
    parser = E.OptionParser(version="%prog version: $Id: cgat_script_template.py 2871 2010-03-03 10:20:44Z andreas $",
                            usage=globals()["__doc__"])

    parser.add_option("--library-source", dest="library_source", type="string",
                      help="supply help")

    parser.add_option("--library-selection", dest="library_selection", type="string",
                      help="supply help")

    parser.add_option("--tax-id", dest="tax_id", type="int",
                      help="supply help")

    parser.set_defaults(library_source=None,
                        library_selection=None,
                        tax_id=9606)

    # add common options (-h/--help, ...) and parse command line
    (options, args) = E.Start(parser, argv=argv)

    # tree = ET.parse('/ifs/home/andreas/ena.xml')
    # root = tree.getroot()

    # for study in root.findall("STUDY"):
    #     alias = study.attrib["alias"]
    #     center_name = study.attrib["center_name"]
    #     accession   = study.attrib["accession"]
    #     try:
    #         description = study.find("*/STUDY_DESCRIPTION").text
    #         description = description.encode('ascii', 'ignore')
    #     except AttributeError:
    #         description = ""

    #     options.stdout.write( "\t".join( (alias,
    #                                       accession,
    #                                       center_name,
    #                                       description ) ) + "\n")

    #query_url = "http://www.ebi.ac.uk/ena/data/warehouse/search?query=%22tax_eq%289606%29%20AND%20library_source=%22TRANSCRIPTOMIC%22%20AND%20%28instrument_model=%22Illumina%20Genome%20Analyzer%20II%22%20OR%20instrument_model=%22Illumina%20Genome%20Analyzer%22%20OR%20instrument_model=%22Illumina%20Genome%20Analyzer%20IIx%22%20OR%20instrument_model=%22Illumina%20HiScanSQ%22%20OR%20instrument_model=%22Illumina%20HiSeq%201000%22%20OR%20instrument_model=%22Illumina%20HiSeq%202000%22%20OR%20instrument_model=%22Illumina%20HiSeq%202500%22%29%22&domain=read&download=txt"
    #query_url = "http://www.ebi.ac.uk/ena/data/view/search?query=%22tax_eq%289606%29%20AND%20library_source=%22TRANSCRIPTOMIC%22%20AND%20%28instrument_model=%22Illumina%20Genome%20Analyzer%20II%22%20OR%20instrument_model=%22Illumina%20Genome%20Analyzer%22%20OR%20instrument_model=%22Illumina%20Genome%20Analyzer%20IIx%22%20OR%20instrument_model=%22Illumina%20HiScanSQ%22%20OR%20instrument_model=%22Illumina%20HiSeq%201000%22%20OR%20instrument_model=%22Illumina%20HiSeq%202000%22%20OR%20instrument_model=%22Illumina%20HiSeq%202500%22%29%22&domain=read&download=txt"
    #query_url = "http://www.ebi.ac.uk/ena/data/warehouse/search?query=%22(instrument_model=%22Illumina%20HiSeq%202000%22%20OR%20instrument_model=%22Illumina%20HiSeq%201000%22%20OR%20instrument_model=%22Illumina%20HiSeq%202500%22)%20AND%20library_layout=%22PAIRED%22%20AND%20library_source=%22TRANSCRIPTOMIC%22%22&domain=read"
    # query_url = "http://www.ebi.ac.uk/ena/data/view/A00145&display=xml"

    query_url = "http://www.ebi.ac.uk/ena/data/warehouse/search"
    data_url = "http://www.ebi.ac.uk/ena/data/view"

    #params = None
    # query_url = "http://www.ebi.ac.uk/ena/data/view/DRP000011&display=xml"

    fields = ['base_count',
              'read_count',
              'instrument_model',
              'scientific_name',
              'library_layout',
              'library_source',
              'library_strategy',
              'library_selection',
              'experiment_accession',
              'experiment_title',
              'study_accession',
              'study_title',
              'first_public',
              'submission_accession',
              'center_name',
              ]

    query = 'tax_eq(%i) AND instrument_platform="ILLUMINA"' % (options.tax_id)

    if options.library_source:
        query += ' AND library_source="%s" ' % options.library_source
    if options.library_selection:
        query += ' AND library_selection="%s" ' % options.library_selection

    # collect pre-study results
    params = urllib.urlencode({'query':  query,
                               'display': 'report',
                               'fields': ",".join(fields),
                               'result': 'read_run'})

    E.debug("?".join((query_url, params)))

    lines = urllib2.urlopen(query_url, params)

    header = lines.readline()

    fields.insert(0, 'run_accession')

    DATA = collections.namedtuple("DATA", fields)

    fields.append("read_length")
    fields.append("design")

    table_study = options.stdout  # IOTools.openFile( "study.tsv", "w" )
    table_study.write("\t".join(fields) + "\n")
    # collect a list of all studies
    studies = set()

    for line in lines:
        # line endings are \r\n for data, but only \n for header
        line = line[:-2]

        data = DATA(*line.split("\t"))
        try:
            read_length = float(data.base_count) / float(data.read_count)
        except ValueError:
            read_length = 0

        if data.library_layout == "PAIRED":
            read_length /= 2.0

        design = MAP_CODE2DESIGN.get(
            (data.library_selection, data.library_source),
            "other")

        table_study.write(
            line + "\t" + str(read_length) + "\t" + design + "\n")

        studies.add(data.study_accession)

    table_studies = IOTools.openFile("studies.tsv", "w")
    studies_fields = ["study_accession", "nreferences", "pubmed_ids"]

    table_studies.write("\t".join(studies_fields) + "\n")

    return

    # params = urllib.urlencode( { 'display' : 'xml' } )
    # url =  "/".join( ( data_url, 'SRP013999') ) + "&" + params
    # print urllib2.urlopen( url ).read()

    for study_accession in studies:
        # get additional info
        params = urllib.urlencode({'display': 'xml'})
        url = "/".join((data_url, study_accession)) + "&" + params

        info_lines = urllib2.urlopen(url)
        tree = ET.parse(info_lines)
        root = tree.getroot()

        pmids = []
        for link in root.findall('*//XREF_LINK'):
            db = link.find('DB').text
            if db == "pubmed":
                pmids.append(link.find('ID').text)

        # get geo
        geos = []
        for attribute in root.findall('*//STUDY_ATTRIBUTE'):
            if attribute.find('TAG').text == "GEO Accession":
                geos.append(attribute.find('VALUE').text)

        params = {'dbfrom': 'gds',
                  'db': 'pubmed',
                  }

        geo_pmids = []
        for geo in geos:
            Entrez.email = "andreas.heger@dpag.ox.ac.uk"
            handle = Entrez.esearch(db="gds", retmax=1, term=geo)
            record = Entrez.read(handle)

            uids = record['IdList']
            handle.close()

            for uid in uids:
                record = Entrez.read(Entrez.elink(dbfrom="gds",
                                                  dbto="pubmed",
                                                  id=uid))
                linksets = record[0]["LinkSetDb"]
                if not linksets:
                    continue

                assert len(linksets) == 1
                for linksetdb in linksets:
                    geo_pmids = [x['Id'] for x in linksetdb["Link"]]

        if not pmids:
            pmids = geo_pmids

        table_studies.write("\t".join(map(str, (
            study_accession,
            len(pmids),
            ",".join(pmids),
            len(geos),
            ",".join(geos)))) + "\n")

    # write footer and output benchmark information.
    E.Stop()

if __name__ == "__main__":
    sys.exit(main(sys.argv))
