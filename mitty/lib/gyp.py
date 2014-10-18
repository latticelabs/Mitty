"""Library for python "interface" to ggeco. Each bat_ function returns a string that can be saved as a batch file
to run on ggeco. The other functions manage the result files produced by ggeco.

Commandline::

  Usage:
    gyp  --in=IN  --out_prefix=OUT_PREF

  Options:
    --in=IN                 Input result file
    --out_prefix=OUT_PREF   Prefix of output files
"""


def bat_create_genome(ref, start_dir):
  """ref is a genome class.
  Creation and population of a genome from file is like:

  // create a new genome
  create t

  // load hg38
  add t raw://v38_no_newline.fa
  """
  import os
  hdr = ref.genome_header()
  #rel_genome_dir = os.path.relpath(genome_dir, start=join(experiment_prefix, gsd))  # %^&$ work around for ggeeco bug
  rel_genome_dir = os.path.relpath(ref.dir, start_dir)  # %^&$ work around for ggeeco bug
  script = "// Create a 'genome' for every chromosome\n"
  for chrom, h in zip(ref.sorted_chrom_idx(), hdr):
    # We do this to discard the sequence id + newline at the start of the files
    start = len(h[0]) + 2  # Seq id + newline
    stop = start + h[1] - 1
    script += "create chr{:d}\n".format(chrom)
    script += "add chr{:d} raw://{:s}/chr{:d}.fa:{:d}..{:d}\n".format(chrom, rel_genome_dir, chrom, start, stop)
  return script


def bat_load_vcf(ref, vcf_rdr):
  script = "// Loading VCF\n"
  for chrom in ref.sorted_chrom_idx():
    script += _load_variants_for_chrom(vcf_rdr, chrom)
  return script


def _load_variants_for_chrom(vcf_rdr, chrom):
  script = "// Loading variants for chrom {:d}\n".format(chrom)
  try:
    this_rdr = vcf_rdr.fetch(chrom, start=0)
  except (ValueError, KeyError):  # New version of pyvcf changed the error
    return script

  for v in this_rdr:
    # We only handle snps and indels
    if v.is_sv or v.is_sv_precise:
      continue

    alt = v.ALT[0]
    start, stop = v.POS - 1, v.POS + len(v.REF) - 2
    script += "add chr{:d}:{:d}..{:d} [{:s}]\n".format(chrom, start, stop, alt)

  return script


def bat_map_reads(fastq_fp):
  """fastq_fp = pysam.Fastqfile(in_fastq)."""
  script = '// Create a list of find commands\n'
  for read in fastq_fp:
    script += "print [{:s}]\n".format(read.name)
    script += "find [{:s}]\n".format(read.sequence)
  return script


def sanitize_map_reads_output(in_fp):
  """in_fp - pointer to results file from ggeco.
  ignore_first - ignore these many lines as they are part of the setup
  We need this because there are a lot of extraneous characters in the result file from ggeco
  """
  for line in in_fp:
    sanitized = line.strip()
    if len(sanitized) == 0: continue
    # Only pass the lines we might be interested in
    if sanitized.startswith('> print') or \
       sanitized.startswith('> find') or \
       sanitized.startswith('~') or \
       sanitized.startswith('c'):
        yield sanitized
    # if sanitized.startswith('> run'): continue
    # if sanitized.startswith('executing'): continue
    # if sanitized.startswith('batch'): continue
    # if sanitized.startswith('> print'): continue
    # if sanitized.startswith('> exit'): continue  # Nasty stuff at end
    # if sanitized.startswith('deleting'): continue  # Nasty stuff at end
    #yield sanitized


def write_sanitize_map_reads_as_file(in_fp, out_fp):
  for line in sanitize_map_reads_output(in_fp):
    out_fp.write(line + '\n')


def parse_read_header(line, first):
  # 1:0|r0|<|31330|100M|>|31180|100M
  qname = line.split('|')
  correct_chrom = int(qname[0].split(':')[0])
  correct_pos, correct_dir = (int(qname[3]), qname[2]) if first else (int(qname[6]), qname[5])
  return line, correct_chrom, correct_pos, correct_dir

