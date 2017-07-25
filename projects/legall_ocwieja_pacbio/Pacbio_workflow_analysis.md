# Generation of potential proteins using Pacbio data from the Ocwieja paper

## Downloading Pacbio Consensus Reads

Script to download data from SRA website uses a text file with the FTP site for each sample as a line in the file. Use script to download the data for each line in the file (sample)

```bash
while IFS='' read -r line || [[ -n "$line" ]]; do
    wget $line
done < "$1"
```

From the SRA files, extract the FASTA sequences of the consensus reads. More information about the code can be found at http://seqanswers.com/forums/archive/index.php/t-58456.html

```bash
for sra in *.sra; do ~/tools/sratoolkit.2.7.0-centos_linux64/bin/fastq-dump.2.7.0 --fasta $sra; done
```

Combine all fasta files together into a single file for alignment since we do not care about where the sequence came from.

```bash
cat "names of all fasta files"
```

## Filtering the Pacbio sequences for length and contamination with RT primer

Remove sequences less than 40 nucleotides and sequences matching the RT primer similar to the Ocwieja paper (Ocwieja protocol removed sequences with subreads less than 100nt - these should have been removed prior to generation of the consensus reads, so we do not need to perform this step)

```bash
module load seq/fastx/0.0.13 

fasta_formatter -i SRR528772.fasta -w 10000 | fastx_clipper -l 40

fastx_clipper -a CTCCACACTAACACTTGTCTCTCCG #RTPrime
```

## Align Pacbio reads

