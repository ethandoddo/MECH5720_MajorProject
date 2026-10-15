"""Flutter shutter codes, after Raskar, Agrawal and Tumblin, SIGGRAPH 2006.

A code is a list of 0s and 1s, one per chop. The board plays it on the panel from its
own clock while the camera sits open in bulb mode, so the panel is the shutter. A target
that moves at a steady speed then blurs by the code stretched along its motion. A good
code keeps every spatial frequency of that blur above zero, so least squares can undo it.
A box exposure of the same length has zeros, which is why its deblurred image shows bands.

design() searches random codes with half the chops open for the one whose padded spectrum
has the highest minimum, the criterion of the paper. The search is seeded, so every machine
designs the same code and the manifest can name it by its text. The sketch takes up to
MAX_CHOPS chops and 16 bit millisecond times, so a run has to fit FLUTTER_MAX_S.

  python flutter.py             prints the default code, its score and the box score
  python flutter.py 1011001...  scores a code of your own
"""
import sys

import numpy as np

import config as cfg

MAX_CHOPS = 64          # the sketch's limit
PAD = 8                 # the spectrum is sampled at PAD times the code length


def parse(code):
    """a code as a list of 0s and 1s from a string of 0s and 1s (spaces ignored) or any sequence"""
    if isinstance(code, str):
        bits = [c for c in code if not c.isspace()]
        bad = sorted(set(bits) - {"0", "1"})
        if bad:
            raise ValueError(f"a code is 0s and 1s, not {bad}")
        out = [int(c) for c in bits]
    else:
        out = [1 if int(b) else 0 for b in code]
    if not 1 <= len(out) <= MAX_CHOPS:
        raise ValueError(f"a code has 1 to {MAX_CHOPS} chops, not {len(out)}")
    return out


def to_text(code):
    return "".join("1" if b else "0" for b in code)


def box(n):
    """every chop open: the conventional exposure of the same length"""
    return [1] * n


def shut(n):
    """every chop shut: the leakage and dark frames, which keep the bulb timing of a coded frame"""
    return [0] * n


def spectrum(codes):
    """magnitude spectrum of each row of a 0/1 array, zero padded to PAD times its length"""
    c = np.atleast_2d(np.asarray(codes, dtype=float))
    return np.abs(np.fft.rfft(c, PAD * c.shape[1], axis=1))


def score(code):
    """the smallest spectral magnitude as a fraction of the DC term, 0 for a code with a zero.
    Higher is better. A box of n chops scores 0 and the designed 32 chop code about 0.075"""
    mag = spectrum(parse(code))[0]
    return float(mag.min() / mag[0]) if mag[0] else 0.0


def design(n=None, ones=None, seed=None, trials=20000):
    """the best of `trials` random codes with `ones` open chops out of n. The first and last
    chop stay open, so the blur length is the code length. Ties go to the flatter spectrum"""
    n = n or cfg.FLUTTER_CHOPS
    ones = ones or n // 2
    if n < 2 or n > MAX_CHOPS:
        raise ValueError(f"n is 2 to {MAX_CHOPS}")
    if not 2 <= ones <= n:
        raise ValueError("ones is 2 to n")
    rng = np.random.default_rng(cfg.FLUTTER_SEED if seed is None else seed)
    codes = np.zeros((trials, n), dtype=np.uint8)
    codes[:, 0] = codes[:, -1] = 1
    inner = n - 2
    pick = np.argsort(rng.random((trials, inner)), axis=1)[:, :ones - 2] + 1
    np.put_along_axis(codes, pick, 1, axis=1)
    mag = spectrum(codes)
    low = mag.min(axis=1) / mag[:, 0]
    flat = -mag.std(axis=1) / mag[:, 0]
    best = np.lexsort((flat, low))[-1]
    return codes[best].tolist()


def total_ms(n, chop_ms, lead_ms=None, tail_ms=None):
    """how long the board holds the sequence, play command to report"""
    lead = cfg.FLUTTER_LEAD_MS if lead_ms is None else lead_ms
    tail = cfg.FLUTTER_TAIL_MS if tail_ms is None else tail_ms
    return int(lead) + n * int(chop_ms) + int(tail)


def check_timing(n, chop_ms, lead_ms, tail_ms):
    for name, v in (("chop_ms", chop_ms), ("lead_ms", lead_ms), ("tail_ms", tail_ms)):
        if int(v) != v or v < 0 or v > 65535:
            raise ValueError(f"{name} is a whole number of ms from 0 to 65535")
    if chop_ms < 1:
        raise ValueError("chop_ms is at least 1")
    t = total_ms(n, chop_ms, lead_ms, tail_ms)
    if t > cfg.FLUTTER_MAX_S * 1000:
        raise ValueError(f"lead + code + tail is {t / 1000:.1f} s, over the {cfg.FLUTTER_MAX_S} s limit")
    return t


def target_speed(blur_px, n, chop_ms):
    """pixels per second a target moves to blur by blur_px over the code"""
    return blur_px / (n * chop_ms / 1000)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        code = parse(sys.argv[1])
        print(f"{to_text(code)}  {len(code)} chops, {sum(code)} open, score {score(code):.3f}")
    else:
        code = design()
        n = len(code)
        print(f"designed {n} chops, {sum(code)} open, seed {cfg.FLUTTER_SEED}")
        print(f"  {to_text(code)}  score {score(code):.3f}")
        print(f"  box of {n}  score {score(box(n)):.3f}")
        print(f"  {cfg.FLUTTER_CHOP_MS} ms chops: {n * cfg.FLUTTER_CHOP_MS / 1000:.1f} s of code, "
              f"{total_ms(n, cfg.FLUTTER_CHOP_MS) / 1000:.1f} s with lead and tail")
