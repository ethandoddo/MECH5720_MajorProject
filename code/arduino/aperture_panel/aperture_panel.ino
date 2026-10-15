/*
  Aperture panel driver. Runs on an Arduino or an ESP32 wired to the Adafruit 358
  1.8 inch TFT (ST7735R, 128 x 160) that sits in the optical path. The laptop runs
  server.py with --display arduino, which streams every pattern to this sketch over
  USB serial.

  Wiring. SCK and MOSI go to the board's hardware SPI pins, which the library picks on
  its own. CS, D/C and RST are the defines below and any output pin will do. The
  breakout has its own regulator and level shifter, so it takes 5 V from an Uno or
  3.3 V from an ESP32 on Vin and on the logic pins. ESP32 numbers are GPIO numbers.

    panel    Uno    ESP32    ESP32-C3    ESP32-S2    ESP32-S3
    Vin      5V     3V3      3V3         3V3         3V3
    GND      GND    GND      GND         GND         GND
    SCK      13     18       4           36          12
    MOSI     11     23       6           35          11
    TFT_CS   10     5        7           34          10
    D/C      8      21       10          33          8
    RST      9      22       3           38          9
    LITE     not connected, the backlight is stripped

  Protocol. The laptop sends one command byte, then the sketch answers:

    '?'           banner "aperture 2 <width> <height>\n", also sent once at boot; 2 is the
                  protocol version, which the laptop checks
    'O' r         rotation r in 0..3, times 90 degrees, answers with the banner
    'F' v         fill the screen black (v = 0) or white (v = 1), answers 'K'
    'R' runs...   one frame as run lengths, answers 'K' when the SPI write is done.
                  Each row is a list of bytes that alternate black run, white run,
                  black run and so on, starting with black and summing to the width.
                  A row that starts white begins with a zero. Rows arrive top to
                  bottom. The sketch writes each run to the panel as it arrives, so
                  it needs no frame buffer and fits an Uno's 2 KB of RAM. It sends
                  'c' each time it has taken CREDIT_BYTES more bytes of the frame out
                  of its receive buffer.
    other bytes   ignored

  'E' answers a frame whose runs overrun a row or that stalls for BYTE_TIMEOUT_MS.
  After 'E' the sketch swallows bytes until the line goes quiet for QUIET_MS, so the
  next command starts clean.

  Flow control. At 500 kbaud a byte arrives every 20 us, but one byte can be a run of
  128 pixels, which takes the SPI write hundreds of us. Sent in one burst, a frame
  outruns the panel and overflows the Uno's 64 byte receive buffer, so the laptop
  keeps at most ARDUINO_WINDOW (48) bytes in flight and sends more as the 'c' credits
  come back. The buffer then never holds more than 48 bytes, whatever the pattern.
  The serial transfer still overlaps the SPI write, which sets the frame time: 95 ms
  measured for the open disc on a CH340 Uno, 130 ms for the Lab 3 masks, 1.5 s for a
  one pixel checkerboard, the worst case. A board with native USB ignores the baud rate.

  Libraries: Adafruit GFX Library and Adafruit ST7735 and ST7789 Library, which pulls
  in Adafruit BusIO. ESP32 boards need the esp32 core. A C3, S2 or S3 with no USB
  bridge chip needs USB CDC On Boot enabled so that Serial is the USB port.
*/

#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>

// ---- pins and SPI clock per board family. Change CS, D/C and RST to match the wiring.
#if defined(ESP32)
#if defined(CONFIG_IDF_TARGET_ESP32C3)
#define TFT_CS 7     // C3 hardware SPI: SCK 4, MOSI 6
#define TFT_DC 10
#define TFT_RST 3
#elif defined(CONFIG_IDF_TARGET_ESP32S2)
#define TFT_CS 34    // S2 hardware SPI: SCK 36, MOSI 35
#define TFT_DC 33
#define TFT_RST 38
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
#define TFT_CS 10    // S3 hardware SPI: SCK 12, MOSI 11
#define TFT_DC 8
#define TFT_RST 9
#else
#define TFT_CS 5     // classic ESP32 hardware SPI: SCK 18, MOSI 23
#define TFT_DC 21
#define TFT_RST 22
#endif
#define SPI_HZ 10000000  // 80 MHz / 8, under the 15 MHz ST7735R write limit
#else
#define TFT_CS 10    // Uno hardware SPI: SCK 13, MOSI 11
#define TFT_DC 8
#define TFT_RST 9
#define SPI_HZ 15000000  // the ST7735R write limit; an Uno caps itself at 8 MHz anyway
#endif

