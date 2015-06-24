"""Plot mis-alignments data in multiple ways.

Commandline::

  Usage:
    plot_align circle <dbfile> [--sf=SF] [--fig=FIG] [--samples=S] [-i] [-v]
    plot_align matrix <dbfile> [--fig=FIG] [--samples=S] [-v]
    plot_align detailed <dbfile>... [--sf=SF] [--fig=FIG] [--sample=S] [-i] [-v]

  Options:
    circle           Plot a circle plot
    matrix           Plot a 2D histogram
    detailed         Plot a detailed analysis panel
    <dbfile>         File containing mis alignment data as produced by perfectbam
    --sf=SF          Genome score file
    --fig=FIG        Name of output figure file [default: align_fig.png]
    --samples=S      Samples to show [default: 1000]
"""
import docopt

import matplotlib
orig_backend = matplotlib.get_backend()
matplotlib.use('Agg')

import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as patches
from matplotlib.colors import LogNorm
import numpy as np

import mitty.benchmarking.perfectbam as pbam

import logging
logger = logging.getLogger(__name__)


def mis_mat_cell(conn, chrom1, pos11, pos12, chrom2, pos21, pos22):
  """Get us the number of reads that should have aligned to chrom1 between pos11 and pos12 but ended up aligned to
  chrom2 pos21, pos22

  :param conn:    connection to mis-aligned reads database as produced by perfectbam
  :param chrom1:  correct chrom
  :param pos11:   correct pos lower bound
  :param pos12:   correct pos upper bound
  :param chrom2:  aligned chrom
  :param pos21:   aligned pos lower bound
  :param pos22:   aligned pos upper bound
  :return: integer corresponding to read count
  """
  query = 'SELECT COUNT(*) FROM reads WHERE correct_chrom=? AND ? <= correct_pos AND ? < correct_pos AND aligned_chrom=? AND ? <= aligned_pos AND aligned_pos < ?'
  return conn.execute(query, (chrom1, pos11, pos12, chrom2, pos21, pos22)).next()[0]


def compute_mis_mat(conn, chrom_lens, bp_per_bin, reverse=False):
  """Get us a matrix binning the number of reads going to and fro

  :param conn:        connection to mis-aligned reads database as produced by perfectbam
  :param chrom_lens:  list of chromosome lengths in order of chromosome number
  :param bp_per_bin:  base-pairs per bin -> used to determine how many bins
  :param reverse:     map aligned->correct instead of correct->aligned
  :return: a numpy matrix
  """




# class Data:
#   """A container for mis-alignment and mappability data that can be used by plots to display views of the data."""
#   def __init__(self, conn, map_score=None, chrom=-1, window=int(1e5), samples=1000):
#     """Setup data container
#
#     :param conn: connection to mis-aligned reads database as produced by perfectbam
#     :param map_score: numpy file structure as generated by kmer score
#     :param chrom: chromosome to start in. If -1, we will return data from all chromosomes
#     :param window: size of window to consider for reads
#     :param samples: number of random samples to retrieve. If None, return all reads passing filter
#     """
#     def process_array(st, arr):
#       this_array = np.empty((arr.size, 2), dtype=np.uint32)
#       this_array[:, 0] = np.arange(start=0, stop=arr.size * st, step=st, dtype=np.uint32)
#       this_array[:, 1] = arr  # This is stored as np.uint32
#       return this_array
#
#     self.conn, self.chrom, self.pos, self.window, self.samples = conn, chrom, 0, window, samples
#     self.summary = pbam.load_summary(self.conn)
#     if map_score:
#       step = map_score['step'][0]  # This is saved as an array by np, but it's actually a scalar
#       #for k, v in map_score.iteritems(): print k, map_score[k]
#       self.map_score = {int(k[6:]): process_array(step, map_score[k]) for k, v in map_score.iteritems() if k != 'step'}
#     else:
#       self.map_score = None
#
#   def set_view(self, chrom=None, pos=None, window=None):
#     """Set view parameters
#
#     :param chrom: chromosome to return data from. If -1, we will return data from all chromosomes
#     :param pos: position in chromosome. If None, leave unchanged
#     :param window: window size. If None, leave unchanged
#     """
#     self.chrom, self.pos, self.window = chrom or self.chrom, pos or self.pos, window or self.window
#
#   def fetch_read_summary(self):
#     return self.summary
#
#   def fetch_read_data(self):
#     """Thin wrapper around conn.execute
#     :returns iterator over database rows"""
#     logger.debug('Fetching chrom={:d},start={:d},stop={:d}'.format(self.chrom, self.pos, self.pos + self.window))
#     return pbam.load_reads(self.conn, chrom=self.chrom, start_pos=self.pos, stop_pos=self.pos + self.window,
#                            sample=self.samples)
#
#   def fetch_mappability_data(self):
#     """Give us the mappability data for the view we have set
#
#     :returns dictionary: chromosome numbers [1,2,3 ...] as keys and values as
#     Nx2 numpy arrays with first column as position and second column as mappability value
#     """
#     this_view = None
#     if self.map_score:
#       if self.chrom == -1:  # We want EVERYTHING
#         this_view = self.map_score
#       else:
#         k = self.chrom
#         this_view = self.map_score[k][self.pos <= self.map_score[k] <= (self.pos + self.window), :]
#     return this_view


