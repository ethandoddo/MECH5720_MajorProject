# Dynamic aperture capture

The Pi drives the LCD in the optical path and fires the Canon EOS 60D over USB. The laptop
drives the Pi from `camview_capture.py`, the same window as the Lab 3 capture tool with
the Pi camera parts replaced by the DSLR and the panel. `capture_series.py` does the same
from the command line for scripted runs. A sequence of patterns and frames runs on the Pi
in its own thread, so no network delay sits between a pattern change and the shutter. The
laptop polls for progress.

The EOS 60D has live view over USB, so the camera view in the window streams what the
camera sees. One process owns the USB link, so the stream pauses around each capture and
comes back afterwards. With live view off the window shows the last frame taken.

## Files

| File | Purpose |
| --- | --- |
| [camview_capture.py](camview_capture.py) | The main driver. Camera view, panel view and controls for patterns, camera settings, single frames and sequences |
| [capture_series.py](capture_series.py) | Command line client for scripted runs |
| [server.py](server.py) | Flask server on the Pi |
| [config.py](config.py) | Panel geometry, SPI pins, lens pupil, the coded pair, named sequences |
| [patterns.py](patterns.py) | Builds 128 x 160 pattern images: open disc, white, black, any `masks/*.txt` grid, `scan0`..`scan8`, any PNG. `python patterns.py` writes them all to `out/patterns/` |
| [display.py](display.py) | `st7735` for the real panel, `window` for the 7 inch screen or a laptop, `null` for tests |
| [camera.py](camera.py) | `gphoto` for the 60D. `dummy` writes the shown pattern so everything runs with no camera |
| [liveview.py](liveview.py) | Live view stream from `gphoto2 --capture-movie`. The dummy version streams the panel image |
| [preview.py](preview.py) | Pulls the embedded JPEG out of a CR2 for the camera view |
| [show.py](show.py) | Show one pattern with no server |
| `masks/` | Cell grids in the Lab 3 format. `zhou_a.txt` and `zhou_b.txt` are the 13 x 13 coded pair from figure 4 of Zhou, Lin and Nayar, ICCV 2009, sampled from the paper's own figure raster. `levin.txt` and `nayar.txt` are the Lab 3 masks |

## Pi setup

```
sudo raspi-config           # Interface Options -> SPI -> enable
sudo apt install -y gphoto2 python3-pil.imagetk
pip install -r requirements-pi.txt --break-system-packages
```

Panel wiring, BCM numbering, the Adafruit Pi guide default that `config.py` uses:

| Panel pin | Pi pin |
| --- | --- |
| VIN | 3V3 |
| GND | GND |
| SCK | GPIO 11 (SCLK) |
| MOSI | GPIO 10 |
| TFT_CS | GPIO 8 (CE0) |
| D/C | GPIO 24 |
| RST | GPIO 25 |
| LITE | not connected |

Camera: put the 60D's mode dial on M, switch the lens to MF, set the quality to RAW+JPEG
on the body, turn off auto power off in the menu and plug the USB cable into the Pi.
RAW+JPEG gives a CR2 for processing and a JPEG the camera view shows at once. Check it:

```
gphoto2 --auto-detect
gphoto2 --summary
gphoto2 --capture-image-and-download
gphoto2 --stdout --capture-movie | head -c 100000 > /dev/null    # live view stream
```

If gphoto2 says it cannot claim the USB device the desktop has mounted the camera as a
drive. `server.py` kills the gvfs monitor at start. By hand it is
`pkill -f gvfs-gphoto2-volume-monitor`.

## Run

On the Pi:

```
python server.py --display st7735 --camera gphoto
python server.py --display window --camera dummy     # development on the 7 inch screen
```

On the laptop:

```
pip install -r requirements-laptop.txt
python camview_capture.py --host <pi> --outdir captures
```

