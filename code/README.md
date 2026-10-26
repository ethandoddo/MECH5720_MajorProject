# Dynamic aperture capture

Everything runs on one Ubuntu laptop. `server.py` streams each aperture pattern to an
Arduino or ESP32 board that drives the LCD in the optical path and fires the Canon EOS
60D through gphoto2 over USB. `camview_capture.py` drives the server from a window, the same window
as the Lab 3 capture tool with the Pi camera parts replaced by the DSLR and the panel.
Its Experiments window runs the capture set for each application: depth, refocus, bokeh
and the flutter shutter. `capture_series.py` does the same from the command line for
scripted runs. A sequence of patterns and frames runs inside the server in its own
thread, so the shutter fires a fixed settle time after each pattern lands. The clients
poll for progress. For the flutter shutter the board plays a code on the panel from its
own clock during one photo on M, so the panel is the shutter.

The EOS 60D streams live view over USB to the camera view in the window. One process owns
the USB link, so the stream pauses around each capture and comes back afterwards. With
live view off the window shows the last frame taken. Live view is the biggest drain on the
camera battery. It turns itself off when no window has taken a frame for 30 s and after
10 min in one go (`LIVEVIEW_IDLE_S` and `LIVEVIEW_MAX_S` in `config.py`). Closing the
window turns it off too. The server terminal says why it stopped.

## Files

| File | Purpose |
| --- | --- |
| [arduino/aperture_panel/aperture_panel.ino](arduino/aperture_panel/aperture_panel.ino) | The sketch. Takes each pattern over serial as run lengths and writes it to the panel as it arrives. Plays a flutter shutter code from its own clock |
| [camview_capture.py](camview_capture.py) | The main driver. Camera view, panel view, controls for patterns, camera settings, single frames and sequences, plus the Experiments window |
| [capture_series.py](capture_series.py) | Command line client for scripted runs |
| [server.py](server.py) | Flask server that owns the panel and the camera |
| [config.py](config.py) | Panel geometry, serial port and baud, lens pupil, the coded pair, named sequences and the flutter shutter settings |
| [patterns.py](patterns.py) | Builds 128 x 160 pattern images: open disc, white, black, any `masks/*.txt` grid, `scan0`..`scan8`, `scan5_0`..`scan5_24` for a 5 x 5 scan, any PNG or GIF frame. `python patterns.py` writes the named ones to `out/patterns/` |
| [flutter.py](flutter.py) | Designs the flutter shutter code and checks its timing. `python flutter.py` prints the default code and its score |
| [flutter_deblur.py](flutter_deblur.py) | Deblurs a flutter run's coded frame with the code from its trace and scores it against the reference frames |
| [flutter_score.py](flutter_score.py) | Checks a flutter run and scores its coded, box and impulse photos against the reference, with the close-up pictures. Uses `flutter_95_template.npy` to find the "95" |
| [display.py](display.py) | `arduino` for the panel, `window` for a window on the laptop, `st7735` for the panel on a Raspberry Pi, `null` for tests. `python display.py` prints what each pattern costs on the serial link |
| [camera.py](camera.py) | `gphoto` for the 60D, stills and the shutter speed check for the flutter frames. `dummy` writes the shown pattern so everything runs with no camera |
| [liveview.py](liveview.py) | Live view stream from `gphoto2 --capture-movie`. The dummy version streams the panel image |
| [preview.py](preview.py) | Pulls the embedded JPEG out of a CR2 for the camera view |
| [show.py](show.py) | Show one pattern with no server |
| `masks/` | Cell grids in the Lab 3 format. `zhou_a.txt` and `zhou_b.txt` are the 13 x 13 coded pair from figure 4 of Zhou, Lin and Nayar, ICCV 2009, sampled from the paper's own figure raster. `levin.txt` and `nayar.txt` are the Lab 3 masks |

## Step by step

The sections after this one explain each part. This one is the order to do things in.

### First run

1. Set the laptop up once. Log out and in again afterwards for the serial port group.
   ```
   sudo apt install -y gphoto2 zenity
   pip install -r requirements.txt
   sudo usermod -aG dialout $USER
   curl -fL -o ~/.local/bin/dnglab https://github.com/dnglab/dnglab/releases/download/v0.8.0/dnglab_linux_x64
   chmod +x ~/.local/bin/dnglab
   ```