class CircularPlot:
  """Encapsulates data and methods for the circular plot.
  In non-interactive mode we simply plot a sample of mis-aligned reads in the given axes.
  In interactive mode we use mouse-scroll to change the read-window size and we use hover to update which section of the
  genome we show

  When this plot is to be used as part of a larger, interactive plot, we should create this in non-interactive mode and
  call the functions from the governing controls
  """
  def __init__(self, data=None, interactive=False, ax=None, chrom_radius=1, chrom_gap=0.05, chrom_thick=5, lw=1):
    """
    :param data: Data object
    :param interactive: if True, create an interactive plot
    :param ax: axis object. Needs to be polar (e.g. ax = plt.subplot(111, polar=True))
    :param chrom_radius: chrom_radius of the plot
    :param chrom_gap: gap between chromosomes in radians
    :param chrom_thick: thickness of chromosome
    """
    self.data = data
    self.interactive = interactive
    self.chrom_radius = chrom_radius
    self.mappability_radius = 1.2 * self.chrom_radius
    if self.data.fetch_mappability_data() is not None:
      self.r_max = 1.04 * self.mappability_radius
    else:
      self.r_max = 1.04 * self.chrom_radius
    self.chrom_gap = chrom_gap
    self.chrom_thick = chrom_thick
    self.lw = lw

    self.chrom_lens = [s['seq_len'] for s in self.data.fetch_read_summary()]
    self.chrom_offsets = reduce(lambda x, y: x + [x[-1] + y], self.chrom_lens, [0])

    if ax is None:
      self.fig = plt.figure()
      self.ax = self.fig.add_subplot(111, polar=True)
    else:
      self.fig = ax.figure
      self.ax = ax

    self.erasable_objects = []  # We use this for the interactive plot
    self.plot_genome_as_a_circle()
    self.plot_mappability_on_a_circle()
    self.plot_reads()

    if interactive:
      self.connect_events()

  def connect_events(self):
    self.action_mouse_move = self.fig.canvas.mpl_connect('motion_notify_event', self.select_pos)
    self.action_mouse_scroll = self.fig.canvas.mpl_connect('scroll_event', self.resize_data_window)
    plt.show()

  def constrain_new_window_size(self, window):
    return max(1, min(window, self.chrom_lens[self.data.chrom - 1]))

  def select_pos(self, event):
    if event.inaxes != self.ax: return

    c_off, c_gap = self.chrom_offsets, self.chrom_gap
    total_len = sum(self.chrom_lens)
    radians_per_base = (2.0 * np.pi - len(self.chrom_lens) * c_gap) / total_len  # With allowance for chrom gaps

    theta = event.xdata
    for n, off in enumerate(c_off):
      if theta <= off * radians_per_base + n * c_gap:
        chrom = n
        pos = int((theta - (chrom - 1) * c_gap) / radians_per_base - c_off[chrom - 1])
        break
    self.data.set_view(chrom=chrom, pos=pos)
    self.update_plot()
    logger.debug('Chrom={:d}, Pos={:d}'.format(self.data.chrom, self.data.pos))

  def resize_data_window(self, event):
    if event.inaxes != self.ax: return
    if event.step < 0:
      window = self.data.window * 2
    else:
      window = self.data.window / 2
    window = min(max(1, window), max(self.chrom_lens))
    self.data.set_view(window=window)
    self.update_plot()

  def plot_genome_as_a_circle(self):
    """Plot the chromosomes on a circle."""
    total_len = sum(self.chrom_lens)
    radians_per_base = (2.0 * np.pi - len(self.chrom_lens) * self.chrom_gap) / total_len  # With allowance for chrom gaps

    xticks = []
    xticklabels = []
    delta_radian = 0.01
    start_radian = 0
    for ch_no, l in enumerate(self.chrom_lens):
      end_radian = start_radian + l * radians_per_base
      theta = np.arange(start_radian, end_radian, delta_radian)
      self.ax.plot(theta, [self.chrom_radius * 1.01] * theta.size, lw=self.chrom_thick, color=[.3, .3, .3])
      xticks.append((start_radian + end_radian)/2)
      xticklabels.append(str(ch_no + 1))
      start_radian = end_radian + self.chrom_gap

    plt.setp(self.ax.get_yticklabels(), visible=False)
    self.ax.grid(False)
    plt.setp(self.ax, xticks=xticks, xticklabels=xticklabels)
    self.ax.set_rmax(self.r_max)

  def plot_mappability_on_a_circle(self):
    """We call this during initialization, and the data window is set for full chromosome viewing."""
    map_data = self.data.fetch_mappability_data()
    if map_data is None: return

    total_len = sum(self.chrom_lens)
    radians_per_base = (2.0 * np.pi - len(self.chrom_lens) * self.chrom_gap) / total_len  # With allowance for chrom gaps

    max_mappability = float(max([md[:, 1].max() for md in map_data.values()]))
    for ch_no, l in enumerate(self.chrom_lens):
      theta = (self.chrom_offsets[ch_no] +  map_data[ch_no + 1][:, 0]) * radians_per_base + ch_no * self.chrom_gap
      r = 1.01 * self.chrom_radius + ((self.mappability_radius - 1.01 * self.chrom_radius) * map_data[ch_no + 1][:, 1] / max_mappability) ** 0.5
      self.ax.plot(theta, r, lw=1, color='blue')
    self.ax.set_rmax(self.r_max)

  def plot_reads(self):
    c_lens, c_off, c_gap, radius, lw, ax = self.chrom_lens, self.chrom_offsets, self.chrom_gap, self.chrom_radius, self.lw, self.ax
    total_len = sum(self.chrom_lens)
    radians_per_base = (2.0 * np.pi - len(self.chrom_lens) * c_gap) / total_len  # With allowance for chrom gaps

    # http://matplotlib.org/users/path_tutorial.html
    codes = [
      Path.MOVETO,
      Path.CURVE4,
      Path.CURVE4,
      Path.CURVE4,
    ]

    patches_added = []
    for read in self.data.fetch_read_data():
        # pbam.load_reads(self.conn, chrom=self.chrom,
        #                         start_pos=self.pos, stop_pos=self.pos + self.window, sample=self.samples):
      t0 = (c_off[read['correct_chrom']-1] + read['correct_pos']) * radians_per_base + (read['correct_chrom']-1) * c_gap
      t1 = (c_off[read['aligned_chrom']-1] + read['aligned_pos']) * radians_per_base + (read['aligned_chrom']-1) * c_gap
      this_radius = max(min(1.0, abs(t1 - t0) / np.pi), 0.05) * radius
      verts = [
        (t0, radius),  # P0
        (t0, radius - this_radius),  # P1
        (t1, radius - this_radius),  # P2
        (t1, radius),  # P3
      ]
      path = Path(verts, codes)
      patch = patches.PathPatch(path, facecolor='none', lw=lw)
      ax.add_patch(patch)
      patches_added.append(patch)
    logger.debug('Plotted {:d} reads'.format(len(patches_added)))

    if self.data.chrom > 0:
      t0 = (c_off[self.data.chrom-1] + self.data.pos) * radians_per_base + (self.data.chrom-1) * c_gap
      t1 = (c_off[self.data.chrom-1] + min(self.data.pos + self.data.window, c_lens[self.data.chrom-1])) * radians_per_base + (self.data.chrom-1) * c_gap
      if t0 < t1:  # Prevents us plotting cursor when we go off the chromosome
        th0 = np.linspace(t0, t1, 10)
        theta = np.concatenate((th0, [t1], th0[::-1], [t0, t0]))
        r = np.concatenate((np.ones(10) * 1.03 * radius, [self.mappability_radius], np.ones(10) * self.mappability_radius, [self.mappability_radius, 1.03 * radius]))
        patches_added += [ax.add_patch(patches.Polygon(np.vstack((theta, r)).T, closed=True, fill=True, color='orange', lw=1, zorder=-10))]
        #theta = np.linspace(t0, t1, 10)
        #patches_added += ax.plot(theta, np.ones(theta.size) * 1.03 * radius, color='gray', lw=10, zorder=-10)
        #self.ax.set_rmax(self.r_max)  # Using plot (as opposed to patch, re computes the axes limits. Go figure)

    self.erasable_objects = patches_added

  def update_plot(self):
    for p in self.erasable_objects:
      p.remove()
    self.plot_reads()
    plt.draw()


