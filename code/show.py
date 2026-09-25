"""Show a pattern with no server, for checking patterns on the 7 inch screen or a laptop.

  python show.py levin
  python show.py open --diameter 20
  python show.py star.png --backend st7735
"""
import argparse
import time

import patterns
from display import open_display


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--backend", choices=["window", "st7735", "null"], default="window")
    ap.add_argument("--diameter", type=float, default=None, help="pupil diameter in mm")
    ap.add_argument("--seconds", type=float, default=0, help="close after this long; 0 keeps it open")
    ap.add_argument("--scale", type=int, default=None,
                    help="window backend only: screen pixels per panel pixel; 1 is about life size on the 7 inch screen")
    args = ap.parse_args()

    kw = {"scale": args.scale} if args.backend == "window" and args.scale else {}
    disp = open_display(args.backend, **kw)
    t = disp.show(patterns.make(args.name, args.diameter))
    print(f"{args.name} shown at {t:.3f}")
    try:
        if args.seconds:
            time.sleep(args.seconds)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        disp.close()


if __name__ == "__main__":
    main()