direction = '><'


def parse_alignment_line(line):
  # ~chr1:31428..31329 [14]
  match, blocks = line.split()
  rev_complement = match[0] == '~'
  chrom, pos = match.strip('~').split(':')
  aligned_chrom = int(chrom[3:])
  p1, p2 = pos.split('..')
  aligned_pos = int(p2) + 1 if rev_complement else int(p1) + 1
  return aligned_chrom, aligned_pos, direction[rev_complement]


def parse_map_reads_file(in_fp, paired=True):
  """Given a raw results file, parse the correct positions of the reads and ."""
  #reads = []
  this_read = None
  this_alignment = []
  first = True
  for line in sanitize_map_reads_output(in_fp):
    if line[0] == 'c' or line[0] == '~':  # Alignment result line
      this_alignment += [parse_alignment_line(line)]
      continue
    elif line[:6] == '> find':
      this_read = this_read + (line[8:-1],)
    else:  # New read begins
      result_to_yield = (this_read, this_alignment) if this_read is not None else None
      this_read = parse_read_header(line[9:-1], first)
      this_alignment = []
      if paired: first = not first
      if result_to_yield is not None:
        yield result_to_yield
  # Close us out
  if this_read is not None:
    yield (this_read, this_alignment)


def score_reads_simple(in_fp, paired=True, window=0):
  """Just check if the first hit is a match within the given window and return us the info in a format that matches
  checkbam.
  Each line of the misa lignment file is like:
  read.qname, correct_chrom_no, correct_pos, read.tid + 1, read.pos + 1, read.mapq, read.mate_is_unmapped, read.seq

  The summary stats are like:
    {"read_counts" : {chrom: count ...}
     "bad_read_counts" : {chrom: count ...}
  """
  from collections import Counter
  misaligned_reads = []
  total_reads_cntr, bad_reads_cntr = Counter(), Counter()
  for result in parse_map_reads_file(in_fp, paired):
    total_reads_cntr[result[0][1]] += 1
    if result[0][1] == result[1][0][0] and result[0][2] == result[1][0][1]:  # Proper, perfect, alignment
      continue
    bad_reads_cntr[result[0][1]] += 1
    # read.qname, correct_chrom_no, correct_pos, read.tid + 1, read.pos + 1, read.mapq, read.mate_is_unmapped, read.seq
    misaligned_reads += [(result[0][0], result[0][1], result[0][2], result[1][0][0], result[1][0][1], 100, False, result[0][4])]
  return misaligned_reads, total_reads_cntr, bad_reads_cntr


def write_csv_header(csv_fp):
  csv_fp.write('qname, correct_chrom, correct_pos, aligned_chrom, aligned_pos, mapping_qual, mate_is_unmapped, seq\n')


def write_csv(csv_fp, misaligned_reads):
  csv_fp.writelines((', '.join(map(str, line)) + '\n' for line in misaligned_reads))


def main(in_fp, csv_fp, json_fp):
  import json
  write_csv_header(csv_fp)
  misaligned_reads, total_reads_cntr, bad_reads_cntr = score_reads_simple(in_fp, paired=True)
  csv_fp.writelines((', '.join(map(str, line)) + '\n' for line in misaligned_reads))
  json.dump({"read_counts": {str(k): v for k,v in total_reads_cntr.iteritems()},
             "bad_read_counts": {str(k): v for k,v in bad_reads_cntr.iteritems()}},
            json_fp, indent=2)

if __name__ == "__main__":
  import docopt
  if len(docopt.sys.argv) < 2:  # Print help message if no options are passed
    docopt.docopt(__doc__, ['-h'])
  else:
    args = docopt.docopt(__doc__)

  with open(args['--in'], 'r') as gg_in_fp, \
      open(args['--out_prefix'] + '.csv', 'w') as csv_out_fp, \
      open(args['--out_prefix'] + '.json', 'w') as json_out_fp:
    main(gg_in_fp, csv_fp=csv_out_fp, json_fp=json_out_fp)