class DataView:
  """Wrapper around reads mis-alignments database(s) and mis-alignment files."""
  def __init__(self, conn={}, mappability={}, chrom=-1, window=int(1e5), samples=1000):
    """
    :param conn:         dict of database connection objects opened with pbam.connect_to_db
    :param mappability:  dict of npz file handles with mappability scores
    :param chrom: chromosome to start in. If -1, we will return data from all chromosomes
    :param window: size of window to consider for reads
    :param samples: maximum number of random samples to retrieve. If None, return all reads passing filter
    """
    def process_array(st, arr):
      this_array = np.empty((arr.size, 2), dtype=np.uint32)
      this_array[:, 0] = np.arange(start=0, stop=arr.size * st, step=st, dtype=np.uint32)
      this_array[:, 1] = arr  # This is stored as np.uint32
      return this_array

    self.conn, self.chrom, self.pos, self.window, self.samples = conn, chrom, 0, window, samples
    self.summary = {k: pbam.load_summary(v) for k, v in self.conn.iteritems()}
    self.map_score = {}
    if mappability:
      for k, v in mappability.iteritems():
        step = v['step'][0]  # This is saved as an array by np, but it's actually a scalar
        self.map_score[k] = {int(k2[6:]): process_array(step, v2) for k2, v2 in v.iteritems() if k2 != 'step'}

  def fetch_read_summary(self, key=None):
    """
    :param key: key identifying which read file data we want. Omit to get first (or only) one
    :return: a dict with summary of mis-alignments
    """
    return self.summary.get(key or self.summary.keys()[0], None)

  def fetch_read_data(self, key=None):
    """Thin wrapper around conn.execute

    :param key: key identifying which read file data we want. Omit to get first (or only) one
    :returns iterator over database rows"""
    if key is None: key = self.conn.keys()[0]
    logger.debug('Fetching chrom={:d},start={:d},stop={:d}'.format(self.chrom, self.pos, self.pos + self.window))
    return [r for r in pbam.load_reads(self.conn[key], chrom=self.chrom, start_pos=self.pos, stop_pos=self.pos + self.window,
                                       sample=self.samples)]

  def fetch_mappability_data(self, key=None):
    """Give us the mappability data for the view we have set

    :param key: key identifying which mappability score we want. Omit to get first (or only) one
    :returns dictionary: chromosome numbers [1,2,3 ...] as keys and values as
    Nx2 numpy arrays with first column as position and second column as mappability value
    """
    this_view = None
    if self.map_score:
      _key = key or self.map_score.keys()[0]
      if _key not in self.map_score:
        pass
      elif self.chrom == -1:  # We want EVERYTHING
        this_view = self.map_score[_key]
      else:
        k = self.chrom
        this_view = self.map_score[_key][k][self.pos <= self.map_score[_key][k] <= (self.pos + self.window), :]
    return this_view

  def set_view(self, chrom=None, pos=None, window=None, samples=None):
    """Set view parameters

    :param chrom: chromosome to return data from. If -1, we will return data from all chromosomes
    :param pos: position in chromosome. If None, leave unchanged
    :param window: window size. If None, leave unchanged
    """
    self.chrom, self.pos, self.window, self.samples = chrom or self.chrom, pos or self.pos, window or self.window, samples or self.samples


