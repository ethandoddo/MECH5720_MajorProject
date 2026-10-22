# Flutter shutter results: 5 s, ISO 100, f/22

The most closely matched photo of each kind taken with the flutter shutter at f/22, the numbers
for each, and how they were worked out. `results.json` has every number; `data.csv` has the
results table for a spreadsheet; `score.py` makes `results.json` and the pictures again from the
photos here.

## Settings

Every photo here was taken with these (checked from the photos' EXIF):

| Setting | Value |
| --- | --- |
| Camera | Canon 60D, mode dial on M, RAW (.cr2, with a .dng copy) |
| Shutter | 5 s (impulse photo 1/10 s) |
| ISO | 100 |
| Aperture | f/22 |
| Focal length | Run3_f22 55 mm; Run2_f22 51 mm; Run1_2 51 mm |

Flutter tab in the Experiments window:

| Setting | Value |
| --- | --- |
| Code | Designed 32 chops: `10001101101001011000001111010101`, 16 open, score 0.075 |
| Chop | 100 ms, so the code lasts 3.2 s |
| Lead | 1000 ms: the panel stays black for 1 s from when the camera is fired, then plays the code |
| Tail | 200 ms |
| Panel | Invert |
| Impulse shutter | 1/10 s (one chop long) |
| Photo | Camera as it is |
| Repeats | 1 |
| Target distance | 217 mm |
| Blur px | 200 (only sets the speed estimate in the pop-up; the capture does not use it) |

Only the aperture was meant to change from the f/11 runs (lamps, focus, camera and track stayed
where they were), but the zoom moved from 51 mm to 55 mm between Run2_f22 and Run3_f22. At 55 mm
everything in the photo is 1.08 times bigger, so Run3_f22's 250 px of blur
is about 232 px at Run2_f22's scale: the coded photo had a little less blur
for its size than the box, which favours the coded photo. Each photo is scored against its own
run's reference, so the scores are not affected otherwise.
Light, measured by each run's reference photo (the car standing still, panel open 3.2 s), as a
fraction of the sensor's full scale:

| Run | Reference mean |
| --- | --- |
| Run3_f22 | 0.00710 |
| Run2_f22 | 0.00649 |
| Run1_2 | 0.00497 |

The f/11 dim runs measured 0.0217 to 0.023, so Run2_f22 and Run3_f22 had
3.1 to 3.5 times less light, not quite the 4 times the
aperture alone gives. The room light was probably not exactly the same; the cause is not known.
Run1_2 was dimmer again; it is used here only for the leakage and dark photos.

## What is here

| Folder | Run | Photos | Used for |
| --- | --- | --- | --- |
| `coded_and_impulse/` | Run3_f22 | reference, impulse, coded | The flutter shutter result, and the short exposure to compare with |
| `box/` | Run2_f22 | reference, box | The ordinary long exposure to compare with |
| `leakage_and_dark/` | Run1_2 | reference, leakage, dark | How much light the black panel lets through, and the camera's own noise |

Each folder also has the run's manifest (`*_manifest.json`) and each frame's trace (`*.json`:
the code, when each chop played, the shutter time). Each photo is scored against its own run's
reference. The other f/22 photos were deleted from `captures/flutter`; their scores and pictures
are in `out/flutter`.

Why these: the coded and box photos are compared fairly only if the car moved the same distance in
each, and the car's speed wandered by 20 to 35% within every run. Run3_f22's coded photo and
Run2_f22's box both have 250 px of blur, the closest match of all the f/22 takes. The
impulse comes from Run3_f22, the same run (same light and speed) as the coded photo. Leakage and dark
were only taken in Run1_2. The other f/22 takes (lam 0.05 scores, same method):

| Run | Photo | Reference mean | Blur | Car speed | MSE | Detail |
| --- | --- | --- | --- | --- | --- | --- |
| Run1_2 | coded | 0.00497 | 400 px | 125 px/s | 0.00307 | 0.508 |
| Run1_2_base | box | 0.00652 | 450 px | 140.6 px/s | 0.00248 | 0.377 |
| Run2_f22 | coded | 0.00649 | 325 px | 101.6 px/s | 0.00255 | 0.540 |
| Run3_f22 | box | 0.00710 | 300 px | 93.8 px/s | 0.00131 | 0.529 |

Images:

- `compare.png`: Run3_f22 coded photo, deblurred (250 px, lam 0.05), reference, stacked.
- `95_compare.png`: the "95" up close: reference, coded as is, deblurred lam 0.05 and RL40 at 250 px.
- `95_baselines.png`: the "95" up close. Top, next to Run3_f22's reference: coded deblurred at its best
  setting (lam 0.5), impulse as is and smoothed. Bottom, next to Run2_f22's reference: box as is,
  deblurred lam 0.05 and RL40.
- `deblurred_best_lam0.5_250px.png`: the best deblur, full frame.

## Results

Car speed is in image pixels per second at full resolution (about 5,200 px across the frame). For coded
and box photos it is the blur length the deblur found divided by the 3.2 s code. For the impulse
photo it is taken from the coded photo of the same run, and the blur is that speed over 1/10 s.

The same method as f/11 (lam 0.05, RL40, impulse smoothed 8 px), then each photo at its best
setting (lowest MSE of lam 0.02 to 1, RL 5 to 80 iterations, impulse smoothed 4 to 16 px):

| Run | Photo | Car speed | Blur | Version | MSE | NCC | Detail |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Run3_f22 | coded | 78.1 px/s | 250 px | as is | 0.00308 | 0.967 | 0.287 |
| Run3_f22 | coded | 78.1 px/s | 250 px | deblurred lam 0.05 | 0.00324 | 0.965 | 0.461 |
| Run3_f22 | coded | 78.1 px/s | 250 px | deblurred RL40 | 0.00500 | 0.946 | 0.426 |
| Run3_f22 | coded | 78.1 px/s | 250 px | best: deblurred lam 0.5 | 0.00202 | 0.978 | 0.525 |
| Run3_f22 | coded | 78.1 px/s | 250 px | best: deblurred RL5 | 0.00215 | 0.977 | 0.546 |
| Run2_f22 | box | 78.1 px/s | 250 px | as is | 0.00178 | 0.979 | 0.400 |
| Run2_f22 | box | 78.1 px/s | 250 px | deblurred lam 0.05 | 0.00117 | 0.986 | 0.604 |
| Run2_f22 | box | 78.1 px/s | 250 px | deblurred RL40 | 0.00121 | 0.986 | 0.626 |
| Run2_f22 | box | 78.1 px/s | 250 px | best: deblurred lam 0.05 | 0.00117 | 0.986 | 0.604 |
| Run2_f22 | box | 78.1 px/s | 250 px | best: deblurred RL20 | 0.00114 | 0.986 | 0.611 |
| Run3_f22 | impulse | 78.1 px/s | 8 px | as is | 0.02653 | 0.672 | 0.306 |
| Run3_f22 | impulse | 78.1 px/s | 8 px | smoothed 8 px | 0.00687 | 0.926 | 0.361 |
| Run3_f22 | impulse | 78.1 px/s | 8 px | best: smoothed 16 px | 0.00538 | 0.943 | 0.412 |

Reading these:

- Coded and box had the same blur (250 px). The box wins on MSE with either method
  (0.00117 against 0.00324 with lam 0.05;
  0.00114 against 0.00202 at the best settings), and is ahead on detail too
  (0.61 against 0.55 at the best settings).
- The f/11 settings (lam 0.05, RL40) are too weak for this light: they amplify the noise. The coded
  photo's best setting is lam 0.5 or RL5; the box hardly changes.
- The impulse is last on both MSE and detail. At 1/10 s and f/22 it is grainy, but it was also taken
  1024 px from where the car stood for the reference, the furthest of the three, so part of its
  error is the car's reflections (see "Distance from the reference spot" below).
- Why the box keeps up is not settled. At 250 px a box blur loses little detail and a
  deblur recovers some of it, and the box has twice the light with no noise amplification, while
  the deblur of the coded photo amplifies the noise. The boxes that did badly had both longer blur
  and a longer distance from the reference spot (below), so these runs cannot say which of the two
  mattered. In the one f/22 pair with long blur (Run1_2's coded photo, 400 px, against Run1_2_base's
  box, 450 px; different runs and light) the coded photo won (best settings MSE 0.00201 against
  0.00248, detail 0.65 against 0.38), but that box was also 784 px from its reference spot.

## Distance from the reference spot

The reference is the car standing still at one place; each moving photo catches it somewhere else.
The car's reflections (the window glint and the bright band along the top of the "95") and the lamp
light on it change with its position, and the score fits only one brightness and contrast to the
whole picture, so a photo taken far from the reference spot scores worse however sharp it is.
Across the f/22 and f/5.6 boxes, the best MSE was 0.0008 to 0.0013 within 450 px of the reference
spot and 0.0025 to 0.0059 from 780 to 1,120 px; the f/5.6 impulses went from 0.0003 at 124 px to
0.0054 at 1,068 px. Distance here (full-resolution px, from the alignment of each photo as taken):

| Photo | Run | Distance from its reference spot |
| --- | --- | --- |
| coded | Run3_f22 | 592 px |
| box | Run2_f22 | 432 px |
| impulse | Run3_f22 | 1024 px |

The coded photo and the box are at similar distances, so their comparison is fair on this count.

## Panel leakage

The black panel lets through **1.57%** of the light an open panel does (Run1_2; f/11's Run8
gave 1.24%). Worked out from the mean levels with the dark subtracted, where the leakage photo is
shut for all 5 s and the reference is open 3.2 s and shut 1.8 s:

leak = 3.2 L / (5 O − 1.8 L), with L = leakage − dark = 0.00012
and O = reference − dark = 0.00495.

The car stood still for the reference and moved for the leakage photo, so this assumes the scene
averaged the same in the two. At f/22 the levels are small, so this is rough.

## Dark photo

The dark photo (lens cap on, 5 s, Run1_2) averages 0.00002 of full scale with a spread of
0.0010: the camera's own noise. The scores above do not subtract it.

## How the numbers were made

- Each photo's green channel is read from the .cr2, hot pixels are median-filtered out, and it is
  binned 4 x 4 (`flutter_deblur.load`).
- Deblur: each row is undone with the code (or the box) stretched over the blur length, either by
  `flutter_deblur.deconvolve` (Tikhonov, lam 0.05 or the best of 0.02 to 1) or by Richardson-Lucy
  (40 iterations, or the best of 5 to 80), which never goes below black.
- Blur length: tried from 200 to 1200 px in 25 px steps with lam 0.05, moving left; the lowest MSE
  is kept. Only left is tried because the car always drives left: in this dim light the
  time-reversed code can score a few percent better by chance (it did for Run3_f22's coded photo,
  whose position in the photos shows it moving left). Every f/11 coded photo also came out left.
- Score: each result is lined up with its run's reference by `flutter_deblur.Scorer`, then by the
  best of 3 rows and 48 px either side of that. Over the middle half of the overlap, after fitting
  brightness and contrast to the reference:
  - **MSE**: mean squared error, reference scaled to its 99.5th percentile. Lower is better.
  - **NCC**: correlation with the reference, 1 is a perfect match.
  - **Detail**: correlation of just the fine detail (features 8 to 32 px across, the size of the
    strokes in the "95") with the reference's. MSE favours smooth pictures; detail does not.
- Smoothed impulse: blurred by 2 binned px (8 px) as at f/11, and by 1 to 4 binned px (4 to 16 px)
  for the best setting, all below the 20 px the lens and setup resolve.

To make `results.json` and the pictures again from the code folder:

    .venv/bin/python captures/flutter_5s_ISO100_f22/score.py
