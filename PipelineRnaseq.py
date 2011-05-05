################################################################################
#
#   MRC FGU Computational Genomics Group
#
#   $Id: PipelineGO.py 2877 2010-03-27 17:42:26Z andreas $
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
"""
=====================================
Rnaseq.py - Tools for RNAseq analysis
=====================================

:Author: Andreas Heger
:Release: $Id$
:Date: |today|
:Tags: Python

Purpose
-------

Pipeline components - GO analysis

Tasks related to gene set GO analysis.

Usage
-----

Type::

   python <script_name>.py --help

for command line help.

Code
----


"""

import Experiment as E
import logging as L
import Database, CSV

import sys, os, re, shutil, itertools, math, glob, time, gzip, collections, random

import numpy, sqlite3
import GTF, IOTools, IndexedFasta
from rpy2.robjects import r as R
import rpy2.robjects as ro
import rpy2.robjects.vectors as rovectors
import rpy2.rinterface as ri

import Pipeline as P

try:
    PARAMS = P.getParameters()
except IOError:
    pass

def buildUTRExtensions( infile, outfile ):
    '''build new utrs by building and fitting an HMM 
    to reads upstream and downstream of known genes.

    Works on output of buildGeneLevelReadExtension.

    Known problems
    --------------

    * the size of the extension is limited by the window size

    * introns within UTRs are ignored.

    * UTR extension might be underestimated for highly expressed genes
      as relative read counts drop off quickly, even though there is
      a good amount of reads still present in the UTR.

    The model
    ---------

    The model is a three-state model:

    UTR --|--> notUTR --|--> otherTranscript --|
      ^---|      ^------|              ^-------|
                 ^-----------------------------|

    The chain starts in UTR and ends in notUTr or otherTranscript.

    The otherTranscript state models peaks of within the upstream/
    downstream region of a gene. These peaks might correspond to
    additional exons or unknown transcripts. Without this state,
    the UTR might be artificially extend to include these peaks.

    Emissions are modelled with beta distributions. These
    distributions permit both bimodal (UTR) and unimodal (notUTR)
    distribution of counts.

    Parameter estimation
    --------------------

    Parameters are derived from known UTRs within full length 
    territories.
    
    Transitions and emissions for the otherTranscript state
    are set heuristically:
       * low probabibily for remaining in state "otherTranscript".
           * these transcripts should be short.

       * emissions biased towards high counts - only strong signals
           will be considered.

       * these could be estimated from known UTRs, but I am worried
           UTR extensions then will be diluted.
    

    Alternatives
    ------------

    The method could be improved.

        * base level resolution? 
            * longer chains result in more data and longer running times.
            * the averaging in windows smoothes the data, which might have
                a beneficial effect.

        * raw counts instead of scaled counts?
            * better model, as highly expressed genes should give more
                confident predictions.

    '''
    
    # the bin size , see gtf2table - can be cleaned from column names
    # or better set as options in .ini file
    binsize = 100
    territory_size = 15000

            
    # read gene coordinates
    geneinfos = {}
    for x in CSV.DictReader( IOTools.openFile( infile ), dialect='excel-tab' ):
        contig, strand, start, end = x['contig'], x['strand'], int(x['start']), int(x['end'] )
        geneinfos[x['gene_id']] = ( contig, strand,
                                    start, end )

    infiles = [infile + ".readextension_upstream_sense.tsv.gz",
               infile + ".readextension_downstream_sense.tsv.gz" ]

    outdir = os.path.join( PARAMS["exportdir"], "utr_extension" )
    
    R('''suppressMessages(library(RColorBrewer))''')
    R('''suppressMessages(library(MASS))''')
    R('''suppressMessages(library(HiddenMarkov))''')

    # for upstream, downstream
    upstream_utrs, downstream_utrs = {}, {}

    all_genes = set()

    for filename, new_utrs in zip(infiles, (upstream_utrs, downstream_utrs)):

        E.info("processing %s" % filename)

        parts = os.path.basename(filename).split( "." )

        data = R('''data = read.table( gzfile( "%(filename)s"), header=TRUE, fill=TRUE, row.names=1)''' % locals() )

        ##########################################
        ##########################################
        ##########################################
        ## estimation
        ##########################################
        # take only those with a 'complete' territory
        R('''d = data[-which( apply( data,1,function(x)any(is.na(x)))),]''')
        # save UTR
        R('''utrs = d$utr''' )
        # remove length and utr column
        R('''d = d[-c(1,2)]''')
        # remove those which are completely empty, logtransform or scale data and export
        R('''lraw = log10( d[-which( apply(d,1,function(x)all(x==0))),] + 1 )''')

        utrs = R('''utrs = utrs[-which( apply(d,1,function(x)all(x==0)))]''' )
        scaled = R('''lscaled = t(scale(t(lraw), center=FALSE, scale=apply(lraw,1,max) ))''' )
        exons = R('''lraw[,1]''')

        #######################################################
        #######################################################
        #######################################################
        # do the estimation: 
        E.debug( "estimation: utrs=%i, exons=%i, vals=%i, dim=%s" % (len(utrs), len(exons), len(scaled), R.dim(scaled)) )
        # counts within and outside UTRs
        within_utr, outside_utr, otherTranscript = [], [], []
        # number of transitions between utrs
        transitions = numpy.zeros( (3,3), numpy.int )
        
        for x in xrange( len( utrs ) ):
            utr, exon = utrs[x], exons[x]

            # only consider genes with expression coverage of 10 or more.
            # note: expression level is logscaled here, 10^1 = 10
            if exon < 1: continue
            
            # first row is column names, so x + 1
            values = list(scaled.rx(x+1, True))
            
            utr_bins = utr // binsize
            nonutr_bins = (territory_size - utr) // binsize

            # build transition matrix
            transitions[0][0] += utr_bins
            transitions[0][1] += 1
            transitions[1][1] += nonutr_bins
            
            outside_utr.extend( values[utr_bins:] )

            # ignore exon and zero counts
            within_utr.extend( [ x for x in values[1:utr_bins] if x > 0.1 ] )

            # add only high counts to otherTranscript emissions
            otherTranscript.extend( [ x for x in values[utr_bins:] if x > 0.5 ] )

        # estimation for 
        # 5% chance of transiting to otherTranscript
        transitions[1][2] = transitions[1][1] * 0.05
        # 10% chance of remaining in otherTranscript
        transitions[2][1] = 900
        transitions[2][2] = 100
        
        E.info( "counting: (n,mean): within utr=%i,%f, outside utr=%i,%f, otherTranscript=%i,%f" % \
                    ( len(within_utr), numpy.mean(within_utr),
                      len(outside_utr), numpy.mean(outside_utr),
                      len(otherTranscript), numpy.mean(otherTranscript)) )
        
        ro.globalenv['transitions'] = R.matrix( transitions, nrow=3, ncol=3 )
        R('''transitions = transitions / rowSums( transitions )''')
        ro.globalenv['within_utr'] = ro.FloatVector(within_utr[:10000])
        ro.globalenv['outside_utr'] = ro.FloatVector(outside_utr[:10000])
        ro.globalenv['otherTranscript'] = ro.FloatVector(otherTranscript[:10000])
        
        # estimate beta distribution parameters
        R('''doFit = function( data ) {
                   data[data == 0] = data[data == 0] + 0.001
                   data[data == 1] = data[data == 1] - 0.001
                   f = fitdistr( data, dbeta, list( shape1=0.5, shape2=0.5 ) )
                   return (f) }''' )

        fit_within_utr = R('''fit_within_utr = suppressMessages(doFit( within_utr))''' )
        fit_outside_utr = R('''fit_outside_utr = suppressMessages(doFit( outside_utr))''' )
        fit_other = R('''fit_otherTranscript = suppressMessages(doFit( otherTranscript))''' )

        within_a, within_b = list(fit_within_utr.rx("estimate"))[0]
        outside_a, outside_b = list(fit_outside_utr.rx("estimate"))[0]
        other_a, other_b = list(fit_other.rx("estimate"))[0]

        E.info( "beta estimates: within_utr=%f,%f outside=%f,%f, other=%f,%f" % \
                    (within_a, within_b, outside_a, outside_b, other_a, other_b))

        fn = ".".join( (parts[0], parts[4], "fit", "png") )
        outfilename = os.path.join( outdir, fn )
        R.png( outfilename, height=1000, width=1000 )
        
        R( '''par(mfrow=c(3,1))''' )
        R( '''x=seq(0,1,0.02)''')
        R( '''hist( within_utr, 50, col=rgb( 0,0,1,0.2) )''' )
        R( '''par(new=TRUE)''')
        R( '''plot( x, dbeta( x, fit_within_utr$estimate['shape1'], fit_within_utr$estimate['shape2']), type='l', col='blue')''')

        R( '''hist( outside_utr, 50, col=rgb( 1,0,0,0.2 ) )''' )
        R( '''par(new=TRUE)''')
        R( '''plot( x, dbeta( x, fit_outside_utr$estimate['shape1'], fit_outside_utr$estimate['shape2']), type='l', col='red')''')

        R( '''hist( otherTranscript, 50, col=rgb( 0,1,0,0.2 ) )''' )
        R( '''par(new=TRUE)''')
        R( '''plot( x, dbeta( x, fit_otherTranscript$estimate['shape1'], fit_otherTranscript$estimate['shape2']), type='l', col='green')''')
        R['dev.off']()

        #####################################################
        #####################################################
        #####################################################
        # build hmm
        # state 1 = UTR
        # state 2 = notUTR
        p = R('''betaparams = list( shape1=c(fit_within_utr$estimate['shape1'],
                                         fit_outside_utr$estimate['shape1'],
                                         fit_otherTranscript$estimate['shape1']),
                                shape2=c(fit_within_utr$estimate['shape2'],
                                         fit_outside_utr$estimate['shape2'],
                                         fit_otherTranscript$estimate['shape2'])) ''')
        R('''hmm = dthmm(NULL, transitions, c(1,0,0), "beta", betaparams )''' )

        E.info( "fitting starts" )
        #####################################################
        #####################################################
        #####################################################
        # fit to every sequence
        genes = R('''rownames(data)''')
        all_genes.update( set(genes))
        utrs = R('''data$utr''')
        exons = R('''data$exon''')
        nseqs = len(utrs)

        counter = E.Counter()
        for x in xrange(len(utrs)):
            if x % 100 == 0: 
                E.debug( "processing gene %i/%i" % (x,len(utrs)))

            counter.input += 1

            # do not predict if terminal exon not expressed
            if exons[x] < 1: 
                counter.skipped_notexpressed += 1
                continue                

            R('''obs = data[%i,][-c(1,2)]''' % (x+1) )
            # remove na
            obs = R('''obs = obs[!is.na(obs)]''' )
            if len(obs) <= 1 or max(obs) == 0: continue
            
            # normalize
            R('''obs = obs / max(obs)''')
            # add small epsilon to 0 and 1 values
            R('''obs[obs==0] = obs[obs==0] + 0.001 ''')
            R('''obs[obs==1] = obs[obs==1] - 0.001 ''')
            R('''hmm$x = obs''')

            try:
                states = list(R('''states = Viterbi( hmm )'''))
            except ri.RRuntimeError, msg:
                counter.skipped_error += 1
                continue

            # subtract 1 for last exon
            try:
                new_utr = binsize * (states.index(2) - 1)
            except ValueError:
                new_utr = binsize * (len( states ) - 1)
            
            counter.success += 1
            gene_id = genes[x]
            old_utr = utrs[x]
            max_utr = binsize * (len(states) -1)
            new_utrs[gene_id] = (old_utr, new_utr, max_utr )

    E.info( "fitting: %s" % str(counter))
    
    outf = IOTools.openFile( outfile, "w" )
    
    outf.write( "\t".join( ["gene_id", "contig", "strand",]+
                           [ "%s_%s_%s" % (x,y,z) for x,y,z in itertools.product( \
                    ("old", "new", "max"),
                    ("5utr", "3utr"),
                    ("length", "start", "end" ) ) ] ) + "\n" )

    def _write( coords, strand ):
        
        start5, end5, start3, end3 = coords
        if strand == "-":
            start5, end5, start3, end3 = start3, end3, start5, end5
            
        if start5 == None: start5, end5, l5 = "", "", ""
        else: l5 = end5-start5

        if start3 == None: start3, end3, l3 = "", "", ""
        else: l3 = end3-start3

        return "\t".join(map(str, (l5,start5,end5,
                                   l3,start3,end3) ) )
        
    def _buildCoords( upstream, downstream, start, end ):
        
        r = []
        if upstream: start5, end5 = start - upstream, start
        else: start5, end5 = None, None
        if downstream: start3, end3 = end, end + downstream
        else: start3, end3 = None, None
        
        return start5, end5, start3, end3

    for gene_id in all_genes:
        contig, strand, start, end = geneinfos[gene_id]
        outf.write( "%s\t%s\t%s" % (gene_id, contig, strand) )

        if gene_id in upstream_utrs: upstream = upstream_utrs[gene_id]
        else: upstream = (None,None,None)
        if gene_id in downstream_utrs: downstream = downstream_utrs[gene_id]
        else: downstream = (None,None,None)

        if strand == "-": upstream, downstream = downstream, upstream

        # build upstream/downstream coordinates
        old_coordinates = _buildCoords( upstream[0], downstream[0], start, end ) 
        new_coordinates = _buildCoords( upstream[1], downstream[1], start, end ) 

        # reconciled = take maximum extension of UTR
        max_coordinates = []
        # note that None counts as 0 in min/max.
        for i,d in enumerate( zip( old_coordinates, new_coordinates )):
            if i % 2 == 0:
                v = [ z for z in d if z != None ]
                if v: max_coordinates.append( min( v ) )
                else: max_coordinates.append( None )
            else:
                max_coordinates.append( max( d ) )

        # convert to 5'/3' coordinates
        outf.write( "\t%s\t%s\t%s\n" % ( _write( old_coordinates, strand ),
                                         _write( new_coordinates, strand ),
                                         _write( max_coordinates, strand ) ) )
        
    outf.close()

