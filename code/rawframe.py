"""Load a captured frame as a green-channel float image.

CR2 and DNG go through rawpy: the mosaic comes off the sensor above black in white-level
units, the green sites are demosaiced bilinearly as in Lab 3, and the frame's ISO and
exposure time come out of its TIFF tags so two frames can be compared in stops. PNG and
JPEG frames, from the dummy camera or a JPEG-only capture, load as grey in [0, 1].
"""
import struct
from collections import namedtuple
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import convolve

Frame = namedtuple("Frame", "green sat iso exposure path")

RAW_EXT = {".cr2", ".dng", ".nef", ".arw"}


def _ifd(buf, off, e):
    n, = struct.unpack(e + "H", buf[off:off + 2])
    for i in range(n):
        p = off + 2 + i * 12
        tag, typ, cnt = struct.unpack(e + "HHI", buf[p:p + 8])
        yield tag, typ, cnt, p + 8


def _value(buf, e, typ, cnt, p):
    if typ == 3:
        return struct.unpack(e + "H", buf[p:p + 2])[0]
    if typ == 4:
        return struct.unpack(e + "I", buf[p:p + 4])[0]
    if typ == 5:
        off = struct.unpack(e + "I", buf[p:p + 4])[0]
        num, den = struct.unpack(e + "II", buf[off:off + 8])
        return num / den if den else None
    return None


def exif(path):
    """{"iso": int, "exposure": seconds} from a TIFF-based raw file; missing tags come back None"""
    buf = Path(path).read_bytes()
    if buf[:2] not in (b"II", b"MM"):
        return {"iso": None, "exposure": None}
    e = "<" if buf[:2] == b"II" else ">"
    root, = struct.unpack(e + "I", buf[4:8])
    offs = [root]
    for tag, typ, cnt, p in _ifd(buf, root, e):
        if tag == 0x8769:
            offs.append(struct.unpack(e + "I", buf[p:p + 4])[0])
    out = {"iso": None, "exposure": None}
    for off in offs:
        for tag, typ, cnt, p in _ifd(buf, off, e):
            if tag == 0x8827 and out["iso"] is None:
                out["iso"] = _value(buf, e, typ, cnt, p)
            if tag == 0x829A and out["exposure"] is None:
                out["exposure"] = _value(buf, e, typ, cnt, p)
    return out


def debayer_green(mosaic, colours, desc):
    """bilinear green plane; measured green sites keep their value"""
    g_index = desc.index("G")
    m = (colours == g_index).astype(float)
    k = np.ones((3, 3))
    est = convolve(mosaic * m, k, mode="constant") / np.maximum(convolve(m, k, mode="constant"), 1e-9)
    known = m.astype(bool)
    est[known] = mosaic[known]
    return est


def read(path):
    path = Path(path)
    if path.suffix.lower() in RAW_EXT:
        import rawpy
        with rawpy.imread(str(path)) as raw:
            bayer = raw.raw_image_visible.astype(np.float64)
            colours = np.asarray(raw.raw_colors_visible)
            black = np.asarray(raw.black_level_per_channel, dtype=np.float64)
            white = float(raw.white_level)
            desc = raw.color_desc.decode()
        sat = float(np.mean(bayer >= white))
        mosaic = (bayer - black[colours]) / (white - black.mean())
        tags = exif(path)
        return Frame(debayer_green(mosaic, colours, desc), sat, tags["iso"], tags["exposure"], path)
    img = np.asarray(Image.open(path).convert("L")).astype(np.float64) / 255.0
    return Frame(img, float(np.mean(img >= 1.0)), None, None, path)


def relative_gain(a, b):
    """how much more light frame a collected than frame b from its ISO and exposure tags alone,
    as a linear factor; 1.0 when either frame lacks the tags"""
    if None in (a.iso, a.exposure, b.iso, b.exposure):
        return 1.0
    return (a.iso * a.exposure) / (b.iso * b.exposure)