class MatrixPlot:
  """Encapsulates methods and data needed to display a zoom-able matrix plot of mis-alignments.

  Zooming

  The home plot displays the complete misalignment matrix with N samples. Zooming keeps the number of samples constant
  but reduces the view-port.
  """
  def __init__(self):
    pass


class InteractivePanel:
  """Encapsulates data and methods for the detailed plot. There is no non-interactive mode.

  The matrix plot serves as the main controller plot. We plot the different mappability measures on the top row and


  The master controller is the circular plot - we use this to control which part of the

  When this plot is to be used as part of a larger, interactive plot, we should create this in non-interactive mode and
  call the functions from the governing controls
  """
  pass


def cli():
  """Command line script entry point."""
  if len(docopt.sys.argv) < 2:  # Print help message if no options are passed
    docopt.docopt(__doc__, ['-h'])
    return
  else:
    args = docopt.docopt(__doc__)

  level = logging.DEBUG if args['-v'] else logging.WARNING
  logging.basicConfig(level=level)

  plot_fname = args['--fig']

  if args['-i']:
    switch_to_interactive_backend()

  conn = pbam.connect_to_db(args['<dbfile>'][0])
  mappability_data = np.load(args['--sf']) if args['--sf'] else None
  if args['circle']:
    #data = Data(conn, map_score=mappability_data, samples=int(args['--samples']))
    data = DataView({'1': conn}, mappability={'1': mappability_data}, samples=int(args['--samples']))
    #plt.xkcd()
    cp = CircularPlot(data, interactive=args['-i'])

  if not args['-i']:
    plt.savefig(plot_fname)
    #import bokeh.mpl
    #bokeh.mpl.to_bokeh(fig=cp.fig, name='circular.html', xkcd=True)



