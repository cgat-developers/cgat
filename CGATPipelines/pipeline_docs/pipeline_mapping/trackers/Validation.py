import os
import sys
import re
import types
import itertools

from SphinxReport.Tracker import *
from MappingReport import *


class ExonValidationSummary(MappingTracker, SingleTableTrackerRows):
    table = "exon_validation"
