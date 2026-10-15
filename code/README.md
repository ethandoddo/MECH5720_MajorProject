# Dynamic aperture capture

Everything runs on one Ubuntu laptop. `server.py` streams each aperture pattern to an
Arduino or ESP32 board that drives the LCD in the optical path and fires the Canon EOS
60D through gphoto2 over USB. `camview_capture.py` drives the server from a window, the same window
as the Lab 3 capture tool with the Pi camera parts replaced by the DSLR and the panel.
`capture_series.py` does the same from the command line for scripted runs. A sequence of
patterns and frames runs inside the server in its own thread, so the shutter fires a
fixed settle time after each pattern lands. The clients poll for progress.

The EOS 60D has live view over USB, so the camera view in the window streams what the
camera sees. One process owns the USB link, so the stream pauses around each capture and
comes back afterwards. With live view off the window shows the last frame taken. Live view
is the biggest drain on the camera battery, so it turns itself off when no window has taken
a frame for 30 s and after 10 min in one go (`LIVEVIEW_IDLE_S` and `LIVEVIEW_MAX_S` in
`config.py`); closing the window turns it off too, and the server terminal says why it
stopped. The window shows the last frame taken until the box is ticked again.

## Files

| File | Purpose |
| --- | --- |
| [arduino/aperture_panel/aperture_panel.ino](arduino/aperture_panel/aperture_panel.ino) | The sketch. Takes each pattern over serial as run lengths and writes it to the panel as it arrives |
| [camview_capture.py](camview_capture.py) | The main driver. Camera view, panel view and controls for patterns, camera settings, single frames and sequences |
| [capture_series.py](capture_series.py) | Command line client for scripted runs |
| [server.py](server.py) | Flask server that owns the panel and the camera |
| [config.py](config.py) | Panel geometry, serial port and baud, lens pupil, the coded pair, named sequences |
| [patterns.py](patterns.py) | Builds 128 x 160 pattern images: open disc, white, black, any `masks/*.txt` grid, `scan0`..`scan8`, any PNG or GIF frame. `python patterns.py` writes them all to `out/patterns/` |
| [display.py](display.py) | `arduino` for the panel, `window` for a window on the laptop, `st7735` for the panel on a Raspberry Pi, `null` for tests. `python display.py` prints what each pattern costs on the serial link |
| [camera.py](camera.py) | `gphoto` for the 60D. `dummy` writes the shown pattern so everything runs with no camera |
| [liveview.py](liveview.py) | Live view stream from `gphoto2 --capture-movie`. The dummy version streams the panel image |
| [preview.py](preview.py) | Pulls the embedded JPEG out of a CR2 for the camera view |
| [show.py](show.py) | Show one pattern with no server |
| `masks/` | Cell grids in the Lab 3 format. `zhou_a.txt` and `zhou_b.txt` are the 13 x 13 coded pair from figure 4 of Zhou, Lin and Nayar, ICCV 2009, sampled from the paper's own figure raster. `levin.txt` and `nayar.txt` are the Lab 3 masks |

## Laptop setup

Ubuntu. gphoto2 comes from apt and the Python side from pip. The serial port needs the
`dialout` group, which takes effect at the next login.

```
sudo apt install -y gphoto2
pip install -r requirements.txt
sudo usermod -aG dialout $USER
curl -fL -o ~/.local/bin/dnglab https://github.com/dnglab/dnglab/releases/download/v0.8.0/dnglab_linux_x64
chmod +x ~/.local/bin/dnglab
```

dnglab turns each CR2 into a DNG for the Lab 3 MATLAB scripts, since Adobe's DNG Converter
has no Linux build. The conversion is lossless: the raw pixels match the CR2 and so does
the BlackLevel tag MATLAB reads, 2048 against the 2048 to 2049 the 60D's masked border
pixels measure. LibRaw 0.22 reads the same DNGs with a black level of 2088 to 2151, which
darkens a frame by about 5 percent and clips the faint edge of a PSF, so rawpy and
`gates.py` read the CR2 and pick it over a DNG of the same frame. `SAVE_DNG = False` in
`config.py` turns the DNGs off. Without dnglab the CR2s still save and the window says why
the DNGs are missing.

ModemManager probes a new serial device for a few seconds after it appears, so the first
connection after plugging in the Arduino can fail. Wait and retry, or remove it with
`sudo apt remove modemmanager`.

Camera: put the 60D's mode dial on M, switch the lens to MF, set the quality to RAW+JPEG
on the body, turn off auto power off in the menu and plug the USB cable into the laptop.
RAW+JPEG gives a CR2 for processing and a JPEG the camera view shows at once. Check it:

```
gphoto2 --auto-detect
gphoto2 --summary
gphoto2 --capture-image-and-download
gphoto2 --stdout --capture-movie | head -c 100000 > /dev/null    # live view stream
```

If gphoto2 says it cannot claim the USB device, the desktop has mounted the camera as a
drive. `server.py` kills the gvfs monitor at start. By hand it is
`pkill -f gvfs-gphoto2-volume-monitor`.

## Arduino or ESP32 setup

