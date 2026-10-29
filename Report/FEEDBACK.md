# Pitch feedback and where the report answers it

This file is for the team. It does not compile into the report. It maps each comment from the pitch review to the
part of the draft that answers it. It also lists the decisions still open and the detail we cut from the paper for length.

## Professor's comments

| # | Comment | Where the draft answers it |
| --- | --- | --- |
| 1 | Some members shown doing mechanical work alone. Everyone should be across the whole project. | A paper has no roles section. See "Roles" below for a split that gives each member a sensing and signals result. |
| 2 | Custom bokeh needs one aperture. Depth needs one too, so motivate two and quantify. | Method 3.5.3 uses one star and expects the card to win. Method 3.5.1 gives the reason for a pair (complementary spectra, the case a static mask cannot serve). It then measures the pair against each single pattern at equal exposure, including the sparse-prior method of Levin et al. so the single pattern gets a fair run. |
| 3 | Flutter shutter is ambitious. Watch rolling shutter and display to exposure timing. | Method 3.5.4 makes the panel the shutter inside a bulb exposure, so the curtains move while the panel is black. It bounds the row-by-row panel update, sets the chop length from the measured switching time, records the played code with a photodiode and checks timing with an LED streak. |
| 4 | "Cut how?" for the extension tube slot. | Method 3.2, third paragraph: cradle, printed outline, rotary cutting disc, needle file, flocking tape, cut after Stage 1. |
| 5 | Interfacing, cables, headers? | Method 3.2, second paragraph: soldered header, seven jumper leads to the Arduino, SPI clock, USB from the laptop to the camera and to the Arduino, optocoupler on the E3 jack. The pin map goes in the README. |
| 6 | Processing described for one of the many tasks. | Depth: equations 6 and 7, hypotheses, windowing and the all-in-focus image. Refocus: equation 8 with tile centroids and dark-frame subtraction. Bokeh: highlight crop and NCC against field angle. Flutter: equation 9 and regularised least squares with the recorded code. |
| 7 | Define all acronyms (NCC was not defined). | The body defines every acronym at first use and the Table 1 caption repeats them. The abstract has none. |
| 8 | Measure how good, with a continuous metric and a baseline such as laser-cut against LCD. No pass/fail. | Table 1 gives every experiment a continuous metric and a baseline. Card masks cut from the same designs are the baseline for the panel tests. Card frames run at matched exposure time and again at matched signal. The gates and thresholds from the pitch are gone. |
| 9 | Flutter: MSE improvement against a deblurred exposure of the same length or a short noisy one, in low light. | Method 3.5.4, last paragraph: both baselines through the same panel and solver, four light levels set against the read-noise level. |
| 10 | The tube purchase is fine. | No change needed. |

Writing tips from the brief: each Method subsection opens with its topic, every caption names its axes, settings and
symbols. The text refers to every float before or next to it.

## Equations against the lectures

We checked every equation in the method against the slides in `Slides/` (not in git). Nothing contradicts them.

| Report | Lecture | Note |
| --- | --- | --- |
| Eq 1 to 3, blur size | Thin lens 1/f = 1/u + 1/v (Lec 2B p14), one thin lens for the whole system (2B p18), circle of confusion (1B p18) | The lectures give no blur formula. Ours follows from the thin-lens equation. The lecture uses u for object distance and m for magnification, where we use u for the pupil and m for the defocus scale. |
| Eq 2, PSF as scaled aperture | "The PSF ... is an image of the aperture", "depth affects the scale" (Lec 5 p8, p15) | Agrees in words. The sign flip across focus is ours. |
| Eq 4, noise | Poisson noise and Gaussian read noise (Lec 1B p35, p36) | Agrees. Dark current is negligible below 1 s (1B p35), so the 5 s flutter exposure gets a dark frame. |
| Eq 6, pair deconvolution | Wiener filter W = H*/(\|H\|^2 + K), K = S_n/S_x (Lec 5 p29) | Our equation is the two-frame Wiener filter. We switched the conjugate from a bar to a star to match. |
| Eq 8, refocus | Shift-and-add (Lec 8B p5), slope m = Δu/Δs = 1 − D/P_z (8B p4) | Same model with other letters and the opposite sign. |
| Eq 9, flutter | Light and motion blur tradeoff, three shutter rows (Lec 3A p11) | Agrees. The lectures do not cover leakage or code design. |
| Dim-light claim | SNR gain against J/σ_r^2 (Lec 3A p17, Mitra et al.), advantage reverses in bright light (Lec 5 p34) | Agrees. Plot the flutter result on the J/σ_r^2 axis so it sits next to the lecture plot. |

Changes made from the check: Fresnel number defined (half-width a), noise named as Poisson plus Gaussian read noise, Wiener filter named, flutter metric now SNR gain in dB against impulse imaging, dark frames for PSFs and flutter, reason for a one-tile scan given against multiplexing (Lec 2A, 3A), the refocus "one advantage" limited to edge width, the hobbyist citation moved to the maker (the lecturer links the same project on Lec 1A p25) and an AI-use placeholder added (Lec 1A p21 requires disclosure).

## Things the review found in the pitch plan

