#!/usr/bin/env python
"""Prepare Illumina called variants, merging into single sample GATK-compatible VCFs.

Usage:
  illumina_variant_prep.py <in config> <cores>
"""
import csv
import glob
import gzip
import pprint
import os
import shutil
import subprocess
import sys

import yaml

import joblib

from bcbio import broad, utils
from bcbio.variation import effects, population, vcfutils

def main(config_file, env, cores):
    cores = int(cores)
    config = read_config(config_file, env)
    idremap = read_remap_file(config["runinfo"]["idmapping"])
    exclude = read_priority_file(config["runinfo"]["priority"], idremap)
    samples = list(get_input_samples(config["inputs"], idremap))
    problem = [x for x in samples if x["id"] is None]
    if len(problem) > 0:
        print "Problem identifiers"
        for p in problem:
            print p["illuminaid"], os.path.basename(p["dir"])
        raise NotImplementedError
    check_fam(samples, config["runinfo"]["fam"])

    config["algorithm"] = {"num_cores": cores}
    samples = [s for s in samples if s["id"] is not None and s["id"] not in exclude]
    print "Processing %s samples" % len(samples)
    out_files = [outf for outf in joblib.Parallel(cores)(joblib.delayed(run_illumina_prep)(s, config)
                                                         for s in samples)]
    merge_file = merge_vcf_files(out_files, cores, config)
    effects_file = effects.snpeff_effects({"vrn_file": merge_file,
                                           "sam_ref": config["ref"]["GRCh37"],
                                           "reference": {"fasta" : {"base": config["ref"]["GRCh37"]}},
                                           "genome_resources": {"aliases" : {"snpeff": "GRCh37.74"}},
                                           "genome_build": "GRCh37",
                                           "config": config})
    data = {"config": config, "dirs": {"work": os.getcwd()}, "name": [""]}
    gemini_db = population.prep_gemini_db([os.path.join(os.getcwd(), effects_file)],
                                          [utils.splitext_plus(config["outputs"]["merge"])[0], "casava", True],
                                          [{"config": config, "work_bam": "yes", "genome_build": "GRCh37",
                                            "genome_resources": {"aliases": {"human": True}}}],
                                          data)[0][1]["db"]
    print gemini_db
    noexclude_file = "%s-noexclude%s" % utils.splitext_plus(effects_file)
    noexclude_file = vcfutils.exclude_samples(effects_file, noexclude_file, exclude,
                                              config["ref"]["GRCh37"], config)
    prepare_plink_vcftools(noexclude_file, config)

def merge_vcf_files(sample_files, cores, config):
    out_file = config["outputs"]["merge"]
    sample_file_list = "merge-samples.txt"
    with open(sample_file_list, "w") as out_handle:
        for f in sample_files:
            out_handle.write("%s\n" % f)
    if not utils.file_exists(out_file):
        subprocess.check_call(["bcbio-variation-recall", "merge", out_file, config["ref"]["GRCh37"],
                               sample_file_list, "-c", str(cores)])
    return out_file

def _remove_plink_problems(in_file):
    """Remove lines which cause issues feeding into plink.
    """
    chr_remap = {"X": "23", "Y": "24"}
    out_vcf = "%s-plinkready.vcf" % utils.splitext_plus(in_file)[0]
    support_chrs = set(["G", "A", "T", "C", ","])
    if utils.file_exists(out_vcf + ".gz"):
        out_vcf = out_vcf + ".gz"
    if not utils.file_exists(out_vcf):
        with (gzip.open(in_file) if in_file.endswith(".gz") else open(in_file)) as in_handle:
            with open(out_vcf, "w") as out_handle:
                for line in in_handle:
                    # Mitochondrial calls are not called with
                    # same reference, causing plink conversion errors
                    if line.startswith("MT"):
                        line = None
                    # Remap sex chromosomes to plink binary numbering
                    elif line.startswith(tuple(chr_remap.keys())):
                        line = chr_remap[line[0]] + line[1:]
                    elif not line.startswith("#"):
                        parts = line.split("\t", 7)
                        if parts[6] not in set(["PASS", "."]):
                            line = None
                        else:
                            for to_check in parts[3:5]:
                                # Exclude non-GATC inputs
                                if len(set(to_check) - support_chrs) > 0:
                                    line = None
                                    break

                    if line:
                        out_handle.write(line)
    return out_vcf