def switch_to_interactive_backend():
  """By default we use Agg because we want to make static plots, but if we choose the interactive option we need to
  switch back to the original, interactive, backend."""
  if orig_backend not in matplotlib.rcsetup.interactive_bk:
    backend_to_use = matplotlib.rcsetup.interactive_bk[0]
    logger.warning('Original backend {:s} is not in the interactive backend list. Using first interactive backend found {:s}'.format(orig_backend, backend_to_use))
  else:
    backend_to_use = orig_backend
  plt.switch_backend(backend_to_use)
  #plt.switch_backend('WebAgg')


class InteractivePlot:
  def __init__(self, chrom_lens, mis):
    self.chrom = 1
    self.pos = 0
    self.window = 1e5
    self.chrom_lens = chrom_lens
    self.mis = mis
    self.fig = plt.figure()
    self.ax = self.fig.add_subplot(111, polar=True)
    self.current_patches = []
    plot_genome_as_a_circle(chrom_lens, radius=1, chrom_gap=0.05, chrom_thick=5, ax=self.ax)
    self.plot_data()

  def filter_reads(self):
    c, p, w = self.chrom, self.pos, self.window
    return [m for m in self.mis if m[0] == c and p < m[1] < p + w]

  def plot_data(self):
    for p in self.current_patches:
      p.remove()
    self.current_patches = plot_mis_alignments_on_a_circle(self.chrom_lens, self.filter_reads(), section=(self.chrom, self.pos, self.pos + self.window), radius=1, chrom_gap=0.05, lw=0.5, ax=self.ax)
    plt.draw()

  def inext(self, event):
    self.pos += self.window
    if self.pos >= self.chrom_lens[self.chrom - 1]:
      self.chrom += 1
      self.pos = 0
      if self.chrom > len(self.chrom_lens):
        self.chrom = 1
    self.plot_data()


