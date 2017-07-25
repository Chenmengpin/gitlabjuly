"""Functionality to filter input fastq files before further processing.
"""
import os
import subprocess
from contextlib import nested

from Bio.SeqIO.QualityIO import FastqGeneralIterator

from bcbio.utils import memoize_outfile, chdir

@memoize_outfile("-no_ns.fastq")
def remove_ns(in_file, out_file):
    with nested(open(in_file), open(out_file, "w")) as (in_handle, out_handle):
        for name, seq, qual in FastqGeneralIterator(in_handle):
            if seq.find("N") == -1:
                out_handle.write("@%s\n%s\n+\n%s\n" % (name, seq, qual))

def kmer_filter(in_fastq, method, config):
    if method.startswith("shrec"):
        shrec_out = kmer_filter_shrec(in_fastq, method, config)
        return _remove_corrected_shrec(shrec_out)
    else:
        raise ValueError("Unexpected method %s" % method)

@memoize_outfile("-shrec.fastq")
def kmer_filter_shrec(in_fastq, method, config, out_file):
    cl = method.split()
    memory = config.get("algorithm", {}).get("java_memory", "")
    if memory:
        cl.insert(1, "-Xmx%s" % memory)
    dir_name, in_file = os.path.split(in_fastq)
    with chdir(dir_name):
        cl += ["-f", "fastq", in_file, os.path.basename(out_file), "/dev/null"]
        subprocess.check_call(cl)
    return out_file

@memoize_outfile("-fix.fastq")
def _remove_corrected_shrec(in_fastq, out_file):
    """Remove "(corrected)" lines from shrec output which can cause problems.
    """
    to_remove = [" (corrected)", " + (identified)"]
    with nested(open(in_fastq), open(out_file, "w")) as (in_handle, out_handle):
        for line in in_handle:
            for to_rem in to_remove:
                line = line.replace(to_rem, "")
            out_handle.write(line)