2. Wire the panel to the board as the table under Arduino or ESP32 setup shows, plug the
   board in and upload the sketch. Do this again after every pull that changes the sketch.
   ```
   arduino-cli lib install "Adafruit GFX Library" "Adafruit ST7735 and ST7789 Library"
   arduino-cli core install arduino:avr
   arduino-cli compile --fqbn arduino:avr:uno arduino/aperture_panel
   arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino/aperture_panel
   ```
3. Set the camera up: mode dial on M, lens on MF, iris at f/1.8 so the panel is the stop,
   quality RAW+JPEG, auto power off and long exposure noise reduction off in the menu.
   Plug it in and check the laptop sees it.
   ```
   gphoto2 --auto-detect
   gphoto2 --capture-image-and-download
   ```
4. Start the server in one terminal and leave it running.
   ```
   python server.py --display arduino --camera gphoto
   ```
   It prints `display=arduino camera=gphoto pupil 27.8 mm = 126.8 px` when both are up.
   `--display window --camera dummy` runs the whole thing with nothing plugged in.
5. Check the panel from a second terminal. `white` should fill the glass edge to edge and
   `scan0` should light one corner tile. Note which corner.
   ```
   python show.py white --backend arduino
   python show.py scan0 --backend arduino
   ```
   Look through the lens at `white` and `black`. If the glass passes light where the image
   is black, set `PANEL_INVERT = True` in `config.py` and restart the server.
6. Start the window in the second terminal.
   ```
   python camview_capture.py --outdir captures
   ```
   Set the ISO and shutter speed under Camera in Controls. Tick Live view to frame the
   scene and untick it before a run, since it drains the battery. If the panes sit on top
   of each other, close the window, delete `imgui.ini` and start it again.

### Running an experiment

1. Place the target and type its distance into Target distance mm in the Experiments
   window. Set Repeats to 5 for the error bars.
2. Pick the tab and press the button for the capture. The progress bar at the top of the
   window counts the steps.
3. When the window says Waiting for you, do what the prompt says and press Continue. The
   flutter Run puts each prompt in a pop-up instead. Stop ends the run after the current
   step.
4. The frames land in `captures/<experiment>/` with the manifest beside them once the run
   ends. The Activity line in Controls says when.

The buttons per tab, in the order to run them:

- **Depth**, point source at each distance: PSF set. The textured target at each distance
  comes next: Pair, Singles, Card pair.
- **Refocus**, target at each distance: Scan 3x3, Scan 5x5, f/5.6 frame, Lens focus.
- **Bokeh**, highlights in the scene: Browse to the shape, Capture, Card shape.
- **Flutter**: the next list.

### The flutter shutter

1. Light the scene with lamps on a direct current supply. Mains lighting flickers at 100 Hz.
2. On the Flutter tab leave the designed code, set Chop ms to 100, pick Invert and press
   LCD only flutter shutter. The panel flutters on its own with no camera. Watch it: it
   should go fully clear and fully dark in the code's pattern. If it never goes fully
   clear, Invert does not work on this panel and Frame write is the method.
3. Set Blur px to 100. The line under it gives the target speed in px/s for the chop.
   Turn that into mm/s or rpm with the table under Target speed below and set the
   target's motor to it.
4. Set the shutter speed on M to at least Lead + code, 5 s for the defaults. The tab says
   in red when it is too short. Tick all six captures, or reference, impulse, coded and box
   for the light-level runs of step 7. Set Repeats to 1 or 2 and press Run.
   Press Run again for more. Pop-ups say what to set up and wait for Continue: the target
   still for the reference, then moving for the impulse, coded, box and leakage frames,
   which run straight through, then lens cap on for the darks and off at the end. The dial
   stays on M.
5. Repeat step 4 with Frame write at 100 ms and at 200 ms.
6. Repeat step 4 with Invert at 25, 50 and 200 ms, resetting the target speed each time.
7. Repeat step 4 at 100 ms at the other light levels. Set the light with the aperture, not
   the lamps: f/5.6, f/11 and f/22 at 5 s and ISO 100. See Light levels and scoring below.

The same from the command line, one coded frame at a time at the shutter speed set on M:

