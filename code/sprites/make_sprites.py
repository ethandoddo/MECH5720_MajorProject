"""Generate sprite animations as aperture masks in two tone sets.

Link, Mario, the Knight (Realm of the Mad God) and a Terraria miner are written
as character grids. Each animation is written in two variants:

    binary   opaque black and transparent
    grey     opaque black, opaque mid-grey (128, 128, 128) and transparent

Grid letters record the original colour regions. In the binary variant every
region is black. In the grey variant each animation maps its regions to black
or grey (see ANIMATIONS). Other cells:

    .        transparent background
    a-z      transparent cut-out inside the silhouette (eye, button, visor
             slit); the letter is the original region, in lower case

Canvas sizes are native to each sprite: 16 x 16 for the walk cycles (the
Knight is drawn on 8 x 8 and upscaled 2x), 26 x 16 for the Link attack and
33 x 26 for the Terraria miner. Outputs per animation and variant, in
<variant>/<character>/: native PNGs, nearest-neighbour upscaled PNGs, and
looping GIF and APNG animations. Run from any directory:

    python3 make_sprites.py
"""
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent
TARGET_PX = 320  # longest side of the upscaled outputs
FRAME_MS = 250
BLACK = (0, 0, 0, 255)
GREY = (128, 128, 128, 255)

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

# grey: region letter -> tone. "k" is black, "g" is grey. Regions left out
# are transparent.
LINK_GREY = {
    # hair, shield, sword and boots black; cap, tunic, face and arm grey
    "B": "k", "G": "g", "S": "g",
}
ANIMATIONS = [
    {
        "character": "link", "action": "walk", "frames": LINK_WALK,
        "upscale": 1, "frame_ms": FRAME_MS, "grey": LINK_GREY,
    },
    {
        "character": "mario", "action": "walk", "frames": MARIO_WALK,
        "upscale": 1, "frame_ms": 100,
        # hair, sleeves, moustache and shoes black; cap, overalls, face and
        # hands grey
        "grey": {"R": "g", "B": "k", "S": "g"},
    },
    {
        "character": "knight", "action": "walk", "frames": KNIGHT_WALK,
        "upscale": 2, "frame_ms": FRAME_MS,
        # helmet, arm, sword, body and feet black; visor, shield and belt
        # buckle grey
        "grey": {"G": "k", "W": "g", "K": "k", "S": "g"},
    },
    {
        "character": "link", "action": "attack", "frames": LINK_ATTACK,
        "upscale": 1, "frame_ms": FRAME_MS, "grey": LINK_GREY,
    },
    {
        "character": "terraria", "action": "mine", "frames": TERRARIA_MINE,
        "upscale": 1, "frame_ms": FRAME_MS,
        # outline, hair, pickaxe handle and boots black; skin, shirt, pants
        # and pickaxe head grey
        "grey": {
            "K": "k", "H": "k", "J": "k", "R": "k", "T": "k", "B": "k",
            "S": "g", "D": "g", "G": "g", "F": "g", "P": "g", "I": "g", "N": "g",
        },
    },
]

TONES = {"k": BLACK, "g": GREY}


def mask(rows, tone_of):
    """One pixel per grid cell. tone_of maps a region letter to RGBA or None."""
    img = Image.new("RGBA", (len(rows[0]), len(rows)), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        assert len(row) == len(rows[0]), f"ragged row {y}: {row!r}"
        for x, ch in enumerate(row):
            if ch == "." or ch.islower():
                continue
            colour = tone_of(ch)
            if colour:
                img.putpixel((x, y), colour)
    return img


def upscale(img, factor):
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


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
    assert len({f.size for f in frames}) == 1
    folder = OUT / variant / character
    folder.mkdir(parents=True, exist_ok=True)
    tag = f"{character}_{variant}_{action}"
    scale = max(1, TARGET_PX // max(frames[0].size))
    big = [upscale(f, scale) for f in frames]
    for i, (frame, up) in enumerate(zip(frames, big), start=1):
        frame.save(folder / f"{tag}_{i}.png")
        up.save(folder / f"{tag}_{i}_x{scale}.png")
    big[0].save(
        folder / f"{tag}_x{scale}.png",
        save_all=True,
        append_images=big[1:],
        duration=frame_ms,
        loop=0,
        disposal=2,
    )
    gif = [gif_frame(b) for b in big]
    gif[0].save(
        folder / f"{tag}_x{scale}.gif",
        save_all=True,
        append_images=gif[1:],
        duration=frame_ms,
        loop=0,
        disposal=2,
        transparency=2,
    )


def main():
    for a in ANIMATIONS:
        tones = {
            "binary": lambda ch: BLACK,
            "grey": lambda ch, m=a["grey"]: TONES.get(m.get(ch)),
        }
        for variant, tone_of in tones.items():
            frames = [upscale(mask(f, tone_of), a["upscale"]) for f in a["frames"]]
            save_variant(variant, a["character"], a["action"], frames, a["frame_ms"])


if __name__ == "__main__":
    main()
