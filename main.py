#!/usr/bin/env python3
"""The World in a Day - Saturday 21 November 2026.

A deterministic news-image generator (Python 3.13, standard library only).
It draws a one-page newspaper front page summing up the day's world news
and writes it as a 1024x1024 PNG to /output/entry.png (or the directory
named by $MAKEFUN_OUTPUT_DIR).

Run:  python3 main.py            (writes the entry image)
      python3 main.py --check    (writes to a temp dir and verifies the PNG)

The picture is drawn entirely in code: a pure-Python PNG encoder, a 5x7
bitmap font, and simple geometric pictograms. No network, no randomness,
no timestamps: two runs produce byte-identical output.
"""

import binascii
import hashlib
import os
import struct
import sys
import tempfile
import zlib

WIDTH = 1024
HEIGHT = 1024

PAPER = (248, 244, 233)
INK = (20, 20, 20)
RED = (163, 30, 34)
BLUE = (47, 84, 124)

# ---------------------------------------------------------------------------
# 5x7 bitmap font. Each glyph is seven rows of five cells; '#' is ink.
# ---------------------------------------------------------------------------

FONT = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "..##.", ".#...", "#....", "#####"),
    "3": ("#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ",": (".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    ";": (".....", ".##..", ".##..", ".....", ".##..", "..#..", ".#..."),
    "'": ("..#..", "..#..", ".#...", ".....", ".....", ".....", "....."),
    "-": (".....", ".....", ".....", ".###.", ".....", ".....", "....."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "..##.", "..#..", ".....", "..#.."),
    "(": ("...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."),
    ")": (".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."),
    "/": ("....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."),
    "&": (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
    "%": ("##..#", "##.#.", "...#.", "..#..", ".#...", ".#.##", "#.##."),
}


def text_width(text, scale):
    """Pixel width of a string rendered at the given scale."""
    if not text:
        return 0
    return len(text) * 6 * scale - scale


# ---------------------------------------------------------------------------
# Canvas: an RGB image with simple drawing primitives.
# ---------------------------------------------------------------------------

class Canvas:
    def __init__(self, width, height, colour):
        self.width = width
        self.height = height
        r, g, b = colour
        self.pixels = bytearray(bytes((r, g, b)) * (width * height))

    def _offset(self, x, y):
        return (y * self.width + x) * 3

    def set_pixel(self, x, y, colour):
        if 0 <= x < self.width and 0 <= y < self.height:
            off = self._offset(x, y)
            self.pixels[off:off + 3] = bytes(colour)

    def fill_rect(self, x, y, w, h, colour):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(colour) * (x1 - x0)
        for yy in range(y0, y1):
            off = self._offset(x0, yy)
            self.pixels[off:off + len(row)] = row

    def hline(self, x, y, length, colour, thick=1):
        self.fill_rect(x, y, length, thick, colour)

    def vline(self, x, y, length, colour, thick=1):
        self.fill_rect(x, y, thick, length, colour)

    def line(self, x0, y0, x1, y1, colour, thick=1):
        """Bresenham line, with a square brush of the given thickness."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        half = thick // 2
        while True:
            self.fill_rect(x0 - half, y0 - half, thick, thick, colour)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def ellipse_outline(self, cx, cy, rx, ry, colour, thick=2, steps=96):
        """Outline of an axis-aligned ellipse, drawn as short chords."""
        import math
        prev = None
        for i in range(steps + 1):
            ang = 2.0 * math.pi * i / steps
            px = cx + int(round(rx * math.cos(ang)))
            py = cy + int(round(ry * math.sin(ang)))
            if prev is not None:
                self.line(prev[0], prev[1], px, py, colour, thick)
            prev = (px, py)

    def circle_outline(self, cx, cy, radius, colour, thick=2):
        self.ellipse_outline(cx, cy, radius, radius, colour, thick)

    def fill_circle(self, cx, cy, radius, colour):
        """Solid disc, drawn scanline by scanline."""
        import math
        for dy in range(-radius, radius + 1):
            dx = int(round(math.sqrt(max(0, radius * radius - dy * dy))))
            self.hline(cx - dx, cy + dy, 2 * dx + 1, colour)

    def draw_text(self, x, y, text, scale, colour):
        """Draw a string with the 5x7 bitmap font; returns the width used."""
        cursor = x
        for ch in text:
            glyph = FONT.get(ch, FONT[" "])
            for row in range(7):
                bits = glyph[row]
                for col in range(5):
                    if bits[col] == "#":
                        self.fill_rect(
                            cursor + col * scale, y + row * scale,
                            scale, scale, colour,
                        )
            cursor += 6 * scale
        return cursor - x - scale

    def draw_text_centred(self, cx, y, text, scale, colour):
        x = cx - text_width(text, scale) // 2
        return self.draw_text(x, y, text, scale, colour)


# ---------------------------------------------------------------------------
# The day's news: four lead stories and two short items, as reported on
# Saturday 21 November 2026. Each story: tag, two headline lines, two
# standfirst lines, pictogram kind.
# ---------------------------------------------------------------------------

STORIES = [
    (
        "EUROPE",
        ("UK AND EU STRIKE", "LANDMARK DEAL"),
        ("TRADE, CARBON AND YOUTH MOBILITY AGREED IN BRUSSELS;",
         "ERASMUS RETURNS FOR BRITISH STUDENTS."),
        "globe",
    ),
    (
        "CLIMATE",
        ("CLIMATE TALKS IN", "OVERTIME"),
        ("DRAFT DEAL DROPS FOSSIL FUELS; THE EU WARNS OF A",
         "'FOSSIL SUMMIT' AS TALKS RUN PAST THEIR DEADLINE."),
        "sun",
    ),
    (
        "JUSTICE",
        ("MYANMAR REJECTS", "GENOCIDE RULING"),
        ("THE WORLD COURT FOUND MYANMAR GUILTY OVER THE",
         "ROHINGYA. NAYPYIDAW CALLS THE RULING UNJUST."),
        "scales",
    ),
    (
        "SECURITY",
        ("MISSILE LANDS", "IN POLAND"),
        ("A RUSSIAN MISSILE CROSSED THE BORDER DURING THE",
         "KYIV STRIKES. TUSK CALLS IT A PROVOCATION."),
        "bridge",
    ),
]

FOOTER = "ALSO: GAZA TRUCE STRAINED - UN BACKS PALESTINE VOTE - 162 NATIONS SAY YES"


# ---------------------------------------------------------------------------
# Pictograms, drawn with the canvas primitives inside a small box.
# ---------------------------------------------------------------------------

def draw_globe(canvas, x, y, w, h):
    cx, cy = x + w // 2, y + h // 2
    r = min(w, h) // 2 - 8
    canvas.circle_outline(cx, cy, r, INK, 3)
    canvas.ellipse_outline(cx, cy, r // 2, r, INK, 2)
    canvas.hline(cx - r, cy, 2 * r, INK, 2)
    canvas.ellipse_outline(cx, cy, r, r // 3, INK, 2)
    canvas.fill_rect(cx - r - 8, cy - r - 8, 4, 4, RED)


def draw_sun(canvas, x, y, w, h):
    import math
    cx, cy = x + w // 2, y + h // 2 - 6
    r = min(w, h) // 4
    canvas.circle_outline(cx, cy, r, RED, 3)
    canvas.fill_circle(cx, cy, r // 2, RED)
    for i in range(8):
        ang = math.pi * i / 4.0
        x0 = cx + int(round((r + 8) * math.cos(ang)))
        y0 = cy + int(round((r + 8) * math.sin(ang)))
        x1 = cx + int(round((r + 22) * math.cos(ang)))
        y1 = cy + int(round((r + 22) * math.sin(ang)))
        canvas.line(x0, y0, x1, y1, RED, 3)
    canvas.hline(x + 14, y + h - 26, w - 28, BLUE, 3)
    canvas.hline(x + 30, y + h - 14, w - 60, BLUE, 3)


def draw_scales(canvas, x, y, w, h):
    cx = x + w // 2
    top = y + 14
    bottom = y + h - 20
    canvas.vline(cx, top, bottom - top, INK, 4)
    canvas.hline(cx - 58, top, 116, INK, 4)
    canvas.hline(cx - 46, bottom, 92, INK, 4)
    for side in (-1, 1):
        px = cx + side * 58
        canvas.vline(px, top, 34, INK, 3)
        canvas.line(px - 26, top + 58, px + 26, top + 58, INK, 3)
        canvas.line(px - 26, top + 58, px, top + 34, INK, 3)
        canvas.line(px + 26, top + 58, px, top + 34, INK, 3)


def draw_bridge(canvas, x, y, w, h):
    import math
    cx = x + w // 2
    deck_y = y + h // 2 + 18
    canvas.hline(x + 8, deck_y, w - 16, INK, 4)
    prev = None
    for i in range(96 + 1):
        ang = math.pi * i / 96.0
        px = cx + int(round(72 * math.cos(math.pi - ang)))
        py = deck_y - int(round(52 * math.sin(ang)))
        if prev is not None:
            canvas.line(prev[0], prev[1], px, py, INK, 3)
        prev = (px, py)
    for px in (x + 30, cx, x + w - 30):
        canvas.vline(px, deck_y, h - (deck_y - y) - 24, INK, 3)
    canvas.hline(x + 20, y + h - 16, w - 40, BLUE, 3)
    canvas.hline(x + 44, y + h - 6, w - 88, BLUE, 3)


PICTOGRAMS = {
    "globe": draw_globe,
    "sun": draw_sun,
    "scales": draw_scales,
    "bridge": draw_bridge,
}


# ---------------------------------------------------------------------------
# Page layout.
# ---------------------------------------------------------------------------

MARGIN = 36
RIGHT = WIDTH - MARGIN


def draw_masthead(canvas):
    canvas.draw_text_centred(WIDTH // 2, 40, "THE WORLD IN A DAY", 5, INK)
    canvas.hline(MARGIN, 88, RIGHT - MARGIN, RED, 4)
    canvas.draw_text_centred(WIDTH // 2, 100, "SATURDAY 21 NOVEMBER 2026", 3, INK)
    canvas.hline(MARGIN, 128, RIGHT - MARGIN, INK, 6)
    canvas.hline(MARGIN, 138, RIGHT - MARGIN, INK, 2)


def draw_story(canvas, row_y, story):
    tag, headline, standfirst, kind = story
    box_x, box_y, box_w, box_h = MARGIN, row_y + 8, 176, 180
    canvas.fill_rect(box_x, box_y, box_w, box_h, (255, 255, 255))
    canvas.hline(box_x, box_y, box_w, INK, 2)
    canvas.hline(box_x, box_y + box_h, box_w, INK, 2)
    canvas.vline(box_x, box_y, box_h, INK, 2)
    canvas.vline(box_x + box_w, box_y, box_h, INK, 2)
    PICTOGRAMS[kind](canvas, box_x, box_y, box_w, box_h)
    text_x = box_x + box_w + 20
    canvas.draw_text(text_x, row_y + 8, tag, 2, RED)
    canvas.draw_text(text_x, row_y + 30, headline[0], 4, INK)
    canvas.draw_text(text_x, row_y + 66, headline[1], 4, INK)
    canvas.draw_text(text_x, row_y + 112, standfirst[0], 2, INK)
    canvas.draw_text(text_x, row_y + 134, standfirst[1], 2, INK)


def render():
    canvas = Canvas(WIDTH, HEIGHT, PAPER)
    draw_masthead(canvas)
    row_y = 154
    for story in STORIES:
        draw_story(canvas, row_y, story)
        row_y += 204
    canvas.hline(MARGIN, 972, RIGHT - MARGIN, INK, 2)
    canvas.draw_text_centred(WIDTH // 2, 984, FOOTER, 2, INK)
    return canvas


# ---------------------------------------------------------------------------
# PNG encoding (pure standard library, deterministic).
# ---------------------------------------------------------------------------

def png_chunk(kind, data):
    chunk = struct.pack(">I", len(data)) + kind + data
    chunk += struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    return chunk


def encode_png(canvas):
    raw = bytearray()
    stride = canvas.width * 3
    for y in range(canvas.height):
        raw.append(0)  # filter: none
        start = y * stride
        raw += canvas.pixels[start:start + stride]
    ihdr = struct.pack(">IIBBBBB", canvas.width, canvas.height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", ihdr)
    png += png_chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += png_chunk(b"IEND", b"")
    return png


def verify_png(data):
    """Check the PNG is whole: signature, IHDR size, chunk CRCs, size cap."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("bad PNG signature")
    if len(data) > 1048576:
        raise ValueError("over the 1 MiB cap")
    pos = 8
    seen_iend = False
    dims = None
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated chunk header")
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(data):
            raise ValueError("truncated chunk " + kind.decode("latin1"))
        crc = struct.unpack(">I", data[end - 4:end])[0]
        actual = binascii.crc32(data[pos + 4:end - 4]) & 0xFFFFFFFF
        if crc != actual:
            raise ValueError("bad CRC in chunk " + kind.decode("latin1"))
        if kind == b"IHDR":
            dims = struct.unpack(">II", data[pos + 8:pos + 16])
        if kind == b"IEND":
            seen_iend = True
            if end != len(data):
                raise ValueError("trailing bytes after IEND")
        pos = end
    if not seen_iend:
        raise ValueError("missing IEND")
    if dims != (WIDTH, HEIGHT):
        raise ValueError("wrong dimensions: %r" % (dims,))
    return True


def write_entry(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    png = encode_png(render())
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as handle:
        handle.write(png)
    digest = hashlib.sha256(png).hexdigest()
    print("wrote %s (%d bytes, sha256 %s)" % (path, len(png), digest))
    return path, png


def main(argv):
    if "--check" in argv:
        with tempfile.TemporaryDirectory() as tmp:
            path, png = write_entry(tmp)
            verify_png(png)
            print("CHECK OK: %s is a whole %dx%d PNG under the size cap"
                  % (path, WIDTH, HEIGHT))
        return 0
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    write_entry(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