```
python capture_series.py --code designed --chop 100 --no-capture --label switch --outdir captures/flutter
python capture_series.py --code designed --chop 100 --label coded --outdir captures/flutter
python capture_series.py --go        # from another terminal when a job is waiting
```

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
pixels measure. LibRaw 0.22 gets these DNGs wrong. It reads a black level of 2088 to 2151,
which darkens a frame by about 5 percent and clips the faint edge of a PSF. `gates.py` and
rawpy read the CR2 for that reason and pick it over a DNG of the same frame.
`SAVE_DNG = False` in `config.py` turns the DNGs off. Without dnglab the CR2s still save
and the window says why the DNGs are missing.

ModemManager probes a new serial device for a few seconds after it appears, so the first
connection after plugging in the Arduino can fail. Nothing here needs it. Remove it with
`sudo apt remove modemmanager`.

Camera: put the 60D's mode dial on M, switch the lens to MF, set the quality to RAW+JPEG
on the body, turn off auto power off and long exposure noise reduction in the menu and
plug the USB cable into the laptop. RAW+JPEG gives a CR2 for processing and a JPEG the
camera view shows at once. The flutter Run takes every frame on M too, at a shutter speed
of at least Lead + code. Check the camera:

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
the bytes arrive, so it needs no frame buffer and fits in an Uno's 2 KB of RAM. The
breakout has its own regulator and level shifter. It takes 5 V from an Uno or 3.3 V from
an ESP32 on both Vin and the logic pins.

SCK and MOSI go to the board's hardware SPI pins, which the library picks on its own.
CS, D/C and RST are defines at the top of the sketch, one block per board family. Any
output pin will do. The sketch's defaults, with ESP32 pins as GPIO numbers:

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

The sketch prints `aperture 4 128 160` at 500000 baud on reset, where 4 is the protocol
version. The backend refuses a board that reports another version, so upload the sketch
again after pulling changes to it. Version 4 dropped the photodiode, which means a board
still on version 3 will not connect until it gets the new sketch. The backend finds the
board on its own, an Uno as `/dev/ttyACM0` (`/dev/ttyUSB0` for a clone with a CH340 chip)
and an ESP32 as `/dev/ttyUSB0` or `/dev/ttyACM0`. Set `ARDUINO_PORT` when the laptop has more than one serial device.
`ARDUINO_BAUD` must match `BAUD` in the sketch. A board with native USB ignores the
baud. An ESP32 may or may not reset when the port opens, so the backend waits for the
banner and then asks for it.

The laptop sends each frame a few bytes at a time. One byte can be a run of 128 pixels,
which the panel takes hundreds of microseconds to draw while the next bytes arrive every
20 µs. A single burst would overflow the Uno's 64 byte receive buffer. The sketch sends a
`c` for every 16 bytes it takes out of the buffer. The laptop keeps at most
`ARDUINO_WINDOW`, 48 bytes, in flight. `ARDUINO_CREDIT` must match `CREDIT_BYTES` in the sketch.

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

The window has four panes. Camera View streams the DSLR's live view. With live view off
it shows the last frame taken. Aperture Panel shows the image on the LCD, pixel for pixel.
Controls has the pattern list and pupil diameter, the ISO, shutter speed and aperture read
from the camera, a label and output folder, the Preview shot and Capture and save buttons
and the sequence runner with a progress bar. Experiments has a tab for each application,
described under Experiments below. Frames from a sequence download to the output folder
when the server reports it finished.

The window saves where you left the panes in `imgui.ini` and puts them back on the next
start. A file saved by an older version can stack the panes on top of each other. Close
the window, delete `imgui.ini` and start it again to get the default layout.

Image files come in through Browse... and Add files..., a file dialog that needs zenity,
which Ubuntu ships. Browse... fills the Image field. Show image puts a PNG on the panel.
A GIF shows its first frame. Image size and Fit circle resize it there and then. Play GIF loops a GIF on the panel at its own frame delays
times the GIF speed slider, 0.25x to 4x. Moving the slider while it plays changes the
speed without restarting it. Stop, another pattern, a capture or a sequence stops it, so
the panel holds still for every exposure. The panel can't change faster than one frame per
draw, about 95 ms on an Uno, so delays shorter than that stretch to it.

