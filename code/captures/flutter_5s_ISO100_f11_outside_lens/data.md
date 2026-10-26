# Flutter shutter results: 5 s, ISO 100, f/11

The best photo of each kind taken with the flutter shutter at one camera setting, the numbers
for each, and how they were worked out. `results.json` has every number; `data.csv` has the
results table for a spreadsheet; `score.py` makes `results.json` again from the photos here.

## Settings

Every photo here was taken with these (checked from the photos' EXIF):

| Setting | Value |
| --- | --- |
| Camera | Canon 60D, mode dial on M, RAW (.cr2, with a .dng copy) |
| Shutter | 5 s (impulse photos 1/10 s) |
| ISO | 100 |
| Aperture | f/11 |
| Focal length | 51 mm (Run8, the leakage photos: 55 mm) |

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

Light: two levels, set by the room lamps, not the camera. Measured by the reference photo's mean
level (fraction of the sensor's full scale):

| Light | Runs | Reference mean |
| --- | --- | --- |
| Bright | Run14 | 0.0556 |
| Dim, about 2.5 times less | Run16, Run17_box, Run19 | 0.0217 to 0.0230 |

## What is here

| Folder | Run | Photos | Used for |
| --- | --- | --- | --- |
| `coded/` | Run19 | reference, coded | The flutter shutter result (dim light) |
| `box/` | Run17_box | reference, box | The ordinary long exposure to compare with (dim light) |
| `impulse_and_dark/` | Run16 | reference, impulse, dark | The short exposure to compare with, and the camera's own noise (dim light) |
| `bright_light/` | Run14 | reference, impulse, coded, box, dark | The same comparison in bright light |
| `leakage/` | Run8 | box, leakage, dark | How much light the black panel lets through |

Each folder also has the run's manifest (`*_manifest.json`) and each frame's trace (`*.json`:
the code, when each chop played, the shutter time). The reference in each folder is that run's
own photo of the car standing still, and is what that run's photos are scored against.

Images (Run19):

- `compare.png`: coded photo, deblurred (500 px, lam 0.05), reference, stacked.
- `95_compare.png`: the "95" up close: reference, coded as is, deblurred lam 0.05 and RL40 at 475 px.
- `deblurred_RL40_475px.png`: the best deblur, full frame.

## Results

Car speed is in image pixels per second at full resolution (about 5,200 px across the frame). For coded
and box photos it is the blur length the deblur found divided by the 3.2 s code. For impulse
photos it is taken from the coded photo of the same run, and the blur is that speed over 1/10 s.

Dim light:

| Run | Photo | Car speed | Blur | Version | MSE | NCC | Detail |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Run19 | coded | 148.4 px/s | 475 px | as is | 0.00535 | 0.942 | 0.164 |
| Run19 | coded | 148.4 px/s | 475 px | deblurred lam 0.05 | 0.00187 | 0.980 | 0.761 |
| Run19 | coded | 148.4 px/s | 475 px | deblurred RL40 | 0.00122 | 0.987 | 0.779 |
| Run17_box | box | 93.8 px/s | 300 px | as is | 0.00170 | 0.980 | 0.610 |
| Run17_box | box | 93.8 px/s | 300 px | deblurred lam 0.05 | 0.00118 | 0.986 | 0.633 |
| Run17_box | box | 93.8 px/s | 300 px | deblurred RL40 | 0.00113 | 0.987 | 0.664 |
| Run16 | impulse | 156.2 px/s | 16 px | as is | 0.00608 | 0.938 | 0.758 |
| Run16 | impulse | 156.2 px/s | 16 px | smoothed 8 px | 0.00131 | 0.987 | 0.804 |

Bright light:

| Run | Photo | Car speed | Blur | Version | MSE | NCC | Detail |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Run14 | coded | 164.1 px/s | 525 px | as is | 0.01277 | 0.870 | -0.008 |
| Run14 | coded | 164.1 px/s | 525 px | deblurred lam 0.05 | 0.00559 | 0.948 | 0.404 |
| Run14 | coded | 164.1 px/s | 525 px | deblurred RL40 | 0.00494 | 0.953 | 0.413 |
| Run14 | box | 78.1 px/s | 250 px | as is | 0.00768 | 0.931 | 0.440 |
| Run14 | box | 78.1 px/s | 250 px | deblurred lam 0.05 | 0.00713 | 0.936 | 0.480 |
| Run14 | box | 78.1 px/s | 250 px | deblurred RL40 | 0.00768 | 0.931 | 0.424 |
| Run14 | impulse | 164.1 px/s | 16 px | as is | 0.00119 | 0.988 | 0.946 |
| Run14 | impulse | 164.1 px/s | 16 px | smoothed 8 px | 0.00032 | 0.997 | 0.952 |

Reading these:

- Run19's coded photo had about 1.6 times the blur of Run17's box (475 px against
  300 px) and still matches it on MSE (0.00122 against
  0.00113, RL40) and beats it on detail (0.779
  against 0.664). The two come from different runs, so the car's speed and
  position differ; the unfairness favours the box.
- In dim light the deblurred coded photo is level with the impulse once the impulse's grain is
  smoothed. In bright light the impulse is far better: there is enough light for a 1/10 s photo
  to be clean, so blur is not worth trading for light.
- In Run14 the car slowed between the coded photo (164.1 px/s) and the box
  (78.1 px/s), so the box had half the blur.

## Panel leakage

The black panel lets through **1.24%** of the light an open panel does (Run8). Worked out
from the mean levels with the dark subtracted, where the leakage photo is shut for all 5 s and
the box is open 3.2 s and shut 1.8 s:

leak = 3.2 L / (5 B − 1.8 L), with L = leakage − dark = 0.00165
and B = box − dark = 0.08567.

The car was moving in both, so this assumes the scene averaged the same in the two. The deblur
treats shut chops as fully shut (leak 0); allowing for 1.5% made no difference to Run16's scores.

## Dark photos

The dark photos (lens cap on, 5 s) average 0.00006 (Run16) and
0.00015 (Run14) of full scale with a spread of about
0.0010: the camera's own noise. The scores above do not subtract
them; subtracting the dark made no difference to Run16's scores.

## How the numbers were made

- Each photo's green channel is read from the .cr2, hot pixels are median-filtered out, and it is
  binned 4 x 4 (`flutter_deblur.load`).
- Deblur: each row is undone with the code (or the box) stretched over the blur length, either by
  `flutter_deblur.deconvolve` (Tikhonov, lam 0.05) or by 40 iterations of Richardson-Lucy, which
  never goes below black.
- Blur length: tried from 200 to 1200 px in 25 px steps, moving left and right; the lowest MSE is
  kept. Every coded photo was moving left.
- Score: each result is lined up with the reference by `flutter_deblur.Scorer`, then by the best
  of 3 rows and 48 px either side of that (the scorer alone sometimes locks onto the wrong match).
  Over the middle half of the overlap, after fitting brightness and contrast to the reference:
  - **MSE**: mean squared error, reference scaled to its 99.5th percentile. Lower is better.
  - **NCC**: correlation with the reference, 1 is a perfect match.
  - **Detail**: correlation of just the fine detail (features 8 to 32 px across, the size of the
    strokes in the "95") with the reference's. MSE favours smooth pictures; detail does not.
- Smoothed impulse: blurred by 2 binned px (8 px) to remove grain, below the 20 px the lens and
  setup resolve, so a smooth blurry picture and a sharp grainy one are compared fairly.

To make `results.json` again from the code folder:

    .venv/bin/python captures/flutter_5s_ISO100_f11_outside_lens/score.py