def interactive_plot(args):
  prefix = args['<prefix>'][0]  # This is a surprising behavior from docopt
  summary_fname = prefix + '_summary.json'
  mis_alignments_fname = prefix + '_misaligned.csv'
  chrom_lens, mis = process_inputs(summary_fname, mis_alignments_fname, args['--down-sample'])
  switch_to_interactive_backend()
  iplot = InteractivePlot(chrom_lens, mis)
  cid = iplot.fig.canvas.mpl_connect('button_press_event', iplot.inext)
  plt.show()


def non_interactive_plots(args):
  prefix = args['<prefix>'][0]  # This is a surprising behavior from docopt
  summary_fname = prefix + '_summary.json'
  mis_alignments_fname = prefix + '_misaligned.csv'

  chrom_lens, mis = process_inputs(summary_fname, mis_alignments_fname, args['--down-sample'])
  plot_suffix = '.pdf' if args['pdf'] else '.png'

  if args['circle']:
    plot_fname = prefix + '_circle_plot' + plot_suffix
    draw_static_circle_plot(chrom_lens, mis)
  elif args['matrix']:
    plot_fname = prefix + '_matrix_plot' + plot_suffix
    draw_static_matrix_plot(chrom_lens, mis)
  elif args['detailed']:
    plot_fname = prefix + '_mappability_plot' + plot_suffix
    f = np.load(args['<sfile>'])
    draw_mappability_plot(chrom_lens, mis, f)
  else:
    logger.warning('Unhandled option')
    return

  plt.savefig(plot_fname)


def draw_static_circle_plot(chrom_lens, mis):
  """Draw a static circle plot with all the mis-alignments

  :param (list) chrom_lens: list of chromosome lengths
  :param (list) mis: list of tuples (correct_chrom, correct_pos, aligned_chrom, aligned_pos) Can be generator
  """
  ax = plt.subplot(111, polar=True)
  plot_genome_as_a_circle(chrom_lens, radius=1, chrom_gap=0.05, chrom_thick=5, ax=ax)
  plot_mis_alignments_on_a_circle(chrom_lens, mis, radius=1, chrom_gap=0.05, lw=0.5, ax=ax)
  #ax.set_rmax(1.04)


def plot_genome_as_a_circle(chrom_lens, radius=1, chrom_gap=0.001, chrom_thick=0.1, ax=None):
  """Plot the chromosomes on a circle. Will plot on the currently active axes.

  :param (list) chrom_lens: list of chromosome lengths
  :param (float) radius: radius of the plot
  :param (float) chrom_gap: gap between chromosomes in radians
  :param (float) chrom_thick: thickness of chromosome
  :param (object) ax: axis object. Needs to be polar (e.g. ax = plt.subplot(111, polar=True))
  """
  total_len = sum(chrom_lens)
  radians_per_base = (2.0 * np.pi - len(chrom_lens) * chrom_gap) / total_len  # With allowance for chrom gaps

  xticks = []
  xticklabels = []
  delta_radian = 0.01
  start_radian = 0
  for ch_no, l in enumerate(chrom_lens):
    end_radian = start_radian + l * radians_per_base
    theta = np.arange(start_radian, end_radian, delta_radian)
    ax.plot(theta, [radius * 1.01] * theta.size, lw=chrom_thick)
    xticks.append((start_radian + end_radian)/2)
    xticklabels.append(str(ch_no + 1))
    start_radian = end_radian + chrom_gap

  plt.setp(ax.get_yticklabels(), visible=False)
  ax.grid(False)
  plt.setp(ax, xticks=xticks, xticklabels=xticklabels)
  ax.set_rmax(1.04 * radius)