Align consensus reads against HIV strain 89.6 reference and human reference using STAR. STAR is the recommended aligner by PacBio as detailed [here](https://github.com/PacificBiosciences/cDNA_primer/wiki/Bioinfx-study:-Optimizing-STAR-aligner-for-Iso-Seq-data). However, GMAP is the aligner used in the Pacbio pipeline.

During alignment, we mapped to human and HIV at the same time to identify human contamination for removal. To perform alignment, gene annotation files were not used since it was not important that we receive the best human alignment, we only needed to know if the reads align to human or not. HIV strain 89.6 doesn't have a well-annotated genome, and our goal was to identify non-annotated junctions, so we did not include the annotation file for human or HIV. 

We used parameters suggested for aligning Pacbio reads using STAR from the [Pacbio recommendations](https://github.com/PacificBiosciences/cDNA_primer/wiki/Bioinfx-study:-Optimizing-STAR-aligner-for-Iso-Seq-data). In addition, to the suggested parameters, the thresholds were relaxed for identifying splice junctions, including the number of unique reads per splice junction (a single read for any junction type) and minimum overhang (nine nucleotides for all junctions). By relaxing these parameters, it is understood that many junctions may be false positives.

```bash
## Generating index for combined human and HIV genomes

module load seq/STAR/2.5.2b

STARlong \
--runThreadN 6 \
--runMode genomeGenerate \
--genomeDir /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/index \
--genomeFastaFiles /groups/shared_databases/igenome/Homo_sapiens/Ensembl/GRCh37/Sequence/WholeGenomeFasta/genome.fa /n/data1/cores/bcbio/legall_hiv_pacbio/references/hiv.U39362.fa

## Performing alignment 

module load seq/STAR/2.5.2b

STARlong \
--runThreadN 6 \
--runMode alignReads \
--genomeDir /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/index \
--readFilesIn /n/data1/cores/bcbio/legall_hiv_pacbio/QC/filtered_ccs.fasta \
--outSAMattributes NH HI NM MD \
--readNameSeparator space \
--outFilterMultimapScoreRange 1 \
--outFilterMismatchNmax 2000 \
--scoreGapNoncan -20 \
--scoreGapGCAG -4 \
--scoreGapATAC -8 \
--scoreDelOpen -1 \
--scoreDelBase -1 \
--scoreInsOpen -1 \
--scoreInsBase -1 \
--outSJfilterOverhangMin 9 9 9 9 \
--outSJfilterCountUniqueMin 1 1 1 1 \
--alignEndsType Local \
--seedSearchStartLmax 50 \
--seedPerReadNmax 100000 \
--seedPerWindowNmax 1000 \
--alignTranscriptsPerReadNmax 100000 \
--alignTranscriptsPerWindowNmax 10000
```
Approximately, 57.45% of reads were identified as too short.

To better identify any novel junctions, STARlong was used to perform 2-pass mapping, which uses the list of junctions from the 1st pass as gene annotations for the 2-pass with the --sjdbFileChrStartEnd option.

```bash
module load seq/STAR/2.5.2b

STARlong \
--runThreadN 6 \
--runMode alignReads \
--genomeDir /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/index \
--readFilesIn /n/data1/cores/bcbio/legall_hiv_pacbio/QC/filtered_ccs.fasta \
--outSAMattributes NH HI NM MD \
--readNameSeparator space \
--outFilterMultimapScoreRange 1 \
--outFilterMismatchNmax 2000 \
--scoreGapNoncan -20 \
--scoreGapGCAG -4 \
--scoreGapATAC -8 \
--scoreDelOpen -1 \
--scoreDelBase -1 \
--scoreInsOpen -1 \
--scoreInsBase -1 \
--outSJfilterOverhangMin 9 9 9 9 \
--outSJfilterCountUniqueMin 1 1 1 1 \
--alignEndsType Local \
--seedSearchStartLmax 50 \
--seedPerReadNmax 100000 \
--seedPerWindowNmax 1000 \
--alignTranscriptsPerReadNmax 100000 \
--alignTranscriptsPerWindowNmax 10000 \
--sjdbFileChrStartEnd /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/SJ.out.tab

# Total number of junctions (HIV or human)
wc -l SJ.out.tab: 681 

# Total number of HIV junctions
grep "U39362.2" SJ.out.tab | wc -l: 617
```

The total number of input reads to STAR was 512,181, with an average input read length of 789. The number of reads that were uniquely mapping was 230,631 (45.03%). The number of identified splice junctions had the following breakdown: 219425 GT/AG, 6807 GC/AG, 8882 AT/AC, and 7236 non-canonical. The mismatch rate per base was 2.53%. 673 reads mapped to multiple loci (0.13%), and 842 mapped to too many loci (0.16%) and were dropped. **The main concern with the alignment is the loss of over half of the reads identified as 'too short' (53.37%). To note, the STAR default requires mapped length to be > 2/3 of the total read length.**

## Remove human contamination from the Pacbio reads

Currently, the aligned reads have both HIV reads and human contamination. To remove human contamination by extracting reads mapping to HIV. Reads mapping only to HIV 89.6 genome, U39362.2, were extracted.

```bash

module load seq/samtools/1.3 

## Convert SAM with header to BAM
samtools view -bS /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/Aligned.out.sam > /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/human_hiv_aligned.bam

## Sort and index bam to use ‘view’ command
samtools sort /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/human_hiv_aligned.bam -o /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/human_hiv_aligned_sorted.bam

samtools index /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/human_hiv_aligned_sorted.bam

## Extract only those reads aligning to HIV (U39362.2)
samtools view /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/human_hiv_aligned_sorted.bam "U39362.2" -o /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/hiv_aligned.bam

## Check extraction
samtools view /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/human_hiv_aligned_sorted.bam | grep U39362.2 | wc -l: 230016
samtools view /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/human_hiv_aligned_sorted.bam | wc -l: 233262
samtools view /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/hiv_aligned.bam | wc -l: 230016
```

## Nucleotide sequence extraction

After removing human contamination, 230,016 reads of the 233,262 total reads remained. To generate potential open reading frames, the nucleotide sequences were extracted. A BED file was required to generate the FASTA sequences, so the coordinates were first converted to BED format prior to extraction.

```bash
# Extracting HIV sequences from BAM file

module load seq/BEDtools/2.26.0

bedtools bamtobed -i /n/data1/cores/bcbio/legall_hiv_pacbio/STAR/pass2/hiv_aligned.bam -split > /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned.bed

# The "-split" argument reports each portion of a “split” BAM (i.e., having an “N” CIGAR operation) alignment as distinct BED intervals. Therefore, the BED file does not output the intronic sequences, only the exons if the read is split.

bedtools getfasta -fi /n/data1/cores/bcbio/legall_hiv_pacbio/references/hiv.U39362.fa -bed /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned.bed -name -fo /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned_reads_split.fa

# Combine exons for each read

## Create a list of read header names to automate merging exons together

grep ">" /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned_reads_split.fa | cut -c 2- | sort -u > /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/header_list

## Create a script, transcript_sequences_extraction.sh, to combine exons:

# Echo name of transcript, then merge sequences of exons together

>for name in $(cat /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/header_list.txt)
>do
>echo ">$name" >> /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned_reads_merged.fa
>grep -A1 $name /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned_reads_split.fa | grep -v $name >> /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned_reads_merged.fa
>done

# Exons for each read are on separate lines, so need to merge the lines together for each read

module load seq/fastx/0.0.13 

fasta_formatter -i /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned_reads_merged.fa -w 0 > /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned_reads_final.fa

grep ">" /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned_reads_final.fa | wc -l: 230016

```

## Identification of ORFs and potential proteins

To identify the potential open reading frames (ORFs) using the getorf tool from the Emboss suite of tools, any ORFs were identified at any location in the read sequences using standard code and alternative initiation codons. The lowest minimum nucleotide size (30) was used, and ORFs were defined as a region that began with a START codon and ended with a STOP codon. We only found ORFs on the forward sequence, as no known transcripts are known to be encoded on the reverse strand for HIV. The identified ORFs were output as potential proteins.

```bash
# Get ORFs using standard code with alternative initiation codons, min nucleotide size of 30, with ORF defined as a region that begins with a START and ends with a STOP codon, and only finding ORFs in the forward sequence (not including reverse complement - using emboss suite getorf command available on Orchestra version 6.6.0

module load seq/emboss/6.6.0

getorf -sequence /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_aligned_reads_merged.fa -outseq /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/pacbio_potential_orfs_split.fa -table 1 -find 1 -reverse No

# Does not wrap lines of peptides, so need to merge the lines together for each read

module load seq/fastx/0.0.13 

fasta_formatter -i /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/pacbio_potential_orfs_split.fa -w 0 > /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/pacbio_potential_orfs_merged.fa

cp /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/pacbio_potential_orfs_merged.fa /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/pacbio_potential_orfs_merged.fa_copy

# Determine total number of unique proteins present

## Collapse redundant protein fasta sequences using awk

awk '!x[$0]++' /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/pacbio_potential_orfs_merged.fa_copy > hiv_pacbio_896_unique_potential_orfs.fa

## Remove headers
grep -v ">"  /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/hiv_pacbio_896_unique_potential_orfs.fa | wc -l : 7797
```

463,629 potential proteins were identified using the getorf program. To determine whether the potential proteins from the Pacbio analysis corresponded to the potential proteins identified from the transcript coordinates given in the Ocwieja paper, the Pacbio proteins were compared to those in the paper using BLAT with a filter for minimum identity equal to 100%. 

```bash
## BLAT the sequences against the ocwieja transcripts to determine known transcripts for the pacbio data 

blat /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/unique_896_potential_proteins.fa /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/pacbio_potential_orfs_merged.fa -prot -minIdentity=100 -out=pslx /n/data1/cores/bcbio/legall_hiv_pacbio/blat/pacbio_orfs_in_ocwieja_data_100ident.pslx

# Determine how many protein sequences were aligned to the Ocwieja proteins

cut -f10 pacbio_orfs_in_ocwieja_data_100ident.pslx > read_names_in_ocwieja.txt

## Collapse redundant protein fasta sequences using awk

awk '!x[$0]++' read_names_in_ocwieja.txt | wc -l: 3983
```
## Statistical analysis in R

Analyzing the correspondence between the proteins identified from the Pacbio analysis and the proteins identified in the Ocwieja paper. The similarity between the protein sequences was determined by using BLAT to align the Pacbio proteins to the proteins from the Ocwieja paper. A summary of the Pacbio proteins alignment to the proteins from the Ocwieja paper is displayed in the table below (the R code used to generate the table is given following the table).

|               | # Pacbio proteins Aligning to Ocwieja Proteins | # Ocwieja Proteins Identified |
| ----------------------------- |:------------------------------------:|:-----------------------------:|
| Total Pacbio proteins | 149,239 / 463,629 | 94 / 108 |
| Uniquely aligning full-length Pacbio proteins | 49,797 / 463,629 | 51 / 108 |
| Total uniquely aligning Pacbio proteins | 54,411 / 463,629 | 56 / 108 |

```r
library(ggplot2)

# Looking out BLAT results
pacbio_to_ocwieja <- read.table("pacbio_orfs_in_ocwieja_data_100ident.pslx", header = F, skip = 2, sep = "\t")

#List of all ocwieja proteins identified
all_ocwieja_proteins <- scan("../../ocwieja_analysis/all_ocwieja_protein_names.txt", what=character())

all_ocwieja_proteins <- all_ocwieja_proteins[grep(">", all_ocwieja_proteins)]

all_ocwieja_proteins <- sapply(strsplit(as.character(all_ocwieja_proteins), ">"), "[", 2)

# Determining how many unique Pacbio proteins present in Ocwieja proteins

pacbio_total_proteins <- scan("../total_pacbio_896_unique_orfs.fa", what=character())

head(pacbio_total_proteins)

oc_protein_sequences <- as.character(pacbio_to_ocwieja$V22)
head(oc_protein_sequences)

oc_protein_sequences_trim <- sapply(strsplit(as.character(oc_protein_sequences), ","), "[", 1)

pc_in_oc <- pacbio_total_proteins[pacbio_total_proteins %in% oc_protein_sequences_trim]
pc_in_oc # 1089

# Exploring the output of BLAT, which aligned only those pacbio proteins with 100% minimum identity to the ocwieja paper-derived proteins.

summary_all_proteins <- summary(pacbio_to_ocwieja$V14)
capture.output(summary_all_proteins, file = "summary_all_proteins.txt")
levels(pacbio_to_ocwieja$V14)

# 108 theoretical proteins were identified by the predicting ORFs from the transcripts in the Ocwieja paper

length(unique(pacbio_to_ocwieja$V10))

# 149,239 of the 463,629 HIV Pacbio proteins were returned from the BLAT analysis as aligning to the proteins from the Ocwieja paper

# To determine which proteins identified by Ocwieja are or are not present in the Pacbio proteins identified by BLAT

proteins_present <- all_ocwieja_proteins[which(all_ocwieja_proteins %in% levels(pacbio_to_ocwieja$V14))]

# 94 proteins of the 108 are present in the Pacbio output

proteins_not_present <- all_ocwieja_proteins[which(!(all_ocwieja_proteins %in% levels(pacbio_to_ocwieja$V14)))]

# 14 proteins are not present in the Pacbio output

# Proteins identified during the Ocwieja analysis that did not have Pacbio protein align had the following headings: 

## [1] "vif2__5"  "vif2__9"  "vif2__10" "vif2__12" "vif2__17"
## [6] "vif2__27" "vif2__30" "vif2__32" "vif2__34" "vif2__35"
## [11] "vif2__49" "vpr3__11" "tat5__11" "env4__11"

#Identification of which Ocwieja proteins had full pacbio potential proteins that aligned identically to them.

## Indicating full length read by specifying the Query start = 0 (.psl is zero-based) and the Query end = the length of the Query

fl_matching <- subset(pacbio_to_ocwieja, V12 == 0 & V13 == V11)
levels(fl_matching$V14)
length(unique((fl_matching$V10)))
length((fl_matching$V10))

# 69 proteins from the Ocwieja paper had full-length Pacbio proteins that aligned to them; however, some of the full-length Pacbio proteins aligned uniquely to proteins, while other full-length reads aligned to multiple proteins

summary_nonunique_proteins <- summary(fl_matching$V14)
capture.output(summary_nonunique_proteins, file = "summary_full_nonunique_proteins.txt")

# Determine number of partial length reads and proteins they align to

pl_matching <- subset(pacbio_to_ocwieja, !(V12 == 0 & V13 == V11))
length(unique((pl_matching$V10)))

summary_pl_nonunique_proteins <- summary(pl_matching$V14)
capture.output(summary_pl_nonunique_proteins, file = "summary_full_nonunique_partial_proteins.txt")

# Identification of the number of Pacbio proteins that had full-length reads aligning uniquely to proteins in the Ocwieja paper

uniq_matching <- which(!(fl_matching$V10 %in% fl_matching$V10[duplicated(fl_matching$V10)]))

full_length_uniq_matching <- fl_matching[uniq_matching, ]

# 49,797 of the 149,239 of the Pacbio potential proteins were full-length and aligned uniquely to a single Ocwieja protein

length(which(levels(full_length_uniq_matching$V14) %in% full_length_uniq_matching$V14))

# 51 proteins from the Ocwieja paper have full-length Pacbio proteins uniquely aligning to them

summary_unique_proteins <- summary(full_length_uniq_matching$V14)
capture.output(summary_unique_proteins, file = "summary_full_unique_proteins.txt")

# Determine the number of proteins that had partial-length reads aligning uniquely to them and no others

partial_uniq_matching <- which(!(pacbio_to_ocwieja$V10 %in% pacbio_to_ocwieja$V10[duplicated(pacbio_to_ocwieja$V10)]))

partial_length_uniq_matching <- pacbio_to_ocwieja[partial_uniq_matching, ]

# 34,642 of the 149,239 pacbio potential proteins were partial-length and aligned uniquely to a single Ocwieja protein

length(which(levels(partial_length_uniq_matching$V14) %in% partial_length_uniq_matching$V14))

# 44 proteins have partial-length pacbio reads uniquely aligning to them

summary_partial_unique_proteins <- summary(partial_length_uniq_matching$V14)
capture.output(summary_partial_unique_proteins, file = "summary_partial_unique_proteins.txt")

# How many of the partial-length pacbio reads align to proteins not identified with full-length uniquely aligning reads?

partial_uniq_proteins <- levels(partial_length_uniq_matching$V14)[levels(partial_length_uniq_matching$V14) %in% partial_length_uniq_matching$V14]

full_length_uniq_proteins <- levels(full_length_uniq_matching$V14)[levels(full_length_uniq_matching$V14) %in% full_length_uniq_matching$V14]

unique_matching <- rbind(full_length_uniq_matching, partial_length_uniq_matching)
length(unique((unique_matching$V10)))
length(which(!(partial_uniq_proteins %in% full_length_uniq_proteins)))

# 5 proteins with partial-length pacbio reads uniquely aligning to them did not have full-length pacbio reads uniquely aligning to them. 

# Therefore, a total of 51 + 5 = 56 proteins of the 108 (51.9%)identified in the Ocwieja paper were supported by full-length or partial-length Pacbio potential proteins that were uniquely aligning. 

# The proteins identified from the Pacbio analysis included novel proteins identified in the Ocwieja paper.

# Tabulation

vif2__16 = VIF gene
vif2__19 = VPR gene
vpr1__17 = TAT gene (one amino acid Q insertion in Ocwieja but not in Pacbio (SRR528781.73802_3 [118 - 420] )) 
vpr1__19 = REV gene (one amino acid N insertion in Ocwieja) - SRR528804.76011_2 [172 - 519] 
vif2__24 = VPU gene (SRR528804.7660_1 [73 - 312])
pacbio (SRR528779.22652_7 [97 - 519] ) = GAG polyprotein gene - only first third of gene (140aa)
vif2__48 = ENV gene (SRR528779.43085_6 [239 - 733]  - only first fifth of gene, but aligns uniquely to the ENV gene (165aa))
vif2__55 = NEF gene (SRR528776.45492_10 [566 - 1111] -  lacking last 22aa, but aligns uniquely to NEF gene (165aa)
tat8c__14 = TAT8C gene first identified in the Ocwieja paper (SRR528833.57982_3 [13 - 303]) tat8c__16 = REF gene first identified in the Ocwieja paper (SRR528818.59842_4 [62 - 310] - lacking last 23aa, but aligns uniquely to the REF protein (83aa))

Only proteins identified in Ocwieja, but not the Pacbio proteins are 14 potential proteins that are only between 10-15aa in length.

# Unique VIF reads (vif2__16)
VIF_gene_unique_reads_fl <- subset(full_length_uniq_matching, V14 == "vif2__16") # 126

# Unique VPR reads (vif2__19)
VPR_gene_unique_reads_fl <- subset(full_length_uniq_matching, V14 == "vif2__19") # 116

# Unique TAT reads (vpr1__17)
TAT_gene_unique_reads_fl <- subset(full_length_uniq_matching, V14 == "vpr1__17") # 651

# Unique REV reads (vpr1__19)
## To attain reads unique to REV protein, need to include rev1__12 because REV is completely within this predicted protein
REV_genes_fl <- fl_matching[fl_matching$V14 == "vpr1__19" | fl_matching$V14 == "rev1__12", ]
no_REV_genes_fl <- subset(fl_matching, V14 != "vpr1__19" & V14 != "rev1__12")
head(which(!(REV_genes_fl$V10 %in% no_REV_genes_fl$V10)))
REV_unique_fl <- REV_genes_fl[which(!(REV_genes_fl$V10 %in% no_REV_genes_fl$V10)), ]
REV_unique_fl <- REV_unique_fl[REV_unique_fl$V16 == 0, ] # 5464

# Unique VPU reads (vif2__24)
VPU_gene_unique_reads_fl <- subset(full_length_uniq_matching, V14 == "vif2__24") # 2545

# Unique ENV reads (vif2__48)
ENV_gene_unique_reads_fl <- subset(full_length_uniq_matching, V14 == "vif2__48") # 3206

# Unique NEF reads (vif2__55)
NEF_gene_unique_reads_fl <- subset(full_length_uniq_matching, V14 == "vif2__55") # 1263

# Unique TAT8C reads (tat8c__14)
TAT8C_gene_unique_reads_fl <- subset(full_length_uniq_matching, V14 == "tat8c__14") # 12

# Unique REF reads (tat8c__16) entirely within ref1__13
REF_genes_fl <- fl_matching[fl_matching$V14 == "tat8c__16" | fl_matching$V14 == "ref1__13", ] 
no_REF_genes_fl <- subset(fl_matching, V14 != "tat8c__16" & V14 != "ref1__13")
head(which(!(REF_genes$V10 %in% no_REF_genes$V10)))
REF_unique_fl <- REF_genes[which(!(REF_genes$V10 %in% no_REF_genes$V10)), ] 
REF_unique_fl <- REF_unique_fl[REF_unique_fl$V16 == 0, ] # 295 
```

## Liftover from HIV strain 89.6 to NL4-3

The HIV strain used to generate the Pacbio reads was 89.6, but the HIV strain used for MS analysis is NL4-3. Therefore, we need to liftover the coordinates for the exons from HIV strain 89.6 to NL4-3.

```bash
## Change FASTA files to 2bit to use kenttools

~/tools/kentUtils/bin/faToTwoBit /n/data1/cores/bcbio/legall_hiv_pacbio/references/hiv.U39362.fa /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/U39362_hiv_896.2bit
~/tools/kentUtils/bin/faToTwoBit /n/data1/cores/bcbio/legall_hiv_pacbio/references/AF324493_hiv_nl43_ref_seq.fasta /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/AF324493_hiv_nl43.2bit
~/tools/kentUtils/bin/twoBitInfo /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/U39362_hiv_896.2bit /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/U39362_hiv_896.chromInfo
~/tools/kentUtils/bin/twoBitInfo /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/AF324493_hiv_nl43.2bit /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/AF324493_hiv_nl43.chromInfo

## Use BLAT to create PSL file aligning 89.6 to NL4-3

module load seq/blat/35

blat /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/U39362_hiv_896.2bit /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/AF324493_hiv_nl43.2bit /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/89_to_nl.psl -tileSize=12 -noHead -minScore=100

## Change coordinate system by creating a LFT file

~/tools/kentUtils/bin/liftUp 89_to_nl_NEW.psl 89_to_nl.lft warn 89_to_nl.psl

## Chain together the coordinates from the LFT file to create a CHAIN file

~/tools/kentUtils/bin/axtChain -psl 89_to_nl_NEW.psl U39362_hiv_896.2bit AF324493_hiv_nl43.2bit 89_to_nl.chain -linearGap=loose

## Make alignment nets from chains

~/tools/kentUtils/bin/chainNet 89_to_nl.chain AF324493_chrom.sizes U39362_chrom.sizes ../net/89_to_nl.net /dev/null

## Create liftover chain file

 ~/tools/kentUtils/bin/netChainSubset ../net/89_to_nl.net 89_to_nl.chain ../89_to_nl_chain_net.chain 

## Liftover of 89.6 coordinates to NL4-3 using net chain files

 ~/tools/kentUtils/bin/liftOver ../../getORFs/hiv_aligned.bed ../89_to_nl_chain_net.chain hiv_converted_to_nl.bed ../unMapped/unmapped_89_to_nl
 ```
 
## NL4-3 proteins from Pacbio data

### Extracting HIV sequences from BAM file

Using the coordinates lifted over from 89.6 HIV strain to NL4-3, the nucleotide sequences were extracted. 

```bash

module load seq/BEDtools/2.26.0

bedtools getfasta -fi /n/data1/cores/bcbio/legall_hiv_pacbio/references/AF324493_hiv_nl43_ref_seq.fasta -bed /n/data1/cores/bcbio/legall_hiv_pacbio/hiv_converted_to_nl.bed -name -fo /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_aligned_reads_nl43.fa

## Combine exons for each read

## Create a list of read header names to automate merging exons together

grep ">" /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_aligned_reads_nl43_split.fa | cut -c 2- | sort -u > /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/header_list_nl43.txt

## Create a script, transcript_sequences_extraction.sh, to combine exons:

# Echo name of transcript, then merge sequences of exons together

for name in $(cat /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/header_list_nl43.txt)
do
echo ">$name" >> /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_aligned_reads_nl43_merged.fa
grep -A1 $name /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_aligned_reads_nl43_split.fa | grep -v $name >> /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_aligned_reads_nl43_merged.fa
done

# Exons for each read are on separate lines, so need to merge the lines together for each read

module load seq/fastx/0.0.13 

fasta_formatter -i /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_aligned_reads_nl43_merged.fa -w 0 > /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_aligned_reads_nl43_final.fa

grep ">" /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_aligned_reads_nl43_final.fa | wc -l: 447549
```

### Identification of ORFs and potential proteins

Using the extracted nucleotide sequences of the exons, potential ORFs and proteins for strain NL4-3 were determined.

To identify the potential open reading frames (ORFs) using the `getorf` tool from the Emboss suite of tools, any ORFs were identified at any location in the read sequences using standard code and alternative initiation codons. The lowest minimum nucleotide size (30) was used, and ORFs were defined as a region that began with a START codon and ended with a STOP codon. We only found ORFs on the forward sequence, as no known transcripts are known to be encoded on the reverse strand for HIV. The identified ORFs were output as potential proteins.

```bash
# Get ORFs using standard code with alternative initiation codons, min nucleotide size of 30, with ORF defined as a region that begins with a START and ends with a STOP codon, and only finding ORFs in the forward sequence (not including reverse complement - using emboss suite getorf command available on Orchestra version 6.6.0

module load seq/emboss/6.6.0

getorf -sequence /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_aligned_reads_nl43_final.fa -outseq /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_pacbio_potential_orfs_nl43_split.fa -table 1 -find 1 -reverse No

# Does not wrap lines of peptides, so need to merge the lines together for each read

module load seq/fastx/0.0.13 

fasta_formatter -i /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/pacbio_potential_orfs_split.fa -w 0 > /n/data1/cores/bcbio/legall_hiv_pacbio/getORFs/pacbio_potential_orfs_merged.fa

grep ">" /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_pacbio_potential_orfs_nl43_merged.fa | wc -l: 490717

cp /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_pacbio_potential_orfs_nl43_merged.fa /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_pacbio_potential_orfs_nl43_merged.fa_copy

## Collapse redundant protein fasta sequences using awk

awk '!x[$0]++' /n/data1/cores/bcbio/legall_hiv_pacbio/NL43_proteins/hiv_pacbio_potential_orfs_nl43_merged.fa_copy > hiv_pacbio_nl43_unique_potential_orfs.fa

# Remove headers
grep -v ">" hiv_pacbio_nl43_unique_potential_orfs.fa > hiv_pacbio_nl43_unique_potential_orfs_list.fa

mv hiv_pacbio_nl43_unique_potential_orfs_list.fa hiv_pacbio_nl43_unique_potential_orfs.fa
```

# Ocwieja analysis

## Extracting sequences using a GTF-like file of transcripts

Need to remove spaces and "" from the transcripts bed file prior to extraction. Also, remove any old .fai files in the directory

```
vim ocwieja_transcripts_bed.txt 

":%s/^M/\r/g" # Need to type :%s/<CtrlV><CtrlM>/\r/g
```

Using HIV 89.6 strain - accession #U39362.2 with bedtools `getfasta` to extract sequences using the given coordinates

```bash
bedtools getfasta -fi U39362.2_hiv_sequence.fasta -bed ocwieja_transcripts_bed.txt -name -fo ocwieja_transcript_sequences.fa
```

## Merge sequences for each individual transcript

Use transcript_sequences_extraction.sh to perform the merging of files:

```bash
# Echo name of transcript, then merge sequences of exons together

for name in vif2_ vpr3_ vpr4_ tat5_ tat6_ tat7_ tat8_ env4_ env8_ env12_ env16_ env3_ env7_ env11_ env15_ env2_ env6_ env10_ env14_ env1_ env5_ env9_ env13_ vpr1_ vpr2_ tat1_ tat2_ tat3_ tat4_ rev3_ rev6_ rev9_ rev12_ rev2_ rev5_ rev8_ rev11_ rev1_ rev4_ rev7_ rev10_ nef2_ nef3_ nef4_ nef5_ nef9_ nef11_ nef1_ novel1_ novel2_ novel3_ novel4_ novel5_ novel6_ novel7_ novel8_ novel9_ d1a8a_ tat8c_ ref3_ ref6_ ref9_ ref2_ ref1_ ref4_ ref7_ novel10_ novel11_ novel12_ novel13_ novel14_ novel15_ novel16_ novel17_ novel18_ novel19_ d1a5d4a8_ d1a8_

do

echo ">$name" >> merged_transcript_sequences.fa
grep -A1 $name ocwieja_transcript_sequences.fa | grep -v $name >> merged_transcript_sequences.fa

done
```

Merge consequtive sequences in vim by "gJ" in command mode

## Identification of ORFs and potential proteins

To identify the potential open reading frames (ORFs) using the `getorf` tool from the Emboss suite of tools available on Orchestra version 6.6.0. Any ORFs were identified at any location in the read sequences using standard code and alternative initiation codons. The lowest minimum nucleotide size (30) was used, and ORFs were defined as a region that began with a START codon and ended with a STOP codon. We only found ORFs on the forward sequence, as no known transcripts are known to be encoded on the reverse strand for HIV. The identified ORFs were output as potential proteins.

```bash
getorf -sequence merged_transcript_sequences.fa -outseq ./potential_orfs.fa -table 1 -find 1 -reverse No 

cp potential_orfs.fa potential_orfs.fa_copy
```

## Collapse redundant protein fasta sequences using awk
Using the potential_orfs.fa_copy file do the following:
in vim, remove all new lines ':% s/\n/'
in vim, add new lines before > ':%s/>/\r>/g'
in vim, add new line after ] ':%s/]\s/]\r/g'
in command line, collapse duplicates
awk '!x[$0]++' potential_orfs.fa_copy > unique_potential_orfs.fa

Remove header lines for the duplicated sequences that were already removed in text wrangler by finding and deleting

## Liftover from HIV strain 89.6 to NL4-3

The HIV strain used to generate the Pacbio reads was 89.6, but the HIV strain used for MS analysis is NL4-3. Therefore, we need to liftover the coordinates for the exons from HIV strain 89.6 to NL4-3.

```bash
## Create bedfile in excel based on the GTF file, ocwieja_transcripts_bed.txt, and save as ocwieja_transcripts.bed

vim ocwieja_transcripts.bed

":%s/^M/\r/g" # Need to type :%s/<CtrlV><CtrlM>/\r/g

## Liftover of 89.6 coordinates to NL4-3 using net chain files created previously for the Pacbio liftover, 

~/tools/kentUtils/bin/liftOver /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/ocwieja_transcripts.bed /n/data1/cores/bcbio/legall_hiv_pacbio/liftover/89_to_nl_chain_net.chain /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_converted_nl.bed /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/unmapped_ocwieja_89_to_nl
 ```
 
## NL4-3 proteins from Ocwieja data

### Extracting HIV sequences from BAM file

Using the coordinates lifted over from 89.6 HIV strain to NL4-3, the nucleotide sequences were extracted. 

```bash

module load seq/BEDtools/2.26.0

bedtools getfasta -fi /n/data1/cores/bcbio/legall_hiv_pacbio/references/AF324493_hiv_nl43_ref_seq.fasta -bed /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_converted_nl.bed -name -fo /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_aligned_reads_nl43_split.fa

## Combine exons for each read

## Copy over script used previously to merge exons for Ocwieja data


## Edit the copied transcript_sequences_extraction.sh, to combine exons:

# Echo name of transcript, then merge sequences of exons together

for name in vif2_ vpr3_ vpr4_ tat5_ tat6_ tat7_ tat8_ env4_ env8_ env12_ env16_ env3_ env7_ env11_ env15_ env2_ env6_ env10_ env14_ env1_ env5_ env9_ env13_ vpr1_ vpr2_ tat1_ tat2_ tat3_ tat4_ rev3_ rev6_ rev9_ rev12_ rev2_ rev5_ rev8_ rev11_ rev1_ rev4_ rev7_ rev10_ nef2_ nef3_ nef4_ nef5_ nef9_ nef11_ nef1_ novel1_ novel2_ novel3_ novel4_ novel5_ novel6_ novel7_ novel8_ novel9_ d1a8a_ tat8c_ ref3_ ref6_ ref9_ ref2_ ref1_ ref4_ ref7_ novel10_ novel11_ novel12_ novel13_ novel14_ novel15_ novel16_ novel17_ novel18_ novel19_ d1a5d4a8_ d1a8_

do

echo ">$name" >> /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_aligned_reads_nl43_merged.fa
grep -A1 $name /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_aligned_reads_nl43_split.fa | grep -v $name >> /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_aligned_reads_nl43_merged.fa

done

fasta_formatter -i /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_aligned_reads_nl43_merged.fa -w 0 > /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_aligned_reads_nl43_final.fa
```

### Identification of ORFs and potential proteins

Using the extracted nucleotide sequences of the exons, potential ORFs and proteins for strain NL4-3 were determined.

To identify the potential open reading frames (ORFs) using the `getorf` tool from the Emboss suite of tools, any ORFs were identified at any location in the read sequences using standard code and alternative initiation codons. The lowest minimum nucleotide size (30) was used, and ORFs were defined as a region that began with a START codon and ended with a STOP codon. We only found ORFs on the forward sequence, as no known transcripts are known to be encoded on the reverse strand for HIV. The identified ORFs were output as potential proteins.

```bash
# Get ORFs using standard code with alternative initiation codons, min nucleotide size of 30, with ORF defined as a region that begins with a START and ends with a STOP codon, and only finding ORFs in the forward sequence (not including reverse complement - using emboss suite getorf command available on Orchestra version 6.6.0

module load seq/emboss/6.6.0

getorf -sequence /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_aligned_reads_nl43_final.fa -outseq /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_potential_orfs_nl43_split.fa -table 1 -find 1 -reverse No

# Does not wrap lines of peptides, so need to merge the lines together for each read

module load seq/fastx/0.0.13 

fasta_formatter -i /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_potential_orfs_nl43_split.fa -w 0 > /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_potential_orfs_nl43_merged.fa

grep ">" /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_potential_orfs_nl43_merged.fa | wc -l: 2542

cp /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_potential_orfs_nl43_merged.fa /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_potential_orfs_nl43_merged.fa_copy

## Collapse redundant protein fasta sequences using awk

awk '!x[$0]++' /n/data1/cores/bcbio/legall_hiv_pacbio/ocwieja_analysis/NL43_proteins/hiv_ocwieja_potential_orfs_nl43_merged.fa_copy > hiv_ocwieja_nl43_unique_potential_orfs.fa

# Remove headers
grep -v ">" hiv_ocwieja_nl43_unique_potential_orfs.fa > hiv_ocwieja_nl43_unique_potential_orfs_list.fa

mv hiv_ocwieja_nl43_unique_potential_orfs_list.fa hiv_ocwieja_nl43_unique_potential_orfs.fa
```

Upon exploration of the NL4-3 HIV strain proteins, the novel proteins, Tat8c and Ref, identified in the Ocwieja paper with the corresponding protein sequences for 89.6 strain, were found within the NL4-3 strain. 

A protein similar to Ref with a similar length was identified with the sequence:
MAGRSGDSDEELIRTVRLIKLLYQSNYTPGPGVRYPLTFGWCYKLVPVEPDKVEEANKGENTSLLHPVSLHGMDDPEREVLEWRFDSRLAFHHVARELHPEYFKNC

A shorter protein similar to Tat8c was identified with the sequence: MEPVDPRLEPWKHPGSQPKTACTNCYCKKCCFHCQVCFMTKALGISYGRKKRRQRRRAHQNSQTHQASLSKQ (missing the last 25 amino acids).
