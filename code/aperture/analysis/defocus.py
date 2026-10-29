"""defocus blur against object distance, and the depth of field that falls out of it

A thin lens focused at z_f images a point at z as a disc whose diameter on the sensor is
proportional to |1/z_f - 1/z|. In pixels

    b(z) = A |1/z_f - 1/z|,     A = D v / p

with D the aperture diameter, v the lens-to-sensor distance and p the pixel pitch. Fitting A
and z_f to a set of measured kernel widths gives the focus distance without having to trust
the focus ring, and inverting b(z) < tolerance gives the classical depth of field in mm.

Measured widths never reach zero at focus: the source is a real pinhole, the lens has
aberration, and on this camera the core saturates. So the model carries a floor added in
quadrature,

    b(z)^2 = (A |1/z_f - 1/z|)^2 + b0^2

which is three parameters. With three captured distances that is exactly determined and has
no residual left to test the model with, so fit the five bare-lens marks first to check the
model form, then apply it to the masks and report jitter() rather than a bare number.
"""
from collections import namedtuple

import numpy as np

Fit = namedtuple("Fit", "rms A floor z_focus n dof")

Z_GRID = np.arange(600.0, 2501.0, 1.0)   # mm, the range the rig can plausibly be focused over


def fit(z, b, z_grid=Z_GRID):
    """Fit b(z)^2 = (A|1/z_f - 1/z|)^2 + b0^2 to measured widths

    Linear in the two squared coefficients once z_f is fixed, so sweep z_f and solve the rest
    exactly. That avoids a gradient descent finding a local minimum in what is a genuinely
    multi-modal surface when there are only three points.
    """
    z = np.asarray(z, dtype=float)
    b = np.asarray(b, dtype=float)
    if z.size != b.size or z.size < 2:
        raise ValueError("need at least two (distance, width) pairs")
    best = None
    for zf in z_grid:
        x = np.abs(1 / zf - 1 / z) ** 2
        M = np.vstack([x, np.ones_like(x)]).T
        sol, *_ = np.linalg.lstsq(M, b ** 2, rcond=None)
        if sol[0] <= 0 or sol[1] < 0:
            continue
        rms = float(np.sqrt(np.mean((np.sqrt(np.maximum(M @ sol, 0)) - b) ** 2)))
        if best is None or rms < best[0]:
            best = (rms, float(np.sqrt(sol[0])), float(np.sqrt(sol[1])), float(zf))
    if best is None:
        raise ValueError("no physical fit: widths do not grow away from any focus distance")
    return Fit(best[0], best[1], best[2], best[3], int(z.size), int(z.size) - 3)


def predict(z, f):
    z = np.asarray(z, dtype=float)
    return np.sqrt((f.A * np.abs(1 / f.z_focus - 1 / z)) ** 2 + f.floor ** 2)


def depth_of_field(f, tol=1.0):
    """(near, far) mm over which the defocus term stays under tol pixels

    The floor is not included: it is there at every distance, focus included, so it is not
    what depth of field is about. far is inf once the tolerance reaches the hyperfocal case.
    """
    lim = tol / f.A
    near = 1.0 / (1.0 / f.z_focus + lim)
    far = 1.0 / (1.0 / f.z_focus - lim) if (1.0 / f.z_focus - lim) > 0 else np.inf
    return near, far


def jitter(z, b, delta=2, trials=200, seed=0, z_grid=Z_GRID):
    """(median, 16th, 84th) fitted z_focus when each width is perturbed by +/- delta px

    With three points the fit is exact and has no residual to quote, so this is what says
    whether the answer is stable: it is the only honest error bar available there.
    """
    rng = np.random.default_rng(seed)
    b = np.asarray(b, dtype=float)
    out = []
    for _ in range(trials):
        try:
            out.append(fit(z, np.maximum(b + rng.integers(-delta, delta + 1, b.shape), 1.0),
                           z_grid).z_focus)
        except ValueError:
            continue
    if not out:
        raise ValueError("every perturbed fit failed")
    return (float(np.median(out)), float(np.percentile(out, 16)), float(np.percentile(out, 84)))