#define TFT_TAB INITR_BLACKTAB  // the 1.8 inch breakout; INITR_GREENTAB if the image sits 2 px off
#define BAUD 500000             // must match ARDUINO_BAUD in config.py
#define PROTOCOL 2              // must match ARDUINO_PROTOCOL in config.py
#define CREDIT_BYTES 16         // must match ARDUINO_CREDIT in config.py
#define BYTE_TIMEOUT_MS 500
#define QUIET_MS 100

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_RST);

// next byte from the laptop, or -1 after timeout_ms with nothing
static int readByte(unsigned long timeout_ms) {
  unsigned long t0 = millis();
  while (!Serial.available()) {
    if (millis() - t0 >= timeout_ms) return -1;
  }
  return Serial.read();
}

static void banner() {
  Serial.print(F("aperture "));
  Serial.print(PROTOCOL);
  Serial.print(' ');
  Serial.print(tft.width());
  Serial.print(' ');
  Serial.println(tft.height());
}

// throw away bytes until none arrive for quiet_ms
static void drainQuiet(unsigned long quiet_ms) {
  while (readByte(quiet_ms) >= 0) {
  }
}

// one frame of run lengths straight onto the panel; false on overrun or stall.
// Sends 'c' for every CREDIT_BYTES taken from the receive buffer, so the laptop
// knows how much room there is and the buffer never overflows.
static bool receiveFrame() {
  const uint16_t w = tft.width();
  const uint16_t h = tft.height();
  bool ok = true;
  uint8_t taken = 0;
  tft.startWrite();
  tft.setAddrWindow(0, 0, w, h);
  for (uint16_t row = 0; row < h && ok; row++) {
    uint16_t filled = 0;
    uint16_t colour = ST77XX_BLACK;
    while (filled < w) {
      int n = readByte(BYTE_TIMEOUT_MS);
      if (n < 0 || filled + n > w) {
        ok = false;
        break;
      }
      if (++taken == CREDIT_BYTES) {
        Serial.write('c');
        taken = 0;
      }
      tft.writeColor(colour, n);  // returns at once when n is 0
      filled += n;
      colour = (colour == ST77XX_BLACK) ? ST77XX_WHITE : ST77XX_BLACK;
    }
  }
  tft.endWrite();
  return ok;
}

void setup() {
#if defined(ESP32)
  Serial.setRxBufferSize(2048);  // the UART default is 256 bytes; room for a burst
#endif
  Serial.begin(BAUD);
  tft.initR(TFT_TAB);
  tft.setSPISpeed(SPI_HZ);
  tft.setRotation(0);
  tft.fillScreen(ST77XX_BLACK);
  banner();
}

void loop() {
  int c = readByte(1000);
  if (c < 0) return;
  switch (c) {
    case '?':
      banner();
      break;
    case 'O': {
      int r = readByte(BYTE_TIMEOUT_MS);
      if (r < 0 || r > 3) {
        Serial.write('E');
        break;
      }
      tft.setRotation(r);
      banner();
      break;
    }
    case 'F': {
      int v = readByte(BYTE_TIMEOUT_MS);
      if (v < 0) {
        Serial.write('E');
        break;
      }
      tft.fillScreen(v ? ST77XX_WHITE : ST77XX_BLACK);
      Serial.write('K');
      break;
    }
    case 'R':
      if (receiveFrame()) {
        Serial.write('K');
      } else {
        drainQuiet(QUIET_MS);
        Serial.write('E');
      }
      break;
    default:
      break;
  }
}
