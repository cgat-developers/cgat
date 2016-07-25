##########################################################################
#
#   MRC FGU Computational Genomics Group
#
#   $Id: cgat_script_template.py 2871 2010-03-03 10:20:44Z andreas $
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
##########################################################################
'''
Logfile.py - logfile parsing
============================

:Author: Andreas Heger
:Release: $Id$
:Date: |today|
:Tags: Python

Purpose
-------

Parse logfiles

Usage
-----

Example::

   python cgat_script_template.py --help

Type::

   python cgat_script_template.py --help

for command line help.

Documentation
-------------

Code
----

'''

import collections
import re

RuntimeInformation = collections.namedtuple(
    "RuntimeInformation",
    "script options jobid host has_finished " +
    "start_date end_date " +
    "wall utime stime cutime cstime")

RX_START = re.compile("output generated by (\S+) (.*)")
RX_JOB = re.compile("job started at (.*) on (\S+) -- (\S+)")
RX_FINISH = re.compile(
    "job finished in (\S+) seconds at (.*) --\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+) -- (\S+)")


def parse(filename):

    results = []
    script, options, started, finished, host, jobid = "", "", "?", "?", "?", "?"
    wall, utime, stime, cutime, cstime = [0] * 5
    with open(filename) as inf:
        for line in inf:
            x = RX_START.search(line)
            if x:
                if script:
                    results.append(RuntimeInformation._make((
                        script, options,
                        jobid, host,
                        finished != "",
                        started, finished,
                        int(wall), float(utime), float(stime), float(cutime), float(cstime))))
                script, options, started, finished, host, jobid = "", "", "?", "?", "?", ""
                wall, utime, stime, cutime, cstime = [0] * 5
                script, options = x.groups()
                continue
            x = RX_JOB.search(line)
            if x:
                started, host, jobid = x.groups()
                continue
            x = RX_FINISH.search(line)
            if x:
                wall, finished, utime, stime, cutime, cstime, _jobid = x.groups(
                )
                assert _jobid == jobid

    results.append(RuntimeInformation._make((
        script, options,
        jobid, host,
        finished != "",
        started, finished,
        int(wall), float(utime), float(stime), float(cutime), float(cstime))))

    return results


class LogFileData:
    mRegex = re.compile(
        "# job finished in (\d+) seconds at (.*) --\s+([.\d]+)\s+([.\d]+)\s+([.\d]+)\s+([.\d]+)")
    mFormat = "%6.2f"
    mDivider = 1.0

    def __init__(self):

        self.mWall = 0
        self.mUser = 0
        self.mSys = 0
        self.mChildUser = 0
        self.mChildSys = 0
        self.mNChunks = 0

    def add(self, line):

        if not self.mRegex.match(line):
            return
        t_wall, date, t_user, t_sys, t_child_user, t_child_sys = self.mRegex.match(
            line).groups()

        self.mWall += int(t_wall)
        self.mUser += float(t_user)
        self.mSys += float(t_sys)
        self.mChildUser += float(t_child_user)
        self.mChildSys += float(t_child_sys)
        self.mNChunks += 1

    def __getitem__(self, key):

        if key == "wall":
            return self.mWall
        elif key == "user":
            return self.mUser
        elif key == "sys":
            return self.mSys
        elif key == "cuser":
            return self.mChildUser
        elif key == "csys":
            return self.mChildSys
        elif key == "nchunks":
            return self.mNChunks
        else:
            raise ValueError("key %s not found" % key)

    def __add__(self, other):

        self.mWall += other.mWall
        self.mUser += other.mUser
        self.mSys += other.mSys
        self.mChildUser += other.mChildUser
        self.mChildSys += other.mChildSys
        self.mNChunks += other.mNChunks

        return self

    def __str__(self):

        return "%i\t%s" % (
            self.mNChunks,
            "\t".join([self.mFormat % (float(x) / self.mDivider) for x in (
                self.mWall, self.mUser, self.mSys,
                self.mChildUser, self.mChildSys)]))

    def getHeader(self):
        return "\t".join(("chunks", "wall", "user", "sys", "cuser", "csys"))


class LogFileDataLines(LogFileData):

    """record lines."""

    def __init__(self):
        LogFileData.__init__(self)
        self.mNLines = 0

    def add(self, line):
        if line[0] != "#":
            self.mNLines += 1
        else:
            return LogFileData.add(self, line)

    def __getitem__(self, key):
        if key == "lines":
            return self.mNLines
        else:
            return LogFileData.__getitem__(self, key)

    def __add__(self, other):
        self.mNLines += other.mNLines
        return LogFileData.__add__(self, other)

    def __str__(self):
        return "%s\t%i" % (LogFileData.__str__(self), self.mNLines)

    def getHeader(self):
        return "%s\t%s" % (LogFileData.getHeader(self), "lines")
