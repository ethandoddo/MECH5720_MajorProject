"""A small JPEG of a captured frame, for the camera view in camview_capture.py.

CR2 and DNG files carry an embedded JPEG that rawpy pulls out in a fraction of the time
a full demosaic takes. Without rawpy, dcraw -e does the same job. JPEG and PNG frames are
resized as they are.
"""
import io
import shutil
import subprocess
from pathlib import Path

from PIL import Image

MAX_SIDE = 1200


def _raw_thumb(src):
    try:
        import rawpy
    except ImportError:
        if shutil.which("dcraw"):
            out = subprocess.run(["dcraw", "-e", "-c", str(src)], capture_output=True).stdout
            return Image.open(io.BytesIO(out))
        raise RuntimeError("no rawpy and no dcraw: pip install rawpy or apt install dcraw")
    with rawpy.imread(str(src)) as raw:
        try:
            th = raw.extract_thumb()
        except rawpy.LibRawNoThumbnailError:
            return Image.fromarray(raw.postprocess(half_size=True, use_camera_wb=True, no_auto_bright=True))
        if th.format == rawpy.ThumbFormat.JPEG:
            return Image.open(io.BytesIO(th.data))
        return Image.fromarray(th.data)


def make_preview(src, dest):
    src, dest = Path(src), Path(dest)
    if src.suffix.lower() in (".jpg", ".jpeg", ".png"):
        img = Image.open(src)
    else:
        img = _raw_thumb(src)
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    img.save(dest, "JPEG", quality=85)
    return dest