def vcftools_vcf_to_tped(in_vcf, base_dir, chromosome, config):
    """Use VCFtools to convert a single chromosome into a tped file.
    """
    out_base = os.path.join(base_dir, "%s-%s" % (config["outputs"]["plink"], chromosome))
    out_tped = out_base + ".tped"
    if not utils.file_exists(out_tped):
        subprocess.check_call(["vcftools", "--plink-tped", "--gzvcf", in_vcf,
                               "--chr", str(chromosome), "--out", out_base])
    return out_tped

def _merge_tped_tfam(fnames, out_base, config):
    """Merge all tped files together and copy over fam lines by samples to tfam.
    """
    tped_file = "%s-transposed.tped" % out_base
    if not utils.file_exists(tped_file):
        with open(tped_file, "w") as out_handle:
            for fname in fnames:
                with open(fname) as in_handle:
                    for line in in_handle:
                        out_handle.write(line)
    tfam_file = "%s.tfam" % utils.splitext_plus(tped_file)[0]
    if not utils.file_exists(tfam_file):
        fam_lines = {}
        with open(config["runinfo"]["fam"]) as in_handle:
            for line in in_handle:
                fam_lines[line.split()[1]] = line
        with open(tfam_file, "w") as out_handle:
            base_tfam = "%s.tfam" % utils.splitext_plus(fnames[0])[0]
            with open(base_tfam) as in_handle:
                for line in in_handle:
                    out_line = fam_lines[line.split()[1]]
                    out_handle.write(out_line)
    return tped_file, tfam_file

def _plink_transposed_to_bed(tped_file, tfam_file, out_base):
    """Generate finalize binary PED files from tped and tfam inputs.
    """
    out_file = "%s.bed"
    if not utils.file_exists(out_file):
        subprocess.check_call(["plink", "--tped", tped_file, "--tfam", tfam_file,
                               "--make-bed", "--out", out_base])
    return out_file

def prepare_plink_vcftools(in_vcf, config):
    """Prepare binary PED files using vcftools and plink.
    """
    clean_vcf = _remove_plink_problems(in_vcf)
    bgzip_vcf = vcfutils.bgzip_and_index(clean_vcf, config)
    out_base = os.path.join(os.path.dirname(in_vcf), config["outputs"]["plink"])
    parts_dir = utils.safe_makedir(out_base + "-chromosomes")
    cores = config["algorithm"]["num_cores"]
    out_files = list(joblib.Parallel(cores)(joblib.delayed(vcftools_vcf_to_tped)
                                            (bgzip_vcf, parts_dir, c, config) for c in range(1, 25)))
    tped_file, tfam_file = _merge_tped_tfam(out_files, out_base, config)
    return _plink_transposed_to_bed(tped_file, tfam_file, out_base)

def prepare_plink_gatk(in_vcf, config):
    """Prepare binary PED files for input to plink using GATK walkers.

    XXX Does not produce valid binary PED files for large numbers of input samples.
    """
    clean_vcf = _remove_plink_problems(in_vcf)
    runner = broad.runner_from_config(config)
    out_base = os.path.join(os.path.dirname(in_vcf), config["outputs"]["plink"])
    args = ["-T", "VariantsToBinaryPed", "-R", config["ref"]["GRCh37"],
            "--variant", clean_vcf, "--minGenotypeQuality", "0",
            "--metaData", config["array"]["fam"],
            "--bed", out_base + ".bed", "--bim", out_base + ".bim", "--fam", out_base + ".fam"]
    runner.run_gatk(args)
    print out_base