- **Refocus range.** A 3 x 3 scan leaves a refocused target with a third of its open-disc blur, 49 px at 700 mm. The pitch's refocus targets at 700 and 1300 mm cannot come out sharp. The draft moves them to 950, 1000 and 1050 mm and keeps 700 mm to show the failure.
- **Refocus baseline.** One frame at f/5.6 gives the same depth of field as the 3 x 3 refocus with no scan. The draft adds it as a baseline. The scan's one advantage is choosing the focal plane after capture.
- **Stage 2 focus.** A 25 mm tube on a 50 mm lens limits focus to 127 to 150 mm. Stage 2 cannot share a target with Stage 1.
- **Card against panel exposure.** The panel loses about 4 stops, so card frames at the same shutter time collect about 16 times the light. The draft runs card frames twice, at matched time and at matched signal.
- **Mirror.** `liveview.py` sets `viewfinder=0` before each sequence, so the mirror cycles every frame. The draft says so. Shooting from live view would hold it up.
- **Levin mask symmetry.** It has 180 degree rotational symmetry, so it cannot tell 812 mm from 1300 mm with focus at 1000 mm. The draft gives it the side of focus.
- **Zhou pair stereo cue.** The open-cell centroids of the pair sit 8.3 mm apart. Crop both PSFs about one centre. Centring each PSF on its own throws away a 5 px shift at 950 mm. Each pixel of drift between the pair reads as 4.8 mm of depth at 700 mm.
- **Code still in pitch mode.** `gates.py` prints PASS or FAIL against the pitch thresholds and measures transmission against a bare lens. Rewrite it to report each metric with its standard deviation against the card baselines, so the repository matches the report.

## Page budget

The brief allows six pages plus references. With team notes hidden, the abstract, introduction and method end about
4.1 pages in, so results, literature review, limitations and conclusion get about 1.9 pages. Cuts that keep the
argument, with rough savings:

| Cut | Saves |
| --- | --- |
| Stage 2 (end of 3.1 and the slot sentences in 3.2) | about 0.15 page |
| All-in-focus test (end of 3.5.1 and its Table 1 row) | about 0.08 page |
| Pair spectra diagnostic (second paragraph of 3.3 and its Table 1 row) | about 0.08 page |
| Hobbyist sentence in the introduction | about 0.03 page |

All three scope cuts together bring the method to about 3.7 pages before results. Plan four results figures at most and
use `figure*` spreads with shared axes where you can.

## Decisions still open (blue team notes in the PDF)

- How the backlight came off.
- How the carrier holds the pattern within 0.1 mm of the axis and how you check it.
- The Arduino model, the optocoupler part and whether an Arduino analogue input samples the photodiode.
- The point source: pinhole diameter and lamp.
- The depth target texture, the bokeh highlights and the flutter target drive. Do not use an LCD monitor as the target, since it emits polarised light.
- Whether to keep Stage 2.
- Whether to shoot from live view so the mirror stays up.
- Whether the Lab 3 code includes Levin's sparse-prior deconvolution.
- Whether to add a multiplexed refocus scan in dim light. The lectures teach multiplexing gain (Lec 2A, 3A) and a marker may ask why we scan one tile at a time.
- The AI-use statement in the acknowledgments.

Red numbers are placeholders for measurements. Uncomment `\shownotesfalse` in `main.tex` before you submit, then
search the PDF for red text.

## Detail cut from the paper for the README

The brief says the repository carries what someone needs to rebuild the system. These belong in the README under
build steps and known pitfalls:

- Pin map (already in `code/README.md`) and the header and lead types.
- SPI clock: an Uno's hardware SPI runs at 8 MHz, under the 15 MHz ST7735R write limit, so a full frame takes about 50 ms to write. The sketch caps faster boards at 15 MHz. The serial transfer takes 8 ms for the open disc and under 15 ms for every named pattern at 500 kbaud, and it overlaps the write.
- The panel refreshes at 59.8 Hz from its own memory with no tearing-effect line, so a refresh during a write shows part of each pattern.
- Slot steps with photos and the kerf measurement on each card.
- E3 jack: tip to shutter, ring to focus, sleeve to ground, about 3.3 V pull-up. Drive it through an optocoupler.
- The 60D has no PC sync socket. The hot shoe is the sole wired sync output.
- Mains lighting flickers at 100 Hz in Australia. Use lamps on a direct-current supply.

The remaining pitfalls sit in the comments of `sections/05_limitations.tex`.

## Roles

The professor asked that no member appear to do mechanical work alone. One split that gives each member a full
experiment from capture to analysis:

- **Ethan:** measurement model, depth from the coded pair.
- **Emma:** panel characterisation against card masks, custom bokeh.
- **Jayden:** flutter shutter timing, the E3 and photodiode interfaces, deblurring.
- **Has:** PSF calibration and the width fit, post-capture refocus.

Everyone builds hardware, captures data and writes. If the unit wants a contribution statement, put one line in the
author footnote in `main.tex`.

## Overleaf

1. Upload `main.tex`, `preamble.sty`, `references.bib`, `sections/` and `images/` into the report project. Let `preamble.sty` overwrite the pitch copy, which cannot load under IEEEtran.
2. Check that the Overleaf menu lists `main.tex` as the main document.
3. Overleaf ships IEEEtran V1.8b, the version the ICCP 2026 template uses, so the project needs no class file.
4. Regenerate the two method figures with `python -m aperture.analysis.report_figures`, run from `code/`, after you change `code/aperture/config.py`.