def plot_mis_alignments_on_a_circle(chrom_lens, misalignments, section=(), radius=1, chrom_gap=0.001, lw=2, ax=None):
  """Plot bezier curves indicating where the given misalignment reads originated and landed.

  :param chrom_lens: list of chromosome lengths
  :param misalignments: list of tuples (correct_chrom, correct_pos, aligned_chrom, aligned_pos) Can be generator
  :param section: tuple of the form (chrom, start, stop) indicating which section we are looking at. Draws a marker
                  omit to omit plotting of this marker
  :param radius: radius of the plot
  :param lw: thickness of drawn line
  :param ax: axis object. Needs to be polar (e.g. ax = plt.subplot(111, polar=True))
  :returns list of patches added. These can be `removed` as needed
  """
  total_len = sum(chrom_lens)
  radians_per_base = (2.0 * np.pi - len(chrom_lens) * chrom_gap) / total_len  # With allowance for chrom gaps

  # http://matplotlib.org/users/path_tutorial.html
  codes = [
    Path.MOVETO,
    Path.CURVE4,
    Path.CURVE4,
    Path.CURVE4,
  ]

  patches_added = []
  for m in misalignments:
    t0 = (sum(chrom_lens[:m[0]-1]) + m[1]) * radians_per_base + (m[0]-1) * chrom_gap
    t1 = (sum(chrom_lens[:m[2]-1]) + m[3]) * radians_per_base + (m[2]-1) * chrom_gap
    this_radius = max(min(1.0, abs(t1 - t0) / np.pi), 0.05) * radius
    verts = [
      (t0, radius),  # P0
      (t0, radius - this_radius),  # P1
      (t1, radius - this_radius),  # P2
      (t1, radius),  # P3
    ]
    path = Path(verts, codes)
    patch = patches.PathPatch(path, facecolor='none', lw=lw)
    ax.add_patch(patch)
    patches_added.append(patch)
  if tuple:
    t0 = (sum(chrom_lens[:section[0]-1]) + section[1]) * radians_per_base + (section[0]-1) * chrom_gap
    t1 = (sum(chrom_lens[:section[0]-1]) + section[2]) * radians_per_base + (section[0]-1) * chrom_gap
    verts = [
      (t0, 1.03 * radius),  # P0
      (t0, 1.03 * radius),  # P1
      (t1, 1.03 * radius),  # P2
      (t1, 1.03 * radius),  # P3
    ]
    path = Path(verts, codes)
    patch = patches.PathPatch(path, color='gray', lw=2)
    ax.add_patch(patch)
    patches_added.append(patch)

    #plt.plot(t0, .99 * radius, '.')
  return patches_added


def draw_static_matrix_plot(chrom_lens, mis):
  """Draw a static matrix plot with all the mis-alignments shown

  :param (list) chrom_lens: list of chromosome lengths
  :param (list) mis: list of tuples (correct_chrom, correct_pos, aligned_chrom, aligned_pos) Can be generator
  """
  chrom_offsets = get_chrom_offsets(chrom_lens)
  ax = plt.gca()
  plt.setp(ax.get_xticklabels(), visible=False)
  plt.setp(ax.get_yticklabels(), visible=False)
  plt.setp(ax, xticks=chrom_offsets, yticks=chrom_offsets, ylabel='Correct position', xlabel='Aligned position', aspect=1)
  #plot_mis_alignment_matrix(chrom_offsets, mis, limits=[2.5e6, 3e6], histogram=False, ax=ax)
  plot_mis_alignment_matrix(chrom_offsets, mis, histogram=False, ax=ax)


def get_chrom_offsets(chrom_lens):
  return reduce(lambda x, y: x + [x[-1] + y], chrom_lens, [0])