def check_fam(samples, fam_file):
    """Ensure identifiers are present in PLINK fam file.
    """
    fam_samples = set([])
    with open(fam_file) as in_handle:
        for line in in_handle:
            fam_samples.add(line.split()[1].strip())
    missing_ids = []
    for sample in samples:
        if sample["id"] not in fam_samples:
            missing_ids.append(sample["id"])
    with open("missing_fam_sample_ids.txt", "w") as out_handle:
        for x in sorted(missing_ids):
            out_handle.write("%s\n" % x)

def read_priority_file(in_file, idremap):
    """Read priority and failed information from input files.
    """
    exclude = []
    with open(in_file) as in_handle:
        reader = csv.reader(in_handle)
        header = reader.next()
        #for i, h in enumerate(header):
        #    print i, h
        for parts in reader:
            rutgers_id = parts[0]
            subject_id = parts[2]
            status_flag = parts[16]
            remap_s_id = idremap.get(rutgers_id)
            if status_flag == "Exclude":
                # if remap_s_id != subject_id:
                #     print rutgers_id, remap_s_id, subject_id
                #     print parts
                exclude.append(subject_id)
            else:
                assert status_flag in ["Use", "QC"], status_flag
    return set(exclude)

def run_illumina_prep(sample, config):
    work_dir = utils.safe_makedir(os.path.join(os.getcwd(), "prep_casava_calls"))
    with utils.chdir(work_dir):
        out_file = os.path.join(os.getcwd(), "%s.vcf" % sample["id"])
        if not os.path.exists(out_file) and not os.path.exists(out_file + ".gz"):
            print sample["id"], sample["dir"], out_file
            tmp_dir = utils.safe_makedir(config.get("tmpdir", os.getcwd()))
            subprocess.check_call(["java", "-Xms1g", "-Xmx2g", "-jar", config["bcbio.variation"],
                                   "variant-utils", "illumina", sample["dir"],
                                   sample["id"], config["ref"]["GRCh37"],
                                   config["ref"]["hg19"],
                                   "--types", "snp,indel",
                                   "--outdir", os.getcwd(),
                                   "--tmpdir", tmp_dir])
    return out_file

def dir_to_sample(dname, idremap):
    vcf_file = os.path.join(dname, "Variations", "SNPs.vcf")
    with open(vcf_file) as in_handle:
        for line in in_handle:
            if line.startswith("#CHROM"):
                illumina_id = line.split("\t")[-1].replace("_POLY", "").rstrip()
                return {"id": idremap.get(illumina_id), "dir": dname,
                        "illuminaid": illumina_id}
    raise ValueError("Did not find sample information in %s" % vcf_file)

def get_input_samples(fpats, idremap):
    for fpat in fpats:
        for dname in glob.glob(fpat):
            if os.path.isdir(dname):
                yield dir_to_sample(dname, idremap)

def read_remap_file(in_file):
    out = {}
    with open(in_file) as in_handle:
        in_handle.next() # header
        for line in in_handle:
            patient_id, illumina_id = line.rstrip().split()
            out[illumina_id] = patient_id
    return out

def read_config(config_file, env):
    with open(config_file) as in_handle:
        config = yaml.load(in_handle)
        config = _add_env_kvs(config, env)
        config = _add_base_dir(config, config["base_dir"], "runinfo")
        config = _add_base_dir(config, config["ref_base_dir"], "ref")
        config = _add_org_dir(config, config["app_dir"])
    return config

def _add_env_kvs(config, env):
    """Add key values specific to the running environment.
    """
    for k, val in config[env].iteritems():
        config[k] = val
    return config

def _add_base_dir(config, base_dir, top_key):
    for k, v in config[top_key].iteritems():
        config[top_key][k] = os.path.join(base_dir, v)
    return config

def _add_org_dir(config, base_dir):
    for name, opts in config["resources"].iteritems():
        for k, v in opts.iteritems():
            if k == "dir":
                config["resources"][name][k] = os.path.join(base_dir, v)
    return config

if __name__ == "__main__":
    main(*sys.argv[1:])
