# Flutter shutter results: 5 s, ISO 100, f/5.6

The most closely matched photo of each kind taken with the flutter shutter at f/5.6, the numbers
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
| Aperture | f/5.6 |
| Focal length | 55 mm (both runs) |

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
where they were). The zoom sat at 55 mm for these runs, against 51 mm at f/11 and in part of
f/22, so everything in the photo is 1.08 times bigger than at f/11. Light, measured by each
run's reference photo (the car standing still, panel open 3.2 s), as a fraction of the sensor's full scale:

| Run | Reference mean |
| --- | --- |
| Run2_f5_6 | 0.0775 |
| Run1_f5_6 | 0.0887 |

The f/11 dim runs measured 0.0217 to 0.023, so these had 3.4 to
4.1 times more light, against the 4 times the aperture alone gives.

## What is here

| Folder | Run | Photos | Used for |
| --- | --- | --- | --- |
| `coded_and_box/` | Run2_f5_6 | reference, coded, box | The flutter shutter result, and the ordinary long exposure to compare with |
| `impulse/` | Run1_f5_6 | reference, impulse | The short exposure to compare with |
| `leakage_and_dark/` | Run2_f5_6 | reference, leakage, dark | How much light the black panel lets through, and the camera's own noise |

Each folder also has the run's manifest (`*_manifest.json`) and each frame's trace (`*.json`:
the code, when each chop played, the shutter time). Each photo is scored against its own run's
reference (Run2_f5_6's reference is in two folders; both are the same file). The other f/5.6 photos
were deleted from `captures/flutter`; their scores and pictures are in `out/flutter`.

Why these: a fair comparison needs the same light, a similar blur and a similar distance from where
the car stood for the reference (see "Distance from the reference spot" below). Run2_f5_6's coded
photo and box come from one run, at similar distances (404 and 268 px), with the box
20% shorter in blur (300 against 375 px). Run1_f5_6's own
coded photo and box were at very different distances (172 and 1,120 px), which is unfair to the box.
The impulse comes from Run1_f5_6: Run2_f5_6's impulse was 1,068 px from its reference spot and its
score is spoiled by the car's reflections. Run3_f5_6_2 had twice the light of the others (the lamps
were probably changed) and a reference that clips, so none of it is used. The other f/5.6 takes
(same method):

| Run | Photo | Reference mean | Blur | Distance | Version | MSE | Detail |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Run1_f5_6 | coded | 0.0887 | 425 px | 172 px | lam 0.05 | 0.00120 | 0.662 |
| Run1_f5_6 | box | 0.0887 | 475 px | 1120 px | lam 0.05 | 0.00418 | 0.350 |
| Run2_f5_6 | impulse | 0.0775 | 11.7 px | 1068 px | smoothed 8 px | 0.00548 | 0.667 |
| Run3_f5_6_2 | coded | 0.1552 | 225 px | 680 px | lam 0.05 | 0.00267 | 0.618 |
| Run3_f5_6_2 | box | 0.1552 | about 180 px (sweep failed) | 1124 px | lam 0.05 | 0.00597 | 0.507 |
| Run3_f5_6_2 | impulse | 0.1552 | 7.0 px | 124 px | smoothed 8 px | 0.00038 | 0.960 |

Clipping: the photos used here have 0.0002% or fewer pixels at the white level
(hot pixels). Run1_f5_6's box, not used, clipped 0.07% in the car's reflection.

Images:

- `compare.png`: Run2_f5_6 coded photo, deblurred (375 px, lam 0.05), reference, stacked.
- `95_compare.png`: the "95" up close: reference, coded as is, deblurred lam 0.05 and RL40 at 375 px.
- `95_baselines.png`: the "95" up close. Top, next to Run2_f5_6's reference: coded deblurred at its best
  lam (0.05), box as is and deblurred RL40. Bottom, next to Run1_f5_6's reference: impulse as is,
  smoothed 8 px and at its best smoothing.
- `deblurred_best_lam0.05_375px.png`: the coded photo's best lam deblur, full frame.

## Results