The window has three panes. Camera View streams the DSLR's live view. With live view off
it shows the last frame taken. Aperture Panel shows the image on the LCD, pixel for pixel.
Controls has the pattern list and pupil diameter, the ISO, shutter speed and aperture read
from the camera, a label and output folder, the Preview shot and Capture and save buttons
and the sequence runner with a progress bar. Frames from a sequence download to the output
folder when the Pi reports it finished.

The command line does the same:

```
python capture_series.py --host <pi> --status
python capture_series.py --host <pi> --set iso=100 --set shutterspeed=1/30
python capture_series.py --host <pi> --pattern levin
python capture_series.py --host <pi> --sequence pair --label 700mm --outdir captures/gate3
python capture_series.py --host <pi> --sequence scan --label 1000mm --outdir captures/refocus
python capture_series.py --host <pi> --patterns open star.png open --label bokeh
```

Frames land in `<outdir>/<label>_<index>_<pattern>.CR2` with `<label>_manifest.json`
beside them. The manifest records when each pattern went up, when the shutter fired, the
pupil diameter and pixel pitch in force and the panel image for every frame. The CR2
files open in rawpy the same way the Lab 3 DNGs did.

## Sequences

`config.SEQUENCES` names the ones the pitch asks for.

- `pair`: open, coded A, coded B, open. The two open frames are the control pair for
  Gate 3 and the coded pair feeds depth estimation.
- `scan`: open, then the nine sub-aperture tiles, then open. Post-capture refocus.
- `transmission`: white, black, open. The stops lost to the panel for Gate 1.

Custom bokeh is any PNG on the Pi passed as a pattern name. White is open.

## Geometry

Patterns are drawn in millimetres on the pupil and converted to panel pixels with
`PANEL_PITCH_MM`, 0.219 mm for this panel. A 50 mm lens at f/1.8 has a 27.8 mm pupil,
which is 127 pixels, so the disc almost fills the 128 pixel width. Change `FOCAL_MM`
and `F_NUMBER` for another lens. The pupil field in the window overrides them for one run.

Once the backlight is stripped the cell may pass light where the image is black. Show
`white` and `black` through the lens, look and set `PANEL_INVERT` to match.

## Gates

[gates.py](gates.py) scores downloaded sessions against the pitch. Every frame is a
defocused point source in the image centre, the Lab 3 PSF protocol, captured with the
`pair` sequence.

```
python gates.py gate1 captures/gate1/700mm_manifest.json --bare captures/bare/bare_00_open.CR2
python gates.py gate2 captures/g2/700mm_manifest.json captures/g2/1000mm_manifest.json captures/g2/1300mm_manifest.json
python gates.py gate3 captures/gate3/700mm_manifest.json
python gates.py selftest
```

- **Gate 1** cuts the PSF out of each coded frame, fits the displayed pattern to it over
  pitch, rotation and mirror by normalised cross-correlation and quotes the best NCC. The
  open frame through the panel against a bare-lens frame of the same point source at the
  same ISO and shutter speed gives the stops lost.
- **Gate 2** takes the pair sessions at each distance. PSF width against distance goes
  through the Lab 3 defocus fit, which returns the focus distance. Each spectrum is
  searched for dips below a tenth of its local envelope inside the band. The pair passes
  when it shares under 30 percent of those dips. On ideal masks the Zhou pair shares 10
  percent and a disc against itself 100 percent. Sessions near focus have no dips in the
  band and are reported but not judged.
- **Gate 3** repeats the NCC on the two coded frames and phase-correlates the open frames
  before and after the pair. The shift must be under one pixel.

Results print as a table and land in `gates_<gate>.json` beside the first manifest. The
thresholds sit at the top of the file. `selftest` builds synthetic sessions with known
answers and runs all three gates on them.

## Timing

The manifest's `shown_s` is when the SPI transfer finished. The cell then takes its own
response time to settle. Measure that with a photodiode on the panel while `show.py`
toggles `white` and `black`. That number, with the 60D's shutter lag, decides whether a
flutter shutter code fits inside one exposure. The 60D's remote jack is the 2.5 mm E3
type, which a GPIO pin can drive through an optocoupler when the flutter shutter needs
tighter timing than USB gives.
