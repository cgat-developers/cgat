"""compare two or more vcf files
================================

At the moment a naive implementation of a multi-way comparison.
Only compare chromosome and position and remove all variants that
are PASS or ".".

"""

import os
import sys
import re
import pysam
import pandas
import cgatcore.Experiment as E
import cgatcore.IOTools as IOTools


def read_vcf_positions_into_dataframe(filename, filters=None):

    vcf_in = pysam.VariantFile(filename)

    if filters is None:
        filters = []

    pass_filter = False
    snp_filter = False

    for f in filters:
        if f == "PASS":
            pass_filter = True
        elif f == "SNP":
            snp_filter = True

    records = []
    c = E.Counter()
    for record in vcf_in:
        c.input += 1
        f = record.filter.keys()
        if pass_filter and "PASS" not in f and "." not in f:
            c.removed_pass_filter += 1
            continue
        if snp_filter:
            is_snp = (len(record.ref) == 1 and
                      len(record.alts) == 1 and
                      len(record.alts[0]) == 1)
            if not is_snp:
                c.removed_snp_filter += 1
                continue

        c.output += 1
        records.append((record.chrom, record.pos))

    df = pandas.DataFrame.from_records(
        records,
        columns=["chrom", "pos"])

    E.info("{}: {}".format(filename, c))

    return df


def main(argv=None):

    parser = E.OptionParser(version="%prog version: $Id$",
                            usage=globals()["__doc__"])

    parser.add_option(
        "--regex-filename", dest="regex_filename", type="string",
        help="extract column name from filename via regular expression "
        "[%default]")

    parser.add_option(
        "--filter", dest="filters", type="choice", action="append",
        choices=("PASS", "SNP"),
        help="apply filters to VCFs when reading "
        "[%default]")

    parser.set_defaults(
        regex_filename=None,
        filters=[],
    )

    (options, args) = E.start(parser,
                              argv=argv,
                              add_output_options=True)

    if len(args) < 2:
        raise ValueError("requiring at least 2 input filenames")

    dfs = []
    for filename in args:
        if options.regex_filename:
            try:
                name = re.search(options.regex_filename, filename).groups()[0]
            except AttributeError:
                raise ValueError("regular expression '{}' does not match {}".format(
                    options.regex_filename, filename))
        else:
            name = IOTools.snip(os.path.basename(filename), ".vcf.gz")

        E.debug("reading data from {}".format(filename))
        df = read_vcf_positions_into_dataframe(filename,
                                               filters=options.filters)
        df[name] = 1
        dfs.append(df)

    ndata = len(dfs)
    merged_df = dfs[0]
    for df in dfs[1:]:
        merged_df = merged_df.merge(df, how="outer")
    merged_df = merged_df.fillna(0)
    ddf = merged_df.drop(["chrom", "pos"], axis=1)
    set_counts = ddf.groupby(by=list(ddf.columns)).size()
    set_counts = set_counts.reset_index()
    set_counts.columns = list(set_counts.columns[:-1]) + ["counts"]

    set_counts.to_csv(options.stdout,
                      sep="\t",
                      index=False)
    E.stop()


if __name__ == "__main__":
    sys.exit(main())