Car speed is in image pixels per second at full resolution (about 5,200 px across the frame). For coded
and box photos it is the blur length the deblur found divided by the 3.2 s code. For the impulse
photo it is taken from the coded photo of its own run (Run1_f5_6's, 425 px; not kept here), and the
blur is that speed over 1/10 s.

The same method as f/11 (lam 0.05, RL40, impulse smoothed 8 px), then each photo at its best
setting (lowest MSE of lam 0.02 to 1, RL 5 to 80 iterations, impulse smoothed 4 to 16 px):

| Run | Photo | Car speed | Blur | Version | MSE | NCC | Detail |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Run2_f5_6 | coded | 117.2 px/s | 375 px | as is | 0.00387 | 0.954 | 0.376 |
| Run2_f5_6 | coded | 117.2 px/s | 375 px | deblurred lam 0.05 | 0.00256 | 0.970 | 0.574 |
| Run2_f5_6 | coded | 117.2 px/s | 375 px | deblurred RL40 | 0.00285 | 0.966 | 0.583 |
| Run2_f5_6 | coded | 117.2 px/s | 375 px | best: deblurred lam 0.05 | 0.00256 | 0.970 | 0.574 |
| Run2_f5_6 | coded | 117.2 px/s | 375 px | best: deblurred RL20 | 0.00278 | 0.967 | 0.587 |
| Run2_f5_6 | box | 93.8 px/s | 300 px | as is | 0.00223 | 0.973 | 0.362 |
| Run2_f5_6 | box | 93.8 px/s | 300 px | deblurred lam 0.05 | 0.00090 | 0.989 | 0.720 |
| Run2_f5_6 | box | 93.8 px/s | 300 px | deblurred RL40 | 0.00076 | 0.991 | 0.761 |
| Run2_f5_6 | box | 93.8 px/s | 300 px | best: deblurred lam 0.02 | 0.00081 | 0.990 | 0.754 |
| Run2_f5_6 | box | 93.8 px/s | 300 px | best: deblurred RL40 | 0.00076 | 0.991 | 0.761 |
| Run1_f5_6 | impulse | 132.8 px/s | 13 px | as is | 0.00132 | 0.988 | 0.935 |
| Run1_f5_6 | impulse | 132.8 px/s | 13 px | smoothed 8 px | 0.00093 | 0.991 | 0.942 |
| Run1_f5_6 | impulse | 132.8 px/s | 13 px | best: smoothed 8 px | 0.00093 | 0.991 | 0.942 |

Reading these:

- Lowest MSE: the box. Most detail: the impulse. At its best setting the box reaches MSE
  0.00076 (RL40), the impulse 0.00093 and the coded photo 0.00256 (lam 0.05).
- The box beats the coded photo here on both MSE and detail, but it had 20% less blur. In
  Run1_f5_6, where the box had 12% more blur than the coded photo and was much further from its
  reference spot, the coded photo won (MSE 0.00120 against 0.00418). With these runs, f/5.6 does not
  settle which of the two is better.
- The impulse is the sharpest (detail 0.94 as is): with this much light, 1/10 s is enough for a
  clean photo, as at f/11 in bright light. It was taken 844 px from its reference spot, so its
  MSE is if anything too high.
- The f/11 settings (lam 0.05, RL40) suit this light: the best settings change the scores little.

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
| coded | Run2_f5_6 | 404 px |
| box | Run2_f5_6 | 268 px |
| impulse | Run1_f5_6 | 844 px |

## Panel leakage

The black panel lets through **1.11%** of the light an open panel does (Run2_f5_6; f/11's Run8
gave 1.24%, Run1_f5_6 1.29%). Worked out from the mean levels with the dark subtracted, where the
leakage photo is shut for all 5 s and the reference is open 3.2 s and shut 1.8 s:

leak = 3.2 L / (5 O − 1.8 L), with L = leakage − dark = 0.00134
and O = reference − dark = 0.07740.

The car stood still for the reference and moved for the leakage photo, so this assumes the scene
averaged the same in the two.

## Dark photo

The dark photo (lens cap on, 5 s, Run2_f5_6) averages 0.00010 of full scale with a spread of
0.0010: the camera's own noise. The scores above do not subtract it.

## How the numbers were made

- Each photo's green channel is read from the .cr2, hot pixels are median-filtered out, and it is
  binned 4 x 4 (`flutter_deblur.load`).
- Deblur: each row is undone with the code (or the box) stretched over the blur length, either by
  `flutter_deblur.deconvolve` (Tikhonov, lam 0.05 or the best of 0.02 to 1) or by Richardson-Lucy
  (40 iterations, or the best of 5 to 80), which never goes below black.
- Blur length: tried from 200 to 1200 px in 25 px steps with lam 0.05, moving left; the lowest MSE
  is kept. Only left is tried because the car always drives left (in dim light the time-reversed
  code can score a few percent better by chance). Every f/11 coded photo also came out left.
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

    .venv/bin/python captures/flutter_5s_ISO100_f5.6_outside_lens/score.py
