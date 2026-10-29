"""Generate sprite animations as aperture frames for the 128 x 160 panel.

Link, Mario, the Knight (Realm of the Mad God) and a Terraria miner are written
as character grids. Each animation is written in two variants:

    binary   transparent sprite on an opaque black background
    grey     the same, with some sprite regions at mid-grey (128, 128, 128)

Every frame is a 128 x 160 portrait image (160 x 128 landscape for the Link
attack). The drawn area of all frames in an animation is cropped to one shared
box, scaled up as far as it fits and centred, so the animation does not jitter.
The scale is the largest that fits, using nearest-neighbour sampling. Set
INTEGER_SCALE to keep every sprite pixel the same size at the cost of margins.

Grid letters record the original colour regions. In the binary variant every
region is transparent. In the grey variant each animation maps its regions to
transparent ("k") or grey ("g"), the tonal negative of the earlier black and
grey masks. Other cells:

    .        background, black
    a-z      cut-out inside the silhouette (eye, button, visor slit), black;
             the letter is the original region, in lower case

Outputs per animation and variant, in <variant>/<character>/: one PNG per
frame, a looping GIF and a looping APNG. Run from any directory:

    python3 make_sprites.py
"""
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent
PORTRAIT = (128, 160)   # panel width, height
LANDSCAPE = (160, 128)
INTEGER_SCALE = False
FRAME_MS = 250
BLACK = (0, 0, 0, 255)
GREY = (128, 128, 128, 255)
CLEAR = (0, 0, 0, 0)

# --- Link: 16 x 16, side view facing right. Frame 1 is the walk pose with the
# legs together; frame 2 is the stride pose (Zelda Wiki, TLoZ Link Sprite 3).
LINK_WALK = [
    [
        ".....GGGG.......",
        "...GGGGGBBBB....",
        ".GGGSGGBBBBBB...",
        "GGGGSSBBBBBB....",
        "G.GGSSSBSSgS..B.",
        "..GBBSSBSSbSSSB.",
        "...BBBSSSSSS..B.",
        "....GGGGSSSS..B.",
        "..BGGGGGGGBBBSB.",
        ".BBBGSSSGGGBBSB.",
        ".BBBBSSSGGGBB.B.",
        ".BBBBSSGGGB...B.",
        "..GBBGGBBBB...B.",
        ".GGGGGGGGGG.....",
        "....BBBB........",
        "....BBBBB.......",
    ],
    [
        "................",
        ".....GGGG.......",
        "...GGGGGBBBB....",
        ".GGGSGGBBBBBB...",
        "GGGGSSBBBBBB....",
        "G.GGSSSBSSgS....",
        "..GBBSSBSSbSSS..",
        "...BBBSSSSSS.B..",
        "....GGGGSSSS.B..",
        "..GBBGGSSSBBSB..",
        "..BBBBBSSSGBSB..",
        ".GBBBBBSSGGB.B..",
        ".GGBBBBGGGB..B..",
        "BBGGGGGBBBBG.B..",
        "BBBGGGGGGGGBB...",
        ".BBB.....BBB....",
    ],
]

# --- Mario: 16 x 16, side view facing right. The three frames of the Super
# Mario Bros. walk cycle, in playback order.
MARIO_WALK = [
    [
        "................",
        "......RRRRR.....",
        ".....RRRRRRRRR..",
        ".....BBBSSbS....",
        "....BSBSSSbSSS..",
        "....BSBBSSSBSSS.",
        "....BBSSSSBBBB..",
        "......SSSSSSS...",
        ".....BBBBRB.S...",
        "....SBBBBBBSSS..",
        "...SSRBBBBBSS...",
        "...BBRRRRRRR....",
        "...BRRRRRRRR....",
        "..BBRRR.RRR.....",
        "..B....BBB......",
        ".......BBBB.....",
    ],
    [
        ".....RRRRR......",
        "....RRRRRRRRR...",
        "....BBBSSbS.....",
        "...BSBSSSbSSS...",
        "...BSBBSSSBSSS..",
        "...BBSSSSBBBB...",
        ".....SSSSSSS....",
        "..BBBBRRBB......",
        "SSBBBBRRRBBBSSS.",
        "SSS.BBRsRRRBBSS.",
        "SS..RRRRRRR..B..",
        "...RRRRRRRRRBB..",
        "..RRRRRRRRRRBB..",
        ".BBRRR...RRRBB..",
        ".BBB............",
        "..BBB...........",
    ],
    [
        ".....RRRRR......",
        "....RRRRRRRRR...",
        "....BBBSSbS.....",
        "...BSBSSSbSSS...",
        "...BSBBSSSBSSS..",
        "...BBSSSSBBBB...",
        ".....SSSSSSS....",
        "....BBRBBB......",
        "...BBBBRRBB.....",
        "...BBBRRsRRS....",
        "...BBBBRRRRR....",
        "...RBBSSSRRR....",
        "....RBSSRRR.....",
        ".....RRRBBB.....",
        ".....BBBBBBB....",
        ".....BBBB.......",
    ],
]