The `images` sequence runs a list built with Add files... (several at once) and Add
pattern, which adds the pattern selected above, such as `open` as a control frame. Up,
Down, Remove and Clear edit it. The line under it counts the photos. A GIF takes one
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
python capture_series.py --code designed --chop 100 --label flutter      # one coded frame on M
python capture_series.py --code 1011001 --chop 50 --no-capture           # play it and record the trace
python capture_series.py --go                                            # a paused job carries on
python capture_series.py --abort                                         # stop the running job
```

Frames land in `<outdir>/<label>_<index>_<pattern>.CR2`, `.JPG` and `.dng` with `<label>_manifest.json`
beside them. The manifest records when each pattern went up, when the shutter fired, the
pupil diameter and pixel pitch in force and the panel image for every frame. The CR2
files open in rawpy the same way the Lab 3 DNGs did. The DNGs open in the Lab 3 MATLAB
scripts. The server makes the DNGs after the last frame of a sequence, about a second
each, so they never delay a shutter. An image file is named by its stem, `star` for
`~/Pictures/star.png`. Frame 3 of `walk.gif` is `walk_f03`. The manifest keeps the full
path in `pattern` (`walk.gif#3` for a GIF frame) and the file name part in `tag`.

## Sequences

`config.SEQUENCES` names the ones the pitch asks for.

- `pair`: open, coded A, coded B, open. The two open frames are the control pair for
  Gate 3 and the coded pair feeds depth estimation.
- `scan`: open, then the nine sub-aperture tiles, then open. Post-capture refocus.
- `transmission`: white, black, open. The stops lost to the panel for Gate 1.

A sequence entry can be a step object instead of a name. `{"pattern": "white", "tag":
"card_open", "prompt": "Fit the open card"}` pauses the job with the prompt on show until
Continue in the window or `--go` on the command line, then shows the pattern and fires.
`"camera": {"shutterspeed": "1/250"}` sets the camera first, `"diameter_mm": 8.9` sizes
that one frame and `"capture": false` shows the pattern and takes no frame. `{"prompt":
"Take the lens cap off"}` alone pauses and takes nothing. `{"code": "1011...", "chop_ms":
100}` is a flutter shutter step, described below. Stop ends the job after its current
step. A job that stops or fails still writes its manifest with the frames it took. The
manifest keeps the full step list under `steps`.

Custom bokeh is any PNG the server can read, passed as a pattern name. In an image with
transparency, such as the sprites in `sprites/`, the transparent pixels are open like
clear glass. Every opaque pixel is shut, black and grey alike. The sprites are
transparent characters on black, so a bright point blurs into the character. In an image
with no transparency white is open. An image's longest side is the pupil diameter times
the image size, 100 percent by default. The Image size slider in the window and
`--image-scale` on the command line set it. 71 percent fits a whole square image inside
the round pupil. Above 100 the edges are cut. The size goes in the manifest as
`image_scale` and leaves the built-in patterns alone.

The Rotation slider in the window turns any pattern, in degrees anticlockwise about the
panel centre as the Aperture Panel view shows it. The -90 and +90 buttons beside it turn
it a quarter at a time and 0 puts it back. `--rotate` does the same on the command line.
The centre sits between pixels, so 90 degree steps are exact and other angles resample to
the nearest pixel. The angle goes in the manifest as `rotation_deg` and every frame's
`_panel.png` shows the turned pattern. Gate 1 fits the rotation of a mask itself, but
Gate 3 and the scan tile positions assume an unturned mask, so judge rotated sessions
with that in mind. Rotation turns `white` as well, which leaves black corners. Keep it at
0 for the flutter frames. Changing Pupil mm, Image size or Rotation in the window redraws
whatever is on the panel 0.4 s after the value stops changing. A GIF expands to one frame
per GIF frame, so `walk.gif` in a list is `walk.gif#0`, `walk.gif#1` and so on.
`walk.gif#3` on its own is one frame.

## Experiments

The Experiments window turns each application into a list of steps and runs them as one
sequence. Repeats runs the whole list that many times for the error bars. Target distance
goes into the label. Frames download to `<outdir>/<experiment>/`. Every button uses the
Settle, Pupil mm, Image size and Rotation set in Controls. A step that needs a hand, a
card swap or the lens cap, pauses the job and shows the prompt at the top of the window
with Continue and Stop beside it.

