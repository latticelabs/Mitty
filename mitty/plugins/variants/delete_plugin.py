"""This is the stock deletion generator. The length of deletions follows a geometric distribution as would be expected
from a poisson point process governing deletion termination"""
import itertools

import numpy as np

import mitty.lib
import mitty.lib.util as mutil
from mitty.plugins.variants import scale_probability_and_validate

import logging
logger = logging.getLogger(__name__)


__example_param_text__ = """
{
  "p": 0.01,           # probability that the deletion will happen at any given base
  "p_end": 0.1,        # probability governing length of deletion
  "min_len": 10,   # Lower bound on deletion lengths
  "max_len": 1000  # upper bound on deletion lengths
}
"""

_description = """
This is the stock delete plugin. A typical parameter set resembles
""" + __example_param_text__

_example_params = eval(__example_param_text__)


class Model:
  def __init__(self, p=0.01, p_end=0.1, min_len=10, max_len=1000, **kwargs):
    assert 0 <= p <= 1.0, "Probability out of range"
    assert 0 <= p_end <= 1.0, "Probability out of range"
    assert 0 < min_len < max_len, "Check your min_len and max_len definitions"
    p_end = max(p_end, 1e-8)  # numpy.random.geometric(p=.0, size=10) = WTF
    self.p, self.p_end, self.del_len_min, self.del_len_max = p, p_end, min_len, max_len

  def get_variants(self, ref, p=None, f=None, seed=1, **kwargs):
    """This function is called by the simulator to obtain variants.

    :param ref: reference sequence as a string
    :param chrom: chromosome number (1,2,3,4...)
    :param p: array/list of probability values
    :param f: array/list of frequency values
    :param seed: seed for the random number generators
    :return: 5 arrays/lists/iterables all of the same length
              pos   - position of SNPs
              stop  - stop locations, (pos + 1 for SNPs)
              ref   - reference base,
              alt   - alt base,
              p     - probability value for this variant. These are uniformly distributed random values
    """
    assert 0 < seed < mitty.lib.SEED_MAX
    logger.debug('Master seed: {:d}'.format(seed))

    base_loc_rng, del_len_rng = mutil.initialize_rngs(seed, 2)

    p_eff = scale_probability_and_validate(self.p, p, f)
    del_locs = mutil.place_poisson_seq(base_loc_rng, p_eff, 0, len(ref), ref)
    del_lens = del_len_rng.geometric(p=self.p_end, size=del_locs.shape[0])
    np.clip(del_lens, a_min=self.del_len_min, a_max=self.del_len_max, out=del_lens)  # Make sure our deletions are clipped at the level we want

    del_locs, del_ends, refs, alts = mutil.discard_deletions_in_illegal_regions(ref, del_locs,
                                                                                (del_locs + del_lens + 1).astype('i4'))
    if len(del_locs):
      del_lens = del_ends - del_locs - 1
      p = 1.0 - del_lens / float(del_lens.max())

    return del_locs, del_ends, refs, alts, p


def test0():
  """Edge case - no variants generated"""
  ref_seq = 'ACTGACTGACTGACTGACTGACTGACTGACTGACTG'
  m = Model(p=0.00001)
  pos, stop, ref, alt, p = m.get_variants(ref_seq, seed=10)
  assert len(pos) == 0  # This should just run and not crash


def test1():
  """Do we discard 'N's?"""
  ref_seq = 'ACTGACTGACTGACTGACTGACTGACTGACTGACTG'
  m = Model(p=0.1)
  pos, stop, ref, alt, p = m.get_variants(ref_seq, seed=15)
  assert 6 in pos

  ref_seq = 'ACTGACTGACNGACTGACTGACTGACTGACTGACTG'
  m = Model(p=0.1)
  pos, stop, ref, alt, p = m.get_variants(ref_seq, seed=15)
  assert 6 not in pos


if __name__ == "__main__":
  print _description