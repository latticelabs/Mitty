"""Prepare a binned matrix of misalignments and plot it in different ways"""

import click
import pysam
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as patches
from matplotlib.colors import LogNorm
import numpy as np


def we_have_too_many_bins(bins):
  return sum([len(bb) for bb in bins]) > 5000  # This is our threshold for too many bins to compute


def autoscale_bin_size(chrom_lens, bin_cnt=100.0):
  return int(sum(chrom_lens) / bin_cnt)


def compute_misalignment_matrix_from_bam(bam_fp, bin_size=None, i_know_what_i_am_doing=False):
  """Create a matrix of binned mis-alignments

  :param bam_fp: input BAM
  :param bin_size: size of bin in mega bases
  :param i_know_what_i_am_doing: Set this to override the runtime warning of too many bins

  """
  def binnify(_pos, _bins):
    for n in range(1, len(_bins)):
      if _pos < _bins[n]:
        return n - 1
    return len(_bins) - 1  # Should not get here

  chrom_lens = [hdr['LN'] for hdr in bam_fp.header['SQ']]
  bin_size = bin_size * 1e6 if bin_size is not None else autoscale_bin_size(chrom_lens)
  bins = [np.array(range(0, hdr['LN'], bin_size) + [hdr['LN']], dtype=int) for hdr in bam_fp.header['SQ']]
  if not i_know_what_i_am_doing and we_have_too_many_bins(bins):
    raise RuntimeWarning('The number of bins will be very large. '
                         'If you are sure you want to do this, '
                         'use the --i-know-what-i-am-doing flag.')

  bin_centers = [(bb[:-1] + bb[1:]) / 2.0 for bb in bins]
  # Rows = source (correct pos) Cols = destination (aligned pos)
  matrices = [[np.zeros(shape=(len(bins[j]) - 1, len(bins[i]) - 1), dtype='uint32') for i in range(len(bins))] for j in range(len(bins))]

  # TAG TYPE VALUE
  # XR  i    Aligned chromosome
  # XP  i    Aligned pos
  for r in bam_fp:
    c_chrom, c_pos, a_chrom, a_pos = r.reference_id, r.pos, r.get_tag('XR'), r.get_tag('XP')
    c_pos_binned, a_pos_binned = binnify(c_pos, bins[c_chrom]), binnify(a_pos, bins[a_chrom])
    matrices[c_chrom][a_chrom][c_pos_binned, a_pos_binned] += 1
  return chrom_lens, bins, bin_centers, matrices


def plot_genome_as_a_circle(ax, chrom_lens, chrom_gap=np.pi / 50, chrom_radius=1.0, chrom_thick=5, r_max=1.05):
  """Plot the chromosomes on a circle."""
  total_len = sum(chrom_lens)
  radians_per_base = (2.0 * np.pi - len(chrom_lens) * chrom_gap) / total_len  # With allowance for chrom gaps

  theta_stops, x_ticks, x_tick_labels = [], [], []
  delta_radian = 0.01
  start_radian = 0
  for ch_no, l in enumerate(chrom_lens):
    end_radian = start_radian + l * radians_per_base
    theta = np.arange(start_radian, end_radian, delta_radian)
    theta_stops.append((start_radian, end_radian))
    ax.plot(theta, [chrom_radius * 1.01] * theta.size, lw=chrom_thick, zorder=-1)  # , color=[.3, .3, .3])
    x_ticks.append((start_radian + end_radian)/2)
    x_tick_labels.append(str(ch_no + 1))
    start_radian = end_radian + chrom_gap

  plt.setp(ax.get_yticklabels(), visible=False)
  ax.grid(False)
  plt.setp(ax, xticks=x_ticks, xticklabels=x_tick_labels)
  ax.set_rmax(r_max)
  return theta_stops


def plot_read_mis_alignments_on_a_circle(ax, chrom_lens, bins, bin_centers, matrices, theta_stops,
                                         chrom_radius=1.0, scaling_factor=0.01):
  scaling_factor *= 0.01
  # http://matplotlib.org/users/path_tutorial.html
  codes = [
    Path.MOVETO,
    Path.CURVE4,
    Path.CURVE4,
    Path.CURVE4,
  ]
  for i in range(len(bins)):
    for j in range(len(bins)):
      mat = matrices[i][j]
      range_bp_origin, range_bp_dest = float(chrom_lens[i]), float(chrom_lens[j])
      offset_origin, offset_dest = theta_stops[i][0], theta_stops[j][0]
      range_origin, range_dest = theta_stops[i][1] - theta_stops[i][0], theta_stops[j][1] - theta_stops[j][0]
      scale_origin, scale_dest = range_origin / range_bp_origin, range_dest / range_bp_dest
      c_origin, c_dest = offset_origin + bin_centers[i] * scale_origin, offset_dest + bin_centers[j] * scale_dest
      this_origin, this_dest = np.tile(c_origin, c_dest.shape[0]), np.repeat(c_dest, c_origin.shape[0])
      mat_flat = mat.ravel()
      idx, = mat_flat.nonzero()
      for ii in idx:
        t0, t1 = this_origin[ii], this_dest[ii]

        this_radius = max(min(1.0, abs(t1 - t0) / np.pi), 0.05) * chrom_radius
        vertices = [
          (t0, chrom_radius),  # P0
          (t0, chrom_radius - this_radius),  # P1
          (t1, chrom_radius - this_radius),  # P2
          (t1, chrom_radius),  # P3
        ]
        path = Path(vertices, codes)
        patch = patches.PathPatch(path, facecolor='none', lw=scaling_factor * mat_flat[ii])
        ax.add_patch(patch)