- **Depth.** PSF set is open, pattern A, pattern B, Levin and black for a point source. Pair
  is open, A, B, open for a textured target. Singles takes each coded pattern twice, so one
  pattern gets the pair's exposure. Card pair takes the same four frames through
  hand-fitted cards with the panel white, pausing before each card, the baseline for what
  the panel costs. A and B start as Zhou A and Zhou B. Type another mask name from
  `masks/` or pick a PNG or GIF with Browse A... and Browse B.... Image size in Controls
  sizes an image. The labels read `depth1000mm_pair`, so Gate 2 finds the distance. A pair
  other than the Zhou one adds its names, as in `depth1000mm_pair_star_heart`, so it never
  overwrites the Zhou files. Gates 1 and 3 need a mask file for each pattern, so they only
  judge mask names, not images.
- **Refocus.** Scan 3x3 and Scan 5x5 take open, every tile, black and open. The f/5.6
  frame is one open disc 8.9 mm wide, the depth of field the 3x3 refocus reaches with no
  scan, the one-frame baseline. Lens focus pauses for you to focus the lens on the target
  by hand and takes the in-focus reference for SSIM.
- **Bokeh.** Browse to a PNG or GIF of the shape. Capture takes open, the shape, open at
  the Image size and Rotation from Controls. Card shape takes the same through a laser-cut
  card.
- **Flutter.** Described in the next section.

## Flutter shutter

The flutter shutter of Raskar, Agrawal and Tumblin opens and closes the shutter in a
binary code during one exposure, so the blur of a moving target stays invertible. On this
rig the panel is the shutter. The camera takes one photo on M at its own shutter speed.
The panel is black when the shutter opens, the board plays the code on the panel from
its own clock, and the panel stays black until the shutter closes. The curtains move in
the dark, so every row of the sensor sees the same code and the 60D's 1/250 s curtain
travel does not matter.

The board switches the panel one of two ways. Invert sends the controller's one-byte
invert command, which flips every pixel in the time the liquid crystal takes, 15 to
35 ms by the datasheet. Frame write rewrites every pixel, 41 ms at the Uno's 8 MHz SPI
clock, so chops under about 130 ms slip. Invert is the better method. Frame write is the
fallback for a panel that Invert does not take fully clear. Run both and the difference
is what the faster switch buys. The sketch holds the whole run to a 16 bit millisecond
clock, so lead, code and tail together fit `FLUTTER_MAX_S`, 60 s.

`flutter.py` designs the code: a seeded random search over 32 chop codes with 16 open,
first and last open, for the highest minimum in the padded spectrum. Every machine
designs the same code, `10001101101001011000001111010101`, which the manifest records by
its text. A box of the same length scores 0 and that code 0.075. The Custom field takes
any code of up to 64 chops.

The Flutter tab builds the capture set. Chop ms sets the chop. Lead ms is how long the
panel stays black before the code, so that the shutter has opened by then. Its default
of 1 s is a guess at how long gphoto2 takes to fire. Check that the first real coded
frame has every chop. A small bright dot on the target streaks in the code's on and off
pattern. If the start of that pattern is missing, Lead is too short. If the end is
missing, the shutter speed is too short. Tail ms is how long the panel stays black after
the code, 200 ms by default. Blur px gives the target speed to set for that much blur
over the code.

Every frame is on M. The shutter opens during Lead, so the shutter speed has to be at
least Lead + code: 4.2 s for the default 1 s and 32 chops of 100 ms, which is 5 s on the
60D. The panel is black for the rest, which adds only leakage. The tab shows the shutter
speed and says in red when it is too short. Run then does not start. Tick the captures
to take:

| Capture | Panel | Camera | Target |
| --- | --- | --- | --- |
| reference | open for the code's length | the shutter speed under Photo | still |
| impulse | open | the Impulse shutter speed | moving |
| coded | plays the code | the shutter speed under Photo | moving |
| box | open for the code's length | the same | moving |
| leakage | black for the code's length | the same | moving |
| dark | black for the code's length | the same, lens cap on | any |

Run takes them in that order, Repeats times each. A pop-up says what to change at the rig
and what the frames are for, and waits for Continue, three times: before the reference,
before the moving frames and before the darks. The impulse, coded, box and leakage frames
then run straight through with their repeats, so the target never has to stop. The car
keeps moving between frames too, about 7.5 s for each 5 s frame, so their pop-up says how
far it travels. Start it near the edge of the frame it moves away from. With all six
ticked at 62.5 px/s the car travels about 1,600 px with Repeats 1 and 3,200 px with
Repeats 2. Box and
leakage keep the timing of the coded frame, so the three frames collect the same stray
light.

