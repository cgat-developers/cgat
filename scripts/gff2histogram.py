################################################################################
#
#   MRC FGU Computational Genomics Group
#
#   $Id$
#
#   Copyright (C) 2009 Andreas Heger
#
#   This program is free software; you can redistribute it and/or
#   modify it under the terms of the GNU General Public License
#   as published by the Free Software Foundation; either version 2
#   of the License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#################################################################################
'''
gff2histogram.py - compute histograms from intervals in gff or bed format
=========================================================================

:Author: Andreas Heger
:Release: $Id$
:Date: |today|
:Tags: Python

Purpose
-------

This script computes distribution interval sizes, intersegmental distances
and interval overlap from a list of intervals in :term:`gff` or :term:`bed` 
format.

Usage
-----

Example::

   python gff2histogram.py --help

Type::

   python gff2histogram.py --help

for command line help.

Documentation
-------------

Code
----

'''
import sys
import string
import re
import optparse

USAGE="""python %s [OPTIONS] input1 input2

compute simple statistics on the size of features and the 
distance between features in a gff file.

Methods:
  hist: histogram of distance/sizes
  stats: descriptive statistics of distance/sizes
  overlaps: output overlapping features

Version: $Id: gff2histogram.py 2781 2009-09-10 11:33:14Z andreas $
""" % sys.argv[0]

import CGAT.Experiment as E
import CGAT.GFF as GFF
import CGAT.GTF as GTF
import CGAT.Bed as Bed
import CGAT.Histogram as Histogram
import CGAT.Stats as Stats

##------------------------------------------------------------------------
if __name__ == "__main__":

    parser = E.OptionParser( version = "%prog version: $Id: gff2histogram.py 2781 2009-09-10 11:33:14Z andreas $")

    parser.add_option("-b", "--bin-size", dest="bin_size", type="string",
                      help="bin size."  )
    parser.add_option("--min-value", dest="min_value", type="float",
                      help="minimum value for histogram.")
    parser.add_option("--max-value", dest="max_value", type="float",
                      help="maximum value for histogram.")
    parser.add_option("--no-empty-bins", dest="no_empty_bins", action="store_true",
                      help="do not display empty bins.")
    parser.add_option("--with-empty-bins", dest="no_empty_bins", action="store_false",
                      help="display empty bins.")
    parser.add_option("--ignore-out-of-range", dest="ignore_out_of_range", action="store_true",
                      help="ignore values that are out of range (as opposed to truncating them to range border.")
    parser.add_option("--missing", dest="missing_value", type="string",
                      help="entry for missing values [%default]." )
    parser.add_option("--dynamic-bins", dest="dynamic_bins", action="store_true",
                      help="each value constitutes its own bin." )
    parser.add_option( "--format", dest="format", type="choice", 
                       choices=( "gff", "gtf", "bed" ),
                       help="input file format [%default].")
    parser.add_option( "--method", dest="methods", type="choice", action="append",
                       choices=( "all", "hist", "stats", "overlaps", "values" ),
                       help="methods to apply [%default].")
    parser.add_option( "--data", dest="data", type="choice",
                       choices=( "all", "size", "distance" ),
                       help="data to compute [%default].")

    parser.set_defaults(
        no_empty_bins = True,
        bin_size = None,
        dynamic_bins = False,
        ignore_out_of_range = False,
        min_value = None,
        max_value = None,
        nonull = None,
        missing_value = "na",
        output_filename_pattern="%s",
        methods = [],
        data = "all",
        format = "gff",
        )

    (options, args) = E.Start( parser, add_output_options = True )

    if "all" in options.methods:
        options.methods = ("hist", "stats", "overlaps")
        if not options.output_filename_pattern: options.output_filename_pattern = "%s"

    if len(options.methods) == 0:
        raise ValueError( "please provide counting method using --method option" )

    if options.format == "gff":
        gffs = GFF.iterator( options.stdin )
    elif options.format == "gtf":
        gffs = GFF.iterator( options.stdin )
    elif options.format == "bed":
        gffs = Bed.iterator( options.stdin )

    values_between = []
    values_within = []
    values_overlaps = []

    if "overlaps" in options.methods:
        if not options.output_filename_pattern: 
            options.output_filename_pattern = "%s"
        outfile_overlaps = E.openOutputFile( "overlaps" )
    else:
        outfile_overlaps = None

    last = None
    ninput, noverlaps = 0,0
    for this in gffs:
        ninput += 1
        values_within.append( this.end - this.start )

        if last and last.contig == this.contig:
            if this.start < last.end:
                noverlaps += 1
                if outfile_overlaps:
                    outfile_overlaps.write( "%s\t%s\n" % (str(last), str(this)) )
                values_overlaps.append( min(this.end, last.end) - max(last.start, this.start) )
                if this.end > last.end:
                    last = this
                continue
            else:
                values_between.append( this.start - last.end )
                if this.start - last.end < 10: 
                    print str(last)
                    print str(this)
                    print "=="
                values_overlaps.append( 0 )

        last = this

    if "hist" in options.methods:
        outfile = E.openOutputFile( "hist" )
        h_within = Histogram.Calculate( values_within,
                                        no_empty_bins = options.no_empty_bins,
                                        increment = options.bin_size,
                                        min_value = options.min_value,
                                        max_value = options.max_value,
                                        dynamic_bins = options.dynamic_bins,
                                        ignore_out_of_range = options.ignore_out_of_range )

        h_between = Histogram.Calculate( values_between,
                                         no_empty_bins = options.no_empty_bins,
                                         increment = options.bin_size,
                                         min_value = options.min_value,
                                         max_value = options.max_value,
                                         dynamic_bins = options.dynamic_bins,
                                         ignore_out_of_range = options.ignore_out_of_range )

        if "all" == options.data:
            outfile.write( "residues\tsize\tdistance\n" )
            combined_histogram = Histogram.Combine( [h_within, h_between], missing_value = options.missing_value )
            Histogram.Write( outfile, combined_histogram, nonull = options.nonull )        
        elif options.data == "size":
            outfile.write( "residues\tsize\n" )
            Histogram.Write( outfile, h_within, nonull = options.nonull )        
        elif options.data == "distance":
            outfile.write( "residues\tdistance\n" )
            Histogram.Write( outfile, h_between, nonull = options.nonull )        

        outfile.close()

    if "stats" in options.methods:
        outfile = E.openOutputFile( "stats" )
        outfile.write( "data\t%s\n" % Stats.Summary().getHeader() )
        if options.data in ("size", "all"):
            outfile.write( "size\t%s\n" % str(Stats.Summary(values_within)) )
        if options.data in ("distance", "all"):
            outfile.write( "distance\t%s\n" % str(Stats.Summary(values_between)) )
        outfile.close()

    if "values" in options.methods:
        outfile = E.openOutputFile( "distances" )
        outfile.write( "distance\n%s\n" % "\n".join( map(str, values_between) ) )
        outfile.close()
        outfile = E.openOutputFile( "sizes" )
        outfile.write( "size\n%s\n" % "\n".join( map(str, values_within) ) )
        outfile.close()
        outfile = E.openOutputFile( "overlaps" )
        outfile.write( "overlap\n%s\n" % "\n".join( map(str, values_overlaps) ) )
        outfile.close()

    E.info( "ninput=%i, ndistance=%i, nsize=%i, noverlap=%i" % (ninput, 
                                                                len(values_between),
                                                                len(values_within),
                                                                noverlaps) )

    E.Stop()