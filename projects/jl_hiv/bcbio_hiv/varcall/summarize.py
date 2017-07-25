"""Utilities to help summarize variation statistics.
"""

import collections

def print_summary_counts(info):
    names = ["single", ">=5%", "<5%"]
    selects = [lambda x: x["percent"] == 100.0,
               lambda x: x["percent"] < 100.0 and x["percent"] >= 5.0,
               lambda x: x["percent"] < 5.0]
    print "*** quality: %s, kmer %s, align score %s" % (info["qual"], info["kmer"],
                                                        info["align_score"])
    print "| % 8s | % 12s | % 12s |" % ("", "Correct", "Wrong")
    print "|%s+%s+%s|" % ("-" * 10, "-" * 14, "-" * 14)
    for name, select in zip(names, selects):
        vals = collections.defaultdict(int)
        for d in filter(select, info["calls"]):
            for k, v in d.iteritems():
                if k != "percent":
                    vals[k] += v
        total = float(sum(vals.values()))
        right = vals["correct"]
        wrong = vals["wrong"] + vals["partial"]
        print "| % 8s | % 4s (%.1f%%) | % 3s (%.1f%%) |" % \
              (name, right, right / total * 100.0, wrong, wrong / total * 100.0)

