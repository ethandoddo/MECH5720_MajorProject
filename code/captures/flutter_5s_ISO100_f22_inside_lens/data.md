# Flutter shutter results: 5 s, ISO 100, f/22, LCD inside the lens

Two runs with the LCD in the slot cut into the extension tube, both taken on 28 October 2026.
`data.csv` has every score. Each run's folder holds its photos, traces, manifest, scores and
pictures.

`f22_inside_lcd_run2` (18:28) is the run to use. The first run, `f22_lcd_inside` (16:33), did not
give a usable comparison. The car came towards the camera as it drove left, so its moving photos
show the car bigger and lower than the reference does. The section on the first run explains this.

## Settings

Every photo here was taken with these (checked from the photos' EXIF):

| Setting | Value |
| --- | --- |
| Camera | Canon 60D, mode dial on M, RAW (.cr2, with a .dng and a .jpg copy) |
| Shutter | 5 s (impulse photos 1/10 s) |
| ISO | 100 |
| Aperture | f/22 (both runs) |
| Focal length | 55 mm (both runs) |
| LCD | Inside the extension tube |

Flutter tab in the Experiments window, the same for both runs:

| Setting | Value |
| --- | --- |
| Code | Designed 32 chops: `10001101101001011000001111010101`, 16 open, score 0.075 |
| Chop | 100 ms, so the code lasts 3.2 s |
| Lead | 1000 ms |
| Tail | 200 ms |
| Panel | Invert |
| Impulse shutter | 1/10 s |
| Photo | Camera as it is |
| Repeats | 1 |
| Take | reference, impulse, coded, box, leakage, dark |
| Target distance | Not recorded |

Light, measured by each run's reference photo as a fraction of the sensor's full scale:

| Run | Reference mean |
| --- | --- |
| f22_inside_lcd_run2 | 0.01032 |
| f22_lcd_inside | 0.00605 |

The two runs used the same settings, yet the second reference is 1.7 times brighter. Either the
light on the car changed between the runs or the car filled a different part of the frame. Nothing
recorded says which. The f/11 runs inside the lens measured 0.0136 to 0.0143. That is 1.3 to 1.4
times the second run, against the 4 times the aperture gives. The f/22 runs outside the lens
measured 0.0065 to 0.0071.

## What is here

| Path | Contents |
| --- | --- |
| `f22_inside_lcd_run2/` | The run to use: six photos, traces, manifest, scores (`f22_inside_lcd_run2_100ms_invert.json`) and pictures |
| `f22_lcd_inside/` | The first run, the same set. Not usable |
| `data.csv` | Every score in the tables below, plus the fixed settings (lam 0.05, RL40, impulse smoothed 8 px) |

Pictures in each run's folder:

- `compare.png`: coded photo, deblurred (lam 0.05) and reference, stacked.
- `95_compare.png`: the "95" up close. Reference, coded as is, deblurred lam 0.05 and RL40.
- `95_baselines.png`: the "95" up close. Top: reference, coded as is, deblurred lam 0.05 and RL40.
  Bottom: reference, box as is, box deblurred (lam 0.05 or RL40, whichever scores better), impulse
  as is and smoothed 8 px.
- `<run>_100ms_invert_<photo>*.png`: each photo and deblur, full frame.

## Results

Each photo at its best setting (lowest MSE of lam 0.02 to 1, RL 5 to 80 iterations, impulse
smoothed 4 to 16 px). Distance is how far the photo sat from the reference spot.

| Run | Photo | Blur | Car speed | Version | MSE | NCC | Detail | Distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| f22_inside_lcd_run2 | coded | 400 px | 125.0 px/s | as is | 0.00707 | 0.895 | 0.242 | 744 px |
| f22_inside_lcd_run2 | coded | 400 px | 125.0 px/s | best: deblurred RL10 | 0.00467 | 0.932 | 0.560 | 776 px |
| f22_inside_lcd_run2 | box | 500 px | 156.2 px/s | as is | 0.00528 | 0.925 | 0.347 | 268 px |
| f22_inside_lcd_run2 | box | 500 px | 156.2 px/s | best: deblurred lam 0.05 | 0.00376 | 0.948 | 0.543 | 540 px |
| f22_inside_lcd_run2 | impulse | 12.5 px | 125.0 px/s | as is | 0.02208 | 0.588 | 0.339 | 1572 px |
| f22_inside_lcd_run2 | impulse | 12.5 px | 125.0 px/s | best: smoothed 16 px | 0.00821 | 0.870 | 0.275 | 1548 px |
| f22_lcd_inside | coded | 250 px | 78.1 px/s | as is | 0.02854 | 0.674 | 0.110 | 688 px |
| f22_lcd_inside | coded | 250 px | 78.1 px/s | best: deblurred lam 1 | 0.01793 | 0.810 | 0.216 | 1052 px |
| f22_lcd_inside | box | 200 px or less | | as is | 0.03580 | 0.559 | 0.149 | 1188 px |
| f22_lcd_inside | box | 200 px or less | | best: deblurred RL5 | 0.03512 | 0.574 | 0.216 | 1228 px |
| f22_lcd_inside | impulse | 8 px | 78.1 px/s | as is | 0.04512 | 0.104 | 0.039 | 1036 px |
| f22_lcd_inside | impulse | 8 px | 78.1 px/s | best: smoothed 12 px | 0.04485 | 0.129 | 0.054 | 1036 px |

SNR gain of the deblurred coded photo, 10 log10(MSE baseline / MSE coded):

| Run | Over the box | Over the impulse |
| --- | --- | --- |
| f22_inside_lcd_run2 | −0.9 dB | +2.5 dB |
| f22_lcd_inside | +2.9 dB (not usable) | +4.0 dB (not usable) |

The MSEs recomputed without rounding give −0.94 and +2.45 dB for `f22_inside_lcd_run2`, so the
rounded gains hold.

Reading these, for `f22_inside_lcd_run2`:

- The car stayed on its line. Each photo's row-by-row brightness profile was matched to the
  reference's, which motion blur along the rows does not change. The coded and box photos fit the
  reference within 0.5% in size and 8 px in height.
- The box beats the coded photo by 0.9 dB. The f/22 run outside the lens gave the same margin.
- The box sat 270 to 540 px from the reference spot and the coded photo 580 to 780 px. That
  favours the box. In the f/5.6 and f/11 runs inside the lens the box sat 1,060 to 2,050 px
  away, which favoured the coded photo.
- The box had 1.25 times the blur of the coded photo (500 against 400 px). That favours the coded
  photo. The car sped up from 125 to 156 px/s between the two photos.
- The impulse sat 1,550 to 1,570 px from the reference spot. That favours the coded photo and
  inflates its gain over the impulse.
- The impulse's best smoothing is the largest the script tries.
- The deblur works. The 95 comes back with faint repeated edges and the MSE falls 1.8 dB from the
  coded photo as taken. The best lam (0.1, MSE 0.00468) and the best RL (10 iterations, 0.00467)
  tie.

## Why the first run is not usable

Do not quote the first run's SNR gains. They come from baselines that matched the reference even
worse than the coded photo did.

- The moving photos do not match the reference. `f22_lcd_inside_100ms_invert_coded.png` shows the
  car bigger and lower than the reference does. The box photo shows the car bigger again. The car
  came towards the camera as it drove left. The row profile check needed a size change of at least
  20%, the limit of the check. Every photo scores an NCC below 0.81 against the reference.
- The deblur cannot fit that motion. The blur sweep is nearly flat, with the coded MSE within
  0.0013 of itself from 200 to 375 px. Deblurring at lam 0.05 makes the coded photo worse, 0.0315
  against 0.0285 as taken. The best setting is lam 1, the heaviest the script tries. It smooths the
  photo and moves the alignment by 364 px. The 95 does not come back.
- The impulse recorded almost nothing: a mean of 0.00021 of full scale against 0.00605 for the
  reference. Its alignment hit the vertical search limit, so its score and distance are
  meaningless.
- The box's MSE rises from 200 px, the bottom of the sweep, so its blur is 200 px or less.

## Panel leakage

Worked out as in the other folders: leak = 3.2 L / (5 B − 1.8 L), with L = leakage − dark and
B = box − dark.

| Run | L | B | Leakage |
| --- | --- | --- | --- |
| f22_inside_lcd_run2 | 0.00002 | 0.00952 | 0.13% |
| f22_lcd_inside | −0.00005 | 0.00439 | Below what this light can measure |

At f/22 the leakage photo sits within 0.00005 of the dark photo in both runs, so neither number
means much.

## Dark photos

The dark photos (lens cap on, 5 s) average 0.00067 (`f22_inside_lcd_run2`) and 0.00037
(`f22_lcd_inside`) of full scale with a spread of about 0.0011. The scores do not subtract them.

## How the numbers were made

`flutter_score.py`, the same method as the other folders. Each photo's green channel is read,
median-filtered and binned 4 x 4. The coded and box photos are swept over blur lengths from 200 to
1200 px in 25 px steps with the car moving left (lam 0.05), then deblurred at every setting at the
best length. Each result is aligned to the reference, fitted to it by a gain and an offset and
scored over the middle half of the frame width. Distance is the horizontal shift between the photo
and its reference at that alignment, in full-resolution px.

To make the scores and pictures again, from the code folder (about 5.5 min a run):

    .venv/bin/python -m aperture.analysis.flutter_score f22_inside_lcd_run2 --dir captures/flutter_5s_ISO100_f22_inside_lens/f22_inside_lcd_run2 --out captures/flutter_5s_ISO100_f22_inside_lens --folder f22_inside_lcd_run2
    .venv/bin/python -m aperture.analysis.flutter_score f22_lcd_inside --dir captures/flutter_5s_ISO100_f22_inside_lens/f22_lcd_inside --out captures/flutter_5s_ISO100_f22_inside_lens --folder f22_lcd_inside

Add `--pictures-only` to redraw the pictures from the saved scores in a few seconds.
