# Flutter shutter results: 5 s, ISO 100, f/5.6, LCD inside the lens

One run with the LCD in the slot cut into the extension tube, between the lens and the sensor.
`data.csv` has every score. The run's folder holds its photos, traces, manifest, scores and pictures.

## Settings

Every photo here was taken with these (checked from the photos' EXIF):

| Setting | Value |
| --- | --- |
| Camera | Canon 60D, mode dial on M, RAW (.cr2, with a .dng and a .jpg copy) |
| Shutter | 5 s (impulse photo 1/10 s) |
| ISO | 100 |
| Aperture | f/5.6 |
| Focal length | 55 mm |
| LCD | Inside the extension tube |

Flutter tab in the Experiments window:

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

Light: the reference photo's mean level is 0.0533 of full scale. The outside-lens f/5.6 runs
measured 0.0775 to 0.0887.

## What is here

| Path | Contents |
| --- | --- |
| `f56_run1_lcd_inside/` | The six photos, each frame's trace `.json`, the manifest, the scores (`f56_run1_lcd_inside_100ms_invert.json`) and the pictures |
| `data.csv` | Every score in the table below, plus the fixed settings (lam 0.05, RL40, impulse smoothed 8 px) |

Pictures in the run's folder:

- `compare.png`: coded photo, deblurred (500 px, lam 0.05) and reference, stacked.
- `95_compare.png`: the "95" up close. Reference, coded as is, deblurred lam 0.05 and RL40.
- `95_baselines.png`: the "95" up close. Top: reference, coded as is, deblurred lam 0.05 and RL40.
  Bottom: reference, box as is, box deblurred lam 0.05, impulse as is and smoothed 8 px.
- `f56_run1_lcd_inside_100ms_invert_<photo>*.png`: each photo and deblur, full frame.

## Results

Each photo at its best setting (lowest MSE of lam 0.02 to 1, RL 5 to 80 iterations, impulse
smoothed 4 to 16 px). Distance is how far the photo sat from the reference spot.

| Photo | Blur | Car speed | Version | MSE | NCC | Detail | Distance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| coded | 500 px | 156.2 px/s | as is | 0.01066 | 0.857 | 0.164 | 120 px |
| coded | 500 px | 156.2 px/s | best: deblurred RL20 | 0.00480 | 0.939 | 0.690 | 32 px |
| box | 400 px | 125.0 px/s | as is | 0.00915 | 0.844 | 0.162 | 1064 px |
| box | 400 px | 125.0 px/s | best: deblurred lam 0.05 | 0.00734 | 0.872 | 0.380 | 1320 px |
| impulse | 16 px | 156.2 px/s | as is | 0.01164 | 0.838 | 0.280 | 1272 px |
| impulse | 16 px | 156.2 px/s | best: smoothed 16 px | 0.00986 | 0.864 | 0.377 | 1264 px |

SNR gain of the deblurred coded photo, 10 log10(MSE baseline / MSE coded): +1.8 dB over the box
and +3.1 dB over the impulse.

Reading these:

- The box and impulse sat 1,064 to 1,320 px from the reference spot. The coded photo sat 32 to
  280 px from it. That favours the coded photo, probably by more than the 1.8 to 3.1 dB it wins by.
  Do not quote these gains as a result.
- The coded photo had 1.25 times the blur of the box (500 against 400 px). That favours the box.
- The impulse's best smoothing is the largest the script tries, so more smoothing might lower its
  MSE a little.
- The deblur works. The 95 comes back with faint repeated edges and the MSE falls 3.5 dB from the
  coded photo as taken.

## Panel leakage

The black panel lets through 0.43% of the light an open panel does. Worked out as in the
outside-lens folders: leak = 3.2 L / (5 B − 1.8 L), with L = leakage − dark = 0.00022 and
B = box − dark = 0.03275. The car was moving in both photos, so this is rough.

## Dark photo

The dark photo (lens cap on, 5 s) averages 0.00094 of full scale with a spread of 0.0011. The
scores do not subtract it.

## How the numbers were made

`flutter_score.py`, the same method as the outside-lens f/5.6 and f/22 folders. Each photo's green
channel is read, median-filtered and binned 4 x 4. The coded and box photos are swept over blur
lengths from 200 to 1200 px in 25 px steps with the car moving left (lam 0.05), then deblurred at
every setting at the best length. Each result is aligned to the reference, fitted to it by a gain
and an offset and scored over the middle half of the frame width. Distance is the horizontal shift
between the photo and its reference at that alignment, in full-resolution px.

To make the scores and pictures again, from the code folder (about 4.5 min):

    .venv/bin/python flutter_score.py f56_run1_lcd_inside --dir captures/flutter_5s_ISO100_f5.6_inside_lens/f56_run1_lcd_inside --out captures/flutter_5s_ISO100_f5.6_inside_lens --folder f56_run1_lcd_inside

Add `--pictures-only` to redraw the pictures from the saved scores in a few seconds.