Any Arduino or ESP32 board runs the sketch. It writes each run of pixels to the panel as
the bytes arrive, so it needs no frame buffer and fits an Uno's 2 KB of RAM. The breakout
has its own regulator and level shifter, so it takes 5 V from an Uno or 3.3 V from an
ESP32 on both Vin and the logic pins.

SCK and MOSI go to the board's hardware SPI pins, which the library picks on its own.
CS, D/C and RST are defines at the top of the sketch, one block per board family, and
any output pin will do. The sketch's defaults, with ESP32 pins as GPIO numbers:

| Panel pin | Uno | ESP32 | ESP32-C3 | ESP32-S2 | ESP32-S3 |
| --- | --- | --- | --- | --- | --- |
| Vin | 5V | 3V3 | 3V3 | 3V3 | 3V3 |
| GND | GND | GND | GND | GND | GND |
| SCK | 13 | 18 | 4 | 36 | 12 |
| MOSI | 11 | 23 | 6 | 35 | 11 |
| TFT_CS | 10 | 5 | 7 | 34 | 10 |
| D/C | 8 | 21 | 10 | 33 | 8 |
| RST | 9 | 22 | 3 | 38 | 9 |
| LITE | not connected | | | | |

The ESP32 column covers the D1 mini ESP32 and the DevKit boards. A Mega's hardware SPI
is on pins 50 to 52.

Install Adafruit GFX Library and the Adafruit ST7735 and ST7789 Library from the Library
Manager in the Arduino IDE and upload the sketch. An ESP32 needs the esp32 core from the
Boards Manager first, with `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
under additional boards manager URLs. A C3, S2 or S3 mini with no USB bridge chip needs
USB CDC On Boot set to Enabled in the Tools menu, so that `Serial` is the USB port. From
the command line:

```
arduino-cli lib install "Adafruit GFX Library" "Adafruit ST7735 and ST7789 Library"

arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:uno arduino/aperture_panel
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino/aperture_panel     # /dev/ttyUSB0 on a CH340 clone

URL=https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index --additional-urls $URL
arduino-cli core install esp32:esp32 --additional-urls $URL
arduino-cli compile --fqbn esp32:esp32:esp32 arduino/aperture_panel                                 # classic ESP32
arduino-cli compile --fqbn esp32:esp32:esp32c3 --board-options CDCOnBoot=cdc arduino/aperture_panel  # C3 mini
arduino-cli compile --fqbn esp32:esp32:esp32s3 --board-options CDCOnBoot=cdc arduino/aperture_panel  # S3 mini
arduino-cli upload -p /dev/ttyUSB0 --fqbn esp32:esp32:esp32 arduino/aperture_panel
```

The sketch prints `aperture 2 128 160` at 500000 baud on reset, where 2 is the protocol
version. The backend refuses a board that reports another version, so upload the sketch
again after pulling changes to it. `config.py` finds the board on its own, an Uno as
`/dev/ttyACM0` (`/dev/ttyUSB0` for a clone with a CH340 chip) and an ESP32 as
`/dev/ttyUSB0` or `/dev/ttyACM0`. Set `ARDUINO_PORT` when the laptop has more than one serial device.
`ARDUINO_BAUD` must match `BAUD` in the sketch. A board with native USB ignores the
baud. An ESP32 may or may not reset when the port opens, so the backend waits for the
banner and then asks for it.

A frame is not sent in one burst. One byte can be a run of 128 pixels, which the panel
takes hundreds of microseconds to draw while the next bytes arrive every 20, so a burst
overflows the Uno's 64 byte receive buffer. The sketch sends a `c` for every 16 bytes it
takes out of the buffer, and the laptop keeps at most `ARDUINO_WINDOW`, 48 bytes, in
flight. `ARDUINO_CREDIT` must match `CREDIT_BYTES` in the sketch.

Until the next login after `usermod`, the shell is not in `dialout` yet. Run the upload
and the server under the group in the meantime:
`sg dialout -c "python server.py --display arduino --camera gphoto"`.

On Ubuntu the brltty screen reader service claims CH340 bridges, the chip on most ESP32
minis, so the port vanishes a moment after it appears. `sudo apt remove brltty` fixes
that.

Two checks on the first run. `python show.py white --backend arduino` should fill the
panel edge to edge. A strip of noise two pixels wide along one edge means the panel wants
`INITR_GREENTAB` in the sketch. `python show.py scan0 --backend arduino` lights one corner
tile. Note which corner of the glass that is, since the refocus code takes each tile's
position from the pattern image.

The `st7735` backend keeps the original layout, the panel wired to a Raspberry Pi over
SPI on the pins in `config.py`. It needs `adafruit-circuitpython-rgb-display`.

## Run

Two terminals on the laptop:

```
python server.py --display arduino --camera gphoto
python server.py --display window --camera dummy     # development, no hardware
```

```
python camview_capture.py --outdir captures
```

`--host` on either client points at another machine that runs the server.

The window has three panes. Camera View streams the DSLR's live view. With live view off
it shows the last frame taken. Aperture Panel shows the image on the LCD, pixel for pixel.
Controls has the pattern list and pupil diameter, the ISO, shutter speed and aperture read
from the camera, a label and output folder, the Preview shot and Capture and save buttons
and the sequence runner with a progress bar. Frames from a sequence download to the output
folder when the server reports it finished.

Image files come in through Browse... and Add files..., a file dialog that needs zenity,
which Ubuntu ships. Browse... fills the Image field. Show image puts a PNG, or the first
frame of a GIF, on the panel. Image size and Fit circle resize it there and then. Play GIF loops a GIF on the panel at its own frame delays
times the GIF speed slider, 0.25x to 4x. Moving the slider while it plays changes the
speed without restarting it. Stop, another pattern, a capture or a sequence stops it, so
the panel holds still for every exposure. The panel can't change faster than one frame per
draw, about 95 ms on an Uno, so delays shorter than that stretch to it.

The `images` sequence runs a list built with Add files... (several at once) and Add
pattern, which adds the pattern selected above, such as `open` as a control frame. Up,
Down, Remove and Clear edit it, and the line under it counts the photos. A GIF takes one
photo per frame. The server opens the files by path, so they have to be on the machine
that runs it.

The command line does the same:

```
python capture_series.py --status
python capture_series.py --set iso=100 --set shutterspeed=1/30
python capture_series.py --pattern levin
python capture_series.py --sequence pair --label 700mm --outdir captures/gate3
python capture_series.py --sequence scan --label 1000mm --outdir captures/refocus
python capture_series.py --patterns open star.png walk.gif open --label bokeh
python capture_series.py --play walk.gif --speed 2
python capture_series.py --stop
```

Frames land in `<outdir>/<label>_<index>_<pattern>.CR2`, `.JPG` and `.dng` with `<label>_manifest.json`
beside them. The manifest records when each pattern went up, when the shutter fired, the
pupil diameter and pixel pitch in force and the panel image for every frame. The CR2
files open in rawpy the same way the Lab 3 DNGs did, and the DNGs open in the Lab 3
MATLAB scripts. The server makes the DNGs after the last frame of a sequence, about a
second each, so they never delay a shutter. An image file is named by its
stem, `star` for `~/Pictures/star.png`, and frame 3 of `walk.gif` is `walk_f03`. The
manifest keeps the full path in `pattern`, with `walk.gif#3` for a GIF frame, and the
file name part in `tag`.