# --- Knight: 8 x 8, side view ------------------------------------------------
KNIGHT_WALK = [
    [
        ".GGGGG.G",
        ".GWWWW.G",
        ".GWkkk.G",
        ".GWWkW.G",
        "SSSGGGGW",
        "SSSKWK..",
        "SSSGGG..",
        ".K...K..",
    ],
    [
        ".GGGGGG.",
        ".GWWWWG.",
        ".GWkkkG.",
        ".GWWkWG.",
        ".SSSGGW.",
        ".SSSWK..",
        ".SSSGG..",
        "..KKK...",
    ],
]

# --- Link attack: 26 x 16, facing left. Frame 1 is the walking stance mirrored
# (the game flips the sprite for left); frame 2 is the sword thrust.
# --- Terraria miner: 33 x 26, facing right. Frame 1 is the pickaxe raised
# behind the head; frame 2 repeats the body with the arm and pickaxe rotated
# 180 degrees about the shoulder.
LINK_ATTACK = [
    [
        "................GGGG......",
        ".............BBBBGGGGG....",
        "............BBBBBBGGSGGG..",
        ".............BBBBBBSSGGGG.",
        "..........B..SgSSBSSSGG.G.",
        "..........BSSSbSSBSSBBG...",
        "..........B..SSSSSSBBB....",
        "..........B..SSSSGGGG.....",
        "..........BSBBBGGGGGGGB...",
        "..........BSBBGGGSSSGBBB..",
        "..........B.BBGGGSSSBBBB..",
        "..........B...BGGGSSBBBB..",
        "..........B...BBBBGGBBG...",
        "..............GGGGGGGGGG..",
        ".................BBBB.....",
        "................BBBBB.....",
    ],
    [
        "................GGGG......",
        ".............BBBBGGGGG....",
        "............BBBBBBGGSGG...",
        ".............BBBBBBSSGG...",
        ".............SgSSBSSSGGG..",
        "..........GSSSbSSBSSBBGGG.",
        "..........G..SSSSSSBBB..G.",
        ".BBBBBBBBBGSSSSSSGGGGG....",
        "BBBBBBBBBBGSSSSBBBBBBGG...",
        ".BBBBBBBBBGSGSSBBBBBBBG...",
        "..........G...GBBBBBBBGG..",
        "..........GG.BBGGGBBBGGGG.",
        ".............BBBBBGGGGGGBB",
        "............BBGGGGGGGGGBBB",
        "...........BBBB.......BBB.",
        "..........................",
    ],
]

TERRARIA_MINE = [
    [
        "............K.KK.K...............",
        ".........KKKHKHRKRK..............",
        "........KHHHHHHHRHRK.............",
        "......KKKKHRRHHHHHHHKK...........",
        "..K.KKIINKHHHRHHRRHRHRK..........",
        ".KTKIINKKHHRKRRHHHRHRK...........",
        "..KIINK.KHKKSKKHKRHHK............",
        ".KIINK...K.KSKeKSKHRRK...........",
        ".KINKTK....KSKeSSKRRK............",
        "KINK.KTK..KSSSSSDKKK.............",
        "KNK...KTK..KSSSDKFK..............",
        "KNK....KTK..KKKKGGGK.............",
        ".K......KTKKKGGGGGGK.............",
        ".........KSSDGGGFGFK.............",
        ".........KSSDGFFKKK..............",
        ".........KDDDKKKKFK..............",
        "..........KKKKKGGFK..............",
        "...........KPKPPJJK..............",
        "...........KPKPPJK...............",
        "...........KPKPPJK...............",
        "...........KJKPPJJK..............",
        "...........KBKBPPJK..............",
        "..........KBKBBBJJK..............",
        "..........KKKKKKKKK..............",
        ".................................",
        ".................................",
    ],
    [
        "............K.KK.K...............",
        ".........KKKHKHRKRK..............",
        "........KHHHHHHHRHRK.............",
        ".........KHRRHHHHHHHKK...........",
        ".........KHHHRHHRRHRHRK..........",
        "........KHHRKRRHHHRHRK...........",
        "........KHKKSKKHKRHHK............",
        ".........K.KSKeKSKHRRK...........",
        "...........KSKeSSKRRK............",
        "..........KSSSSSDKKK.............",
        "...........KSSSDKFK..............",
        "............KKKKGGGK.............",
        "............KGGGGGGKKKK..........",
        "............KGGGFGFKDDDK.........",
        "............KGFFKKK.DSSK.........",
        "............KKKKKFK.DSSK.........",
        "............KKKGGFK.KKKTK......K.",
        "...........KPKPPJJK....KTK....KNK",
        "...........KPKPPJK......KTK...KNK",
        "...........KPKPPJK.......KTK.KNIK",
        "...........KJKPPJJK.......KTKNIK.",
        "...........KBKBPPJK........KNIIK.",
        "..........KBKBBBJJK.......KNIIK..",
        "..........KKKKKKKKK......KNIIKTK.",
        "........................NIIKK.K..",
        "........................KKK......",
    ],
]

