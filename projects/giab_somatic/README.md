## Somatic truth sets from Genome in a Bottle samples

A mixture of two [Genome in a Bottle](https://github.com/genome-in-a-bottle)
samples -- NA12878 and NA24385 -- to emulate a somatic-like tumor-normal set.
Known calls from these two samples can be used to estimate true and false
positives from somatic variant callers.

NA12878 and NA24385 are from Genome in a Bottle v3.2.1 calls
(ftp://ftp-trace.ncbi.nlm.nih.gov/giab/ftp/release/). `giab_truthset.snakefile`
has the full commands for creating the truth sets.

* VCF truth set
  * https://s3.amazonaws.com/biodata/giab/na24385/na12878-na24385-somatic-truth.vcf.gz,
  * https://s3.amazonaws.com/biodata/giab/na24385/na12878-na24385-somatic-truth.vcf.gz.tbi

* Callable regions
  * https://s3.amazonaws.com/biodata/giab/na24385/na12878-na24385-somatic-truth-regions.bed.gz