## Sequences

`config.SEQUENCES` names the ones the pitch asks for.

- `pair`: open, coded A, coded B, open. The two open frames are the control pair for
  Gate 3 and the coded pair feeds depth estimation.
- `scan`: open, then the nine sub-aperture tiles, then open. Post-capture refocus.
- `transmission`: white, black, open. The stops lost to the panel for Gate 1.

Custom bokeh is any PNG the server can read, passed as a pattern name. In an image with
transparency, such as the sprites in `sprites/`, the transparent pixels are open, like clear
glass, and every opaque pixel is shut, black and grey alike. The sprites are transparent
characters on black, so a bright point blurs into the character.
In an image with no transparency white is open. An image's longest side is the pupil
diameter times the image size, 100 percent by default. The Image size slider in the window
and `--image-scale` on the command line set it: 71 percent fits a whole square image inside
the round pupil, and above 100 the edges are cut. The size goes in the manifest as
`image_scale` and leaves the built-in patterns alone.

Any pattern turns with the Rotation slider in the window, -90, 0 and +90 buttons beside it,
or `--rotate` on the command line, in degrees anticlockwise as the Aperture Panel view shows
it, about the panel centre. The centre sits between pixels, so 90 degree steps are exact and
other angles resample to the nearest pixel. The angle goes in the manifest as
`rotation_deg` and every frame's `_panel.png` shows the turned pattern. Gate 1 fits the
rotation of a mask itself, but Gate 3 and the scan tile positions assume an unturned mask,
so judge rotated sessions with that in mind. Changing Pupil mm, Image size or Rotation in
the window redraws whatever is on the panel 0.4 s after the value stops changing. A
GIF expands to one frame per GIF frame, so `walk.gif` in a list is `walk.gif#0`,
`walk.gif#1` and so on, and `walk.gif#3` on its own is one frame.

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

The manifest's `shown_s` is when the sketch's acknowledgement arrived, about a
millisecond after its SPI write to the panel finished. The sketch writes each run as it
arrives, so the serial transfer and the SPI write overlap and the write sets the frame
time. Measured on a CH340 Uno: 95 ms for the open disc, white, black and the scan tiles,
105 ms for the Zhou pair, 130 ms for the Lab 3 masks, 0.8 s for random noise and 1.5 s
for a one pixel checkerboard, the worst case. `python display.py` prints the serial cost
of every pattern: 8 ms for the open disc and under 15 ms for every named pattern at
500 kbaud.
The cell then takes its own response time to settle. Measure that with a photodiode on
the panel while `show.py` toggles `white` and `black`, or with the `fill()` call on the
arduino backend, which sends one command instead of a frame. That number, with the 60D's
shutter lag, decides whether a flutter shutter code fits inside one exposure. The 60D's
remote jack is the 2.5 mm E3 type, which an Arduino pin can drive through an optocoupler
when the flutter shutter needs tighter timing than USB gives.