# grey: region letter -> tone. "k" becomes transparent, "g" becomes grey. These
# are the earlier black and grey regions, so the sprite is the negative of the
# first masks.
LINK_GREY = {
    # hair, shield, sword and boots open; cap, tunic, face and arm grey
    "B": "k", "G": "g", "S": "g",
}
ANIMATIONS = [
    {
        "character": "link", "action": "walk", "frames": LINK_WALK,
        "frame": PORTRAIT, "frame_ms": FRAME_MS, "grey": LINK_GREY,
    },
    {
        "character": "mario", "action": "walk", "frames": MARIO_WALK,
        "frame": PORTRAIT, "frame_ms": 100,
        # hair, sleeves, moustache and shoes open; cap, overalls, face and
        # hands grey
        "grey": {"R": "g", "B": "k", "S": "g"},
    },
    {
        "character": "knight", "action": "walk", "frames": KNIGHT_WALK,
        "frame": PORTRAIT, "frame_ms": FRAME_MS,
        # helmet, arm, sword, body and feet open; visor, shield and belt
        # buckle grey
        "grey": {"G": "k", "W": "g", "K": "k", "S": "g"},
    },
    {
        "character": "link", "action": "attack", "frames": LINK_ATTACK,
        "frame": LANDSCAPE, "frame_ms": FRAME_MS, "grey": LINK_GREY,
    },
    {
        "character": "terraria", "action": "mine", "frames": TERRARIA_MINE,
        "frame": PORTRAIT, "frame_ms": FRAME_MS,
        # outline, hair, pickaxe handle and boots open; skin, shirt, pants
        # and pickaxe head grey
        "grey": {
            "K": "k", "H": "k", "J": "k", "R": "k", "T": "k", "B": "k",
            "S": "g", "D": "g", "G": "g", "F": "g", "P": "g", "I": "g", "N": "g",
        },
    },
]

TONES = {"k": CLEAR, "g": GREY}


def drawn_box(frames):
    """Bounding box (x0, y0, x1, y1) of every drawn cell across the frames."""
    xs = [x for rows in frames for row in rows for x, ch in enumerate(row) if ch != "."]
    ys = [y for rows in frames for y, row in enumerate(rows) for ch in row if ch != "."]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def mask(rows, box, tone_of):
    """One pixel per grid cell inside box. Background and cut-outs are black;
    tone_of maps a region letter to its RGBA."""
    x0, y0, x1, y1 = box
    img = Image.new("RGBA", (x1 - x0, y1 - y0), BLACK)
    for y in range(y0, y1):
        row = rows[y]
        assert len(row) == len(rows[0]), f"ragged row {y}: {row!r}"
        for x in range(x0, x1):
            ch = row[x]
            if ch == "." or ch.islower():
                continue
            img.putpixel((x - x0, y - y0), tone_of(ch))
    return img


def fit(img, frame):
    """Scale img as large as the frame allows and centre it on black."""
    fw, fh = frame
    scale = min(fw / img.width, fh / img.height)
    if INTEGER_SCALE:
        scale = max(1, int(scale))
    w = min(fw, round(img.width * scale))
    h = min(fh, round(img.height * scale))
    out = Image.new("RGBA", frame, BLACK)
    out.paste(img.resize((w, h), Image.NEAREST), ((fw - w) // 2, (fh - h) // 2))
    return out


def gif_frame(img):
    """Palette 0 is black, 1 is grey, 2 is the transparent colour."""
    p = Image.new("P", img.size, 2)
    p.putpalette([0, 0, 0, 128, 128, 128, 255, 255, 255])
    data = []
    for r, _, _, a in img.getdata():
        data.append(2 if a == 0 else (0 if r == 0 else 1))
    p.putdata(data)
    return p


def save_variant(variant, character, action, frames, frame_ms):
    folder = OUT / variant / character
    folder.mkdir(parents=True, exist_ok=True)
    tag = f"{character}_{variant}_{action}"
    for i, frame in enumerate(frames, start=1):
        frame.save(folder / f"{tag}_{i}.png")
    frames[0].save(
        folder / f"{tag}_anim.png",
        save_all=True,
        append_images=frames[1:],
        duration=frame_ms,
        loop=0,
        disposal=2,
    )
    gif = [gif_frame(f) for f in frames]
    gif[0].save(
        folder / f"{tag}.gif",
        save_all=True,
        append_images=gif[1:],
        duration=frame_ms,
        loop=0,
        disposal=2,
        transparency=2,
    )


def main():
    for a in ANIMATIONS:
        box = drawn_box(a["frames"])
        tones = {
            "binary": lambda ch: CLEAR,
            "grey": lambda ch, m=a["grey"]: TONES.get(m.get(ch), BLACK),
        }
        for variant, tone_of in tones.items():
            frames = [fit(mask(f, box, tone_of), a["frame"]) for f in a["frames"]]
            save_variant(variant, a["character"], a["action"], frames, a["frame_ms"])


if __name__ == "__main__":
    main()