LCD only flutter shutter plays the code on the panel Repeats times with no camera. Use it
to watch the panel switch and to check Invert before anything else.

Capture takes a plain photo Repeats times with the panel white, no flicker and the dial
on M. Photo sets both Capture and Run. Camera as it is takes the camera's settings as they
are when you press the button, and Run reads them from the camera first. These settings
sends the ISO, shutter speed and aperture picked on the tab first. The camera keeps them
afterwards. Controls still shows the old values until Refresh settings. Run's impulse
frames take the Impulse shutter in place of the shutter speed under Photo. With These
settings they take its ISO and aperture too.

Name starts the file names of all three: `fast_target_100ms_invert_00_coded.CR2` from Run,
`fast_target_100ms_invert_00_switch.json` from LCD only flutter shutter and
`fast_target_00_photo.CR2` from Capture. Spaces and other symbols become `_`. Left empty,
the names start `flutter_`, `flutter_switch_` and `flutter_photo`. A name already in the
flutter folder gets `_2`, `_3` and so on after it, `fast_target_2_100ms_invert_...`, so a
download never replaces an earlier one.

Each coded, box, leakage, reference and dark frame lands with `<index>_<tag>_trace.json`
beside it, which downloads as `<label>_<index>_<tag>.json`. It holds the code, chop, lead
and tail. It also holds `start_ms` and `end_ms` for every switch including the final
black, in ms since the board's clock started. Those are when the board sent each switch.
Nothing records what the glass did, since the photodiode came out. `play_s` and `fired_s`
in the trace, with `shown_s` and `fired_s` in the manifest, are times on the laptop's
clock. `fired_s` minus `play_s` is how long after the board started its clock the laptop
launched gphoto2. It leaves out gphoto2's own start-up. `shutter_s` is the shutter speed
the camera read, in seconds.

The server reads the camera's shutter speed before the first of these frames and again
after each pop-up, impulse frame or setting it sends. It stops the run when the dial is on
B, where the 60D has no shutter speed, or when the shutter speed is shorter than Lead +
code. Check on the first run that Invert takes the glass all the way to white and back,
which you can watch during LCD only flutter shutter.

[flutter_deblur.py](flutter_deblur.py) deblurs the coded frame. It stretches the code from
the trace over a blur length along the rows and removes it row by row by regularised least
squares. It then aligns the result to the averaged reference frames and scores it by MSE,
PSNR and NCC. `--sweep` tries a range of blur lengths in both directions and keeps the
lowest MSE. Run it from the code folder with the run's prefix:

```
python flutter_deblur.py captures/flutter/Run1actual_100ms_invert --blur 100
python flutter_deblur.py captures/flutter/Run1actual_100ms_invert --sweep 100:5200:100
```

The results land in `out/flutter/<run>/`: `compare.png` holds the coded, deblurred and
reference frames one above the other, and `scores.csv` holds every blur length tried. The
alignment searches up to half the frame width, so check the shift column. A deblurred frame
that lands hundreds of pixels from where the coded frame did has matched the wrong part of
the scene, and its MSE does not count.

### Light levels and scoring

The flutter results compare the coded photo with the box and the impulse at several light
levels. The aperture sets the light, so the steps are exact: f/5.6, f/11 and f/22 at 5 s and
ISO 100, a factor of 4 apart. The lamps, focus, zoom and track stay where they are. Each run
ticks reference, impulse, coded and box, with the designed code, Chop 100, Lead 1000, Tail
200, Invert and an Impulse shutter of 1/10. One leakage and one dark photo per aperture are
enough. Drive the car left at about 100 px/s, which gives about 320 px of blur over the code,
and start it with the "95" near the right edge of the frame. The impulse, coded and box
photos take about 18 s, so the car travels about 1,800 px and stays in view.

[flutter_score.py](flutter_score.py) checks and scores a run. Run it from the code folder
with the run's Name:

```
python flutter_score.py Run2_f22
python flutter_score.py Run2_f22 --pictures-only     # redraw the pictures from the saved scores
```