#########################################################################
#########################################################################
#########################################################################
def plotGeneLevelReadExtension( infile, outfile ):
    '''plot reads extending beyond last exon.'''

    infiles = glob.glob( infile + ".*.tsv.gz" )

    outdir = os.path.join( PARAMS["exportdir"], "utr_extension" )
    
    R('''suppressMessages(library(RColorBrewer))''')
    R('''suppressMessages(library(MASS))''')
    R('''suppressMessages(library(HiddenMarkov))''')

    # the bin size , see gtf2table - could be cleaned from column names
    binsize = 100
    territory_size = 15000

    for filename in infiles:

        E.info("processing %s" % filename)

        parts = os.path.basename(filename).split( "." )

        data = R('''data = read.table( gzfile( "%(filename)s"), header=TRUE, fill=TRUE, row.names=1)''' % locals() )

        ##########################################
        ##########################################
        ##########################################
        ## estimation
        ##########################################
        # take only those with a 'complete' territory
        R('''d = data[-which( apply( data,1,function(x)any(is.na(x)))),]''')
        # save UTR
        R('''utrs = d$utr''' )
        # remove length and utr column
        R('''d = d[-c(1,2)]''')
        # remove those which are completely empty, logtransform or scale data and export
        R('''lraw = log10( d[-which( apply(d,1,function(x)all(x==0))),] + 1 )''')

        utrs = R('''utrs = utrs[-which( apply(d,1,function(x)all(x==0)))]''' )
        scaled = R('''lscaled = t(scale(t(lraw), center=FALSE, scale=apply(lraw,1,max) ))''' )
        exons = R('''lraw[,1]''')

        #######################################################
        #######################################################
        #######################################################
        R('''myplot = function( reads, utrs, ... ) {
           oreads = t(data.matrix( reads )[order(utrs), ] )
           outrs = utrs[order(utrs)]
           image( 1:nrow(oreads), 1:ncol(oreads), oreads ,
                  xlab = "", ylab = "",
                  col=brewer.pal(9,"Greens"),
                  axes=FALSE)
           # axis(BELOW<-1, at=1:nrow(oreads), labels=rownames(oreads), cex.axis=0.7)
           par(new=TRUE)
           plot( outrs, 1:length(outrs), yaxs="i", xaxs="i", 
                 ylab="genes", xlab="len(utr) / bp", 
                 type="S", 
                 xlim=c(0,nrow(oreads)*%(binsize)i))
        }''' % locals())


        fn = ".".join( (parts[0], parts[4], "raw", "png") )
        outfilename = os.path.join( outdir, fn )

        R.png( outfilename, height=2000, width=1000 )
        R('''myplot( lraw, utrs )''' )
        R['dev.off']()

        # plot scaled data
        fn = ".".join( (parts[0], parts[4], "scaled", "png") )
        outfilename = os.path.join( outdir, fn )

        R.png( outfilename, height=2000, width=1000 )
        R('''myplot( lscaled, utrs )''' )
        R['dev.off']()
    