def flatten_coordinates(chrom_offsets, mis):
  """Convert data in (chrom, pos) format to data in (pos') format, where pos' pretends all the chromosomes are laid out
  end to end

  :param (list) chrom_offsets: list of chromosome offsets
  :param (list) mis: list of tuples (correct_chrom, correct_pos, aligned_chrom, aligned_pos) Can be generator
  """
  return np.array([[chrom_offsets[r[0] - 1] + r[1], chrom_offsets[r[2] - 1] + r[3]] for r in mis])


def plot_mis_alignment_matrix(chrom_offsets, mis, limits=[], histogram=False, ax=None):
  """

  :param (list) chrom_lens: list of chromosome lengths
  :param (list) mis: list of tuples (correct_chrom, correct_pos, aligned_chrom, aligned_pos) Can be generator
  """
  flattened_coordinates = flatten_coordinates(chrom_offsets, mis)
  if not limits:
    limits = [0, chrom_offsets[-1]]

  if histogram:
    h, xe, ye = np.histogram2d(flattened_coordinates[:, 0], flattened_coordinates[:, 1], bins=100,
                               range=[limits, limits])
    #plt.imshow(h, origin="lower", extent=(0, chrom_offsets[-1], 0, chrom_offsets[-1]), cmap=plt.cm.gray_r, norm=LogNorm(), interpolation=None)
    hdl = plt.matshow(h, origin="lower", extent=(0, chrom_offsets[-1], 0, chrom_offsets[-1]), cmap=plt.cm.gray_r, norm=LogNorm(), interpolation=None)
  else:
    hdl = plt.scatter(flattened_coordinates[:, 1], flattened_coordinates[:, 0], s=1, marker='.')

  plt.setp(ax, xlim=[0, chrom_offsets[-1]], ylim=limits)  # Need to set this after setting ticks
  return hdl


def draw_mappability_plot(chrom_lens, misalignments, npz_file):
  """Plot locations of misaligned plots along-with k-mer scores computed and stored in a file

  """
  ax = plt.gca()
  draw_vertical_genome_mappability(chrom_lens, npz_file, ax)
  hh = bin_reads(chrom_lens, misalignments)
  draw_vertical_binned_reads(chrom_lens, hh, ax)


def bin_reads(chrom_lens, misalignments, source=True):
  """Make a histogram of read locations from the mis-alignment data

  :param chrom_lens: list of chromosome lengths
  :param misalignments: list of tuples (correct_chrom, correct_pos, aligned_chrom, aligned_pos)
  :param source: True if we want to bin according to the correct (source) position of the reads
                 False is we want to bin according to the aligned (destination) position of the reads
  :return:
  """
  chrom_pos = [[] for _ in range(len(chrom_lens))]
  bins = [{'range': (0, ch_len), 'bins': ch_len / 10000} for ch_len in chrom_lens]
  for r in misalignments:
    chrom_pos[r[0] - 1] += r[1:2]
  return [np.histogram(chrom_pos[n], density=True, **bins[n]) for n in range(len(chrom_lens))]


def draw_vertical_genome_mappability(chrom_lens, npz_file, ax):
  step = npz_file['arr_0'][0]
  chrom_max_len = max(chrom_lens)
  for n, ch_len in enumerate(chrom_lens):
    x = npz_file['arr_{:d}'.format(n + 1)] + 5000 * (n + 1)
    y = chrom_max_len - np.arange(x.shape[0], dtype=int) * step
    ax.plot(x, y, color=[0.7, 0.7, 0.7], lw=0.5)


def draw_vertical_binned_reads(chrom_lens, hh, ax):
  chrom_max_len = max(chrom_lens)
  for n, ch_len in enumerate(chrom_lens):
    x = -hh[n][0]/hh[n][0].max() * 2000 + 5000 * (n + 1)
    y = chrom_max_len - (hh[n][1][:-1] + hh[n][1][1:])/2.0
    ax.plot(x, y, color=[0.3, 0.3, 0.3], lw=0.25)


if __name__ == "__main__":
  cli()