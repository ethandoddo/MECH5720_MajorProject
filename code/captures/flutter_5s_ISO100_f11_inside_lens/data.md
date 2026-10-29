# Flutter shutter results: 5 s, ISO 100, f/11, LCD inside the lens

Two runs with the LCD in the slot cut into the extension tube, between the lens and the sensor.
`data.csv` has every score. Each run's folder holds its photos, traces, manifest, scores and
pictures.

`f22_run1_lcd_inside` was meant to be the f/22 run, but the camera stayed at f/11. Every photo's
EXIF says f/11, and its reference is as bright as the other f/11 run's (0.0136 against 0.0143 of
full scale, where f/22 would give about a quarter). It is a second f/11 run. It keeps its name
because the file names and the manifest use it.

## Settings

Every photo here was taken with these (checked from the photos' EXIF):

| Setting | Value |
| --- | --- |
| Camera | Canon 60D, mode dial on M, RAW (.cr2, with a .dng and a .jpg copy) |
| Shutter | 5 s (impulse photos 1/10 s) |
| ISO | 100 |
| Aperture | f/11 (both runs) |
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
| f11_run1_lcd_inside_2 | 0.01433 |
| f22_run1_lcd_inside | 0.01356 |

The f/5.6 run inside the lens measured 0.0533, 3.7 to 3.9 times more, against the 4 times the
aperture gives.

## What is here

| Path | Contents |
| --- | --- |
| `f11_run1_lcd_inside_2/` | The first f/11 run: six photos, traces, manifest, scores (`f11_run1_lcd_inside_2_100ms_invert.json`) and pictures |
| `f22_run1_lcd_inside/` | The second f/11 run, the same set |
| `data.csv` | Every score in the tables below, plus the fixed settings (lam 0.05, RL40, impulse smoothed 8 px) |

Pictures in each run's folder:

- `compare.png`: coded photo, deblurred (lam 0.05) and reference, stacked.
- `95_compare.png`: the "95" up close. Reference, coded as is, deblurred lam 0.05 and RL40.
- `95_baselines.png`: the "95" up close. Top: reference, coded as is, deblurred lam 0.05 and RL40.
  Bottom: reference, box as is, box deblurred lam 0.05, impulse as is and smoothed 8 px.
- `<run>_100ms_invert_<photo>*.png`: each photo and deblur, full frame.

## Results

Each photo at its best setting (lowest MSE of lam 0.02 to 1, RL 5 to 80 iterations, impulse
smoothed 4 to 16 px). Distance is how far the photo sat from the reference spot.

| Run | Photo | Blur | Car speed | Version | MSE | NCC | Detail | Distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| f11_run1_lcd_inside_2 | coded | 375 px | 117.2 px/s | as is | 0.00394 | 0.958 | 0.556 | 1072 px |
| f11_run1_lcd_inside_2 | coded | 375 px | 117.2 px/s | best: deblurred lam 0.1 | 0.00297 | 0.969 | 0.646 | 1280 px |
| f11_run1_lcd_inside_2 | box | 200 px (sweep failed) | | as is | 0.00520 | 0.943 | 0.445 | 1972 px |
| f11_run1_lcd_inside_2 | box | 200 px (sweep failed) | | best: deblurred RL5 | 0.00507 | 0.944 | 0.456 | 1960 px |
| f11_run1_lcd_inside_2 | impulse | 12 px | 117.2 px/s | as is | 0.01879 | 0.784 | 0.361 | 36 px |
| f11_run1_lcd_inside_2 | impulse | 12 px | 117.2 px/s | best: smoothed 16 px | 0.00304 | 0.968 | 0.544 | 28 px |
| f22_run1_lcd_inside | coded | 450 px | 140.6 px/s | as is | 0.00542 | 0.932 | 0.290 | 972 px |
| f22_run1_lcd_inside | coded | 450 px | 140.6 px/s | best: deblurred lam 0.1 | 0.00360 | 0.956 | 0.483 | 1108 px |
| f22_run1_lcd_inside | box | 200 px or less | | as is | 0.00554 | 0.931 | 0.414 | 1592 px |
| f22_run1_lcd_inside | box | 200 px or less | | best: deblurred lam 0.1 | 0.00534 | 0.934 | 0.454 | 1696 px |
| f22_run1_lcd_inside | impulse | 14 px | 140.6 px/s | as is | 0.01796 | 0.761 | 0.503 | 124 px |
| f22_run1_lcd_inside | impulse | 14 px | 140.6 px/s | best: smoothed 16 px | 0.00265 | 0.969 | 0.718 | 124 px |

SNR gain of the deblurred coded photo, 10 log10(MSE baseline / MSE coded):

| Run | Over the box | Over the impulse |
| --- | --- | --- |
| f11_run1_lcd_inside_2 | +2.3 dB (not reliable) | +0.1 dB |
| f22_run1_lcd_inside | +1.7 dB | −1.3 dB |

Reading these:

- The box sweep failed in `f11_run1_lcd_inside_2`. Its MSE is 0.0053 at 200 px and jumps to
  0.035 from 225 px, so the alignment lost the car at every length past the first. Deblurring at
  200 px barely changes the box. Do not use the gain over this box.
- In `f22_run1_lcd_inside` the box's MSE rises steadily from 200 px, the bottom of the sweep. Its
  true blur may be under 200 px, which favours the box.
- The box sat 1,592 to 2,052 px from the reference spot in both runs. That favours the coded photo.
- The impulse sat 28 to 124 px from the reference spot and the coded photo 884 to 1,280 px. That
  favours the impulse, so the coded photo is probably a little better than these numbers say.
- The impulse's best smoothing is the largest the script tries in both runs.
- The deblur works. The 95 comes back with faint repeated edges and the MSE falls 1.2 dB
  (`f11_run1_lcd_inside_2`) and 1.8 dB (`f22_run1_lcd_inside`) from the coded photo as taken.

## Panel leakage

Worked out as in the outside-lens folders: leak = 3.2 L / (5 B − 1.8 L), with L = leakage − dark
and B = box − dark. The car was moving in both photos, and at f/11 the leakage level is close to
the dark level, so these are rough.

| Run | L | B | Leakage |
| --- | --- | --- | --- |
| f11_run1_lcd_inside_2 | 0.00006 | 0.01226 | 0.31% |
| f22_run1_lcd_inside | 0.00015 | 0.01212 | 0.80% |

## Dark photos

The dark photos (lens cap on, 5 s) average 0.00093 (`f11_run1_lcd_inside_2`) and 0.00080
(`f22_run1_lcd_inside`) of full scale with a spread of about 0.0011. The scores do not subtract
them.

## How the numbers were made

`flutter_score.py`, the same method as the outside-lens f/5.6 and f/22 folders. Each photo's green
channel is read, median-filtered and binned 4 x 4. The coded and box photos are swept over blur
lengths from 200 to 1200 px in 25 px steps with the car moving left (lam 0.05), then deblurred at
every setting at the best length. Each result is aligned to the reference, fitted to it by a gain
and an offset and scored over the middle half of the frame width. Distance is the horizontal shift
between the photo and its reference at that alignment, in full-resolution px.

To make the scores and pictures again, from the code folder (about 4.5 min a run):

    .venv/bin/python -m aperture.analysis.flutter_score f11_run1_lcd_inside_2 --dir captures/flutter_5s_ISO100_f11_inside_lens/f11_run1_lcd_inside_2 --out captures/flutter_5s_ISO100_f11_inside_lens --folder f11_run1_lcd_inside_2
    .venv/bin/python -m aperture.analysis.flutter_score f22_run1_lcd_inside --dir captures/flutter_5s_ISO100_f11_inside_lens/f22_run1_lcd_inside --out captures/flutter_5s_ISO100_f11_inside_lens --folder f22_run1_lcd_inside

Add `--pictures-only` to redraw the pictures from the saved scores in a few seconds.