def circle_plot(chrom_lens, bins, bin_centers, matrices, scaling_factor):
  """Plot the confusion matrix as a circle plot."""
  fig = plt.figure()
  ax = fig.add_subplot(111, polar=True)
  theta_stops = plot_genome_as_a_circle(ax, chrom_lens)
  plot_read_mis_alignments_on_a_circle(ax, chrom_lens, bins, bin_centers, matrices, theta_stops, chrom_radius=1.0, scaling_factor=scaling_factor)


def plot_genome_as_a_square(ax, bins, chrom_gap=1000, chrom_thick=5):
  """Plot the chromosomes on a matrix."""
  start_pos, linear_stops, x_ticks, x_tick_labels = chrom_gap, [], [], []
  for ch_no, b in enumerate(bins):
    linear_stops.append([start_pos, start_pos + b[-1]])
    ax.plot([x + start_pos for x in b], [0 for _ in b], color='k' if ch_no % 2 else 'gray', lw=chrom_thick, zorder=-1)
    ax.plot([0 for _ in b], [x + start_pos for x in b], color='k' if ch_no % 2 else 'gray', lw=chrom_thick, zorder=-1)
    x_ticks.append((start_pos + start_pos + b[-1]) / 2)
    x_tick_labels.append(str(ch_no + 1))
    start_pos += b[-1] + chrom_gap

  #plt.setp(ax.get_yticklabels(), visible=False)
  ax.grid(False)
  plt.setp(ax, xticks=x_ticks, xticklabels=x_tick_labels, yticks=x_ticks, yticklabels=x_tick_labels)
  return linear_stops


def plot_read_mis_alignments_as_a_matrix(ax, chrom_lens, bins, bin_centers, matrices, linear_stops,
                                         scaling_factor=1.0, plot_grid=True):
  for i in range(len(bins)):
    for j in range(len(bins)):
      mat = matrices[i][j]
      range_bp_x, range_bp_y = float(chrom_lens[i]), float(chrom_lens[j])
      offset_x, offset_y = linear_stops[i][0], linear_stops[j][0]
      range_x, range_y = linear_stops[i][1] - linear_stops[i][0], linear_stops[j][1] - linear_stops[j][0]
      scale_x, scale_y = range_x / range_bp_x, range_y / range_bp_y
      cx, cy = offset_x + bin_centers[i] * scale_x, offset_y + bin_centers[j] * scale_y
      this_x, this_y = np.tile(cx, cy.shape[0]), np.repeat(cy, cx.shape[0])
      if plot_grid: ax.plot(this_x, this_y, '.', color=(0.8, 0.8, 0.8), ms=2, zorder=-1)
      mat_flat = mat.ravel()
      idx, = mat_flat.nonzero()
      if idx.size > 0:
        ax.scatter(this_x[idx], this_y[idx], mat_flat[idx] * scaling_factor, facecolors='none')


def matrix_plot(chrom_lens, bins, bin_centers, matrices, scaling_factor, plot_grid=True):
  """Plot the confusion matrix as a ... matrix."""
  fig = plt.figure()
  ax = fig.add_subplot(111)
  linear_stops = plot_genome_as_a_square(ax, bins, chrom_gap=max(chrom_lens) * 0.1)
  plot_read_mis_alignments_as_a_matrix(ax, chrom_lens, bins, bin_centers, matrices, linear_stops,
                                       scaling_factor=scaling_factor, plot_grid=plot_grid)
  plt.setp(ax, aspect=1, xlabel='Correct', ylabel='Aligned')


def is_grid_too_dense(bins):
  return sum([len(bb) for bb in bins]) > 100  # This is our threshold for too dense a grid to show


def auto_scale_scaling_factor(matrices, scale=1000.0):
  return scale / max([matrices[i][j].max() for i in range(len(matrices)) for j in range(len(matrices[i]))])


@click.command()
@click.argument('badbam', type=click.Path(exists=True))
@click.option('--circle', type=click.Path(), help='Name of figure file for circle plot')
@click.option('--matrix', type=click.Path(), help='Name of figure file for matrix plot')
@click.option('--bin-size', type=float, default=None, help='Bin size in Mb. Omit to auto-scale')
@click.option('--scaling-factor', type=float, default=None, help='Scale size of disks/lines in plot. Omit to auto-scale')
@click.option('--i-know-what-i-am-doing', is_flag=True, help='Override bin density safety')
def cli(badbam, circle, matrix, bin_size, scaling_factor, i_know_what_i_am_doing):
  """Prepare a binned matrix of mis-alignments and plot it in different ways"""
  chrom_lens, bins, bin_centers, matrices = \
    compute_misalignment_matrix_from_bam(pysam.AlignmentFile(badbam, 'rb'),
                                         bin_size=bin_size, i_know_what_i_am_doing=i_know_what_i_am_doing)
  scaling_factor = scaling_factor or auto_scale_scaling_factor(matrices)

  if circle is not None:
    circle_plot(chrom_lens, bins, bin_centers, matrices, scaling_factor)
    plt.savefig(circle)
  if matrix is not None:
    matrix_plot(chrom_lens, bins, bin_centers, matrices, scaling_factor,
                plot_grid=not is_grid_too_dense(bins))
    plt.savefig(matrix)

if __name__ == '__main__':
  cli()