It checks the manifest and traces, reads each photo's raw level, clipping and EXIF, sweeps
the coded and box photos over blur lengths from 200 to 1200 px with the car moving left, and
scores every photo against the run's reference: MSE, NCC and detail, the correlation of the
8 to 32 px features that make up the strokes of the "95". Each photo is scored with the f/11
settings, lam 0.05 and 40 Richardson-Lucy iterations, and again at its best setting. The
scores and pictures land in `out/flutter/<run>/`. It uses `flutter_deblur.py` for loading,
deblurring and the first alignment, and `flutter_95_template.npy`, the "95" cut from a
reference, to centre the close-ups.

The best matched photo of each kind at each aperture is kept in
`captures/flutter_5s_ISO100_f11_outside_lens/`, `captures/flutter_5s_ISO100_f22_outside_lens/` and
`captures/flutter_5s_ISO100_f5.6_outside_lens/`. Each holds `data.md` with the settings, the results and
why those photos, `data.csv`, `results.json`, the pictures and a `score.py` that makes them
again from the photos. The .cr2 and .dng photos stay on the lab laptop, since `captures/` is
not in git.

Three things decide whether two photos compare fairly:

- **Blur.** The car's speed wanders by 20 to 35% over the 8 s of moving photos, so the coded
  and box photos of one run seldom get the same blur. A box with less blur has the easier job.
- **Distance from the reference spot.** The car's reflections and the lamp light on it change
  with where it is, and the score fits one brightness and contrast to the whole picture. A
  photo taken 1,000 px from where the car stood for the reference scores several times worse
  however sharp it is. Stand the car for the reference where it will be during the coded photo.
- **Zoom.** The zoom moved from 51 mm to 55 mm during the f/22 runs. At 55 mm the car is 8%
  bigger, and so is its blur in px.

### Target speed

The window gives the target speed in pixels per second on the sensor. A motor wants
millimetres per second or rpm. Converting needs the size of one pixel on the target.

A 60D pixel is 4.3 µm. Divide that by the magnification to get its size on the target.
With the bare 50 mm lens and the target 1000 mm from the sensor one pixel covers 82 µm.
With the extension tube fitted and the target 270 mm from the sensor, the thin lens
formula for a 50 mm lens puts the magnification at about 0.33. One pixel then covers
about 13 µm. The whole frame covers only about 69 by 46 mm of the scene.

That 13 µm can be 8 percent out either way, since a real lens strays from the thin lens
formula. Measure it. Photograph a ruler where the target will be and count the pixels in
1 mm. The speed in mm/s is the window's px/s divided by that count.

For a 100 px blur over the designed 32 chop code with the target at 270 mm:

| Chop | Code lasts | Speed | rpm, 5 mm shaft | rpm, 10 mm spool | rpm, 20 mm wheel |
| --- | --- | --- | --- | --- | --- |
| 25 ms | 0.8 s | 1.65 mm/s | 6.3 | 3.2 | 1.6 |
| 50 ms | 1.6 s | 0.83 mm/s | 3.2 | 1.6 | 0.8 |
| 100 ms | 3.2 s | 0.41 mm/s | 1.6 | 0.8 | 0.4 |
| 200 ms | 6.4 s | 0.21 mm/s | 0.8 | 0.4 | 0.2 |

For any other diameter, rpm = mm/s × 60 ÷ (π × diameter in mm). Measure a spool with the
string wound on, since the string adds to the diameter. Halving the chop doubles the speed.
Doubling Blur px doubles it too.

These speeds are far too slow for a toy car. Its own motor drives it hundreds of times
faster than this. At 270 mm it may not even fit in the frame. A stepper motor such as the
28BYJ-48 winding string onto a spool pulls at these speeds and at the same speed every
run. Give it its own Arduino, because the panel's board is busy for the whole code.

Speeds that differ from frame to frame are fine as long as each frame holds a steady
speed. Measure each frame's blur from the frame itself. A small bright dot on the target
leaves a streak that shows it.

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

The cell then takes its own response time to settle, which sets the shortest useful chop.
The datasheet says 15 to 35 ms. The comment on `FLUTTER_CHOP_MS` in `config.py` says 30
to 70 ms. The repository has no measurement of this panel to settle which is right.

The flutter shutter needs no shutter timing from the laptop, since the panel is the
shutter. Lead covers the delay before the shutter opens and the shutter speed covers the
code. The 60D's remote jack is the 2.5 mm E3 type, which an Arduino pin can drive through
an optocoupler if a run ever needs the shutter to open on the board's clock too. That
would take the guesswork out of Lead.
