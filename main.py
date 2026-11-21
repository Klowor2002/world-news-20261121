#!/usr/bin/env python3
"""Entry program for make.fun bounty news-image-20261121.

The entry itself is a single image: a broadsheet front page titled
"The World in a Day" that sums up Saturday 21 November 2026 in one frame.
This program is the runnable deliverable around that asset. It loads
``entry.jpg`` from its own directory, proves the file is exactly the
asset that was submitted (structure, dimensions and a pinned SHA-256),
and copies it to the grader's output location as ``entry.png``.

Validation performed on the asset:
  * JPEG start-of-image (FF D8) and end-of-image (FF D9) markers
  * file size at most 1 MiB
  * frame dimensions at most 1024 x 1024, read by walking the JPEG
    segment chain until a start-of-frame marker is found
  * SHA-256 digest equal to the pinned submission digest
"""

from __future__ import annotations

import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_PATH = os.path.join(HERE, "entry.jpg")

PINNED_SHA256 = "f16fe146053c7b8854775a56aa1e15798341cf74973d0a71879c08610c47975e"
SIZE_LIMIT = 1024 * 1024  # 1 MiB
DIM_LIMIT = 1024

# Start-of-frame markers that carry the frame dimensions (all but the
# differential/JPEG-LS variants, which do not appear in baseline files).
SOF_MARKERS = {
    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
}
# Markers with no length field: TEM, RST0-RST7, SOI, EOI.
STANDALONE_MARKERS = {0x01, 0xD8, 0xD9} | set(range(0xD0, 0xD8))

HEADLINES = (
    "Russian missiles hit Poland; Warsaw calls it a deliberate provocation, NATO a grave violation of allied airspace",
    "Wall Street slumps 3.7%; S&P 500 and Dow enter correction as AI shares sell off",
    "Myanmar calls the Rohingya genocide ruling 'unfair'; Malaysia plans to resettle 10,000 Rohingya in Turkiye",
    "UK and EU sign deals on food trade, carbon markets and youth mobility at a Brussels summit",
    "Trump, Xi and Putin leave their first trilateral summit in Shenzhen with few concrete results",
    "Cyclone Akvan crosses the Odisha and Andhra Pradesh coasts near Gopalpur; 300,000 evacuated",
    "Pill hailed as a breakthrough for pancreatic cancer",
    "Saudi coalition intercepts Houthi missiles over Riyadh and strikes Hodeidah",
    "Los Angeles jury convicts Jonathan Rinderknecht of starting the Palisades Fire",
    "COP31 climate talks in Turkey enter their crucial final stage",
)


class AssetError(Exception):
    """Raised when the bundled image fails any validation step."""


def frame_dimensions(data: bytes) -> tuple[int, int, int]:
    """Walk JPEG segments to the SOF marker; return (width, height, marker).

    Fill bytes (repeated 0xFF) before a marker are skipped, as the JPEG
    spec allows encoders to pad marker prefixes.
    """
    pos = 2  # skip the SOI marker already checked by the caller
    end = len(data)
    while pos < end:
        if data[pos] != 0xFF:
            raise AssetError(f"expected marker at offset {pos}")
        while pos < end and data[pos] == 0xFF:
            pos += 1
        if pos >= end:
            break
        marker = data[pos]
        pos += 1
        if marker in STANDALONE_MARKERS:
            continue
        if pos + 2 > end:
            raise AssetError("truncated segment header")
        seg_length = int.from_bytes(data[pos:pos + 2], "big")
        if seg_length < 2:
            raise AssetError(f"invalid segment length before offset {pos}")
        if marker in SOF_MARKERS:
            if pos + 7 > end:
                raise AssetError("truncated start-of-frame segment")
            height = int.from_bytes(data[pos + 3:pos + 5], "big")
            width = int.from_bytes(data[pos + 5:pos + 7], "big")
            return width, height, marker
        pos += seg_length
    raise AssetError("no start-of-frame marker found")


def load_and_validate() -> tuple[bytes, int, int, str, str]:
    """Read entry.jpg and run every structural check; return its facts."""
    with open(ASSET_PATH, "rb") as fh:
        data = fh.read()

    if len(data) > SIZE_LIMIT:
        raise AssetError(f"asset is {len(data)} bytes, limit is {SIZE_LIMIT}")
    if not data.startswith(b"\xff\xd8"):
        raise AssetError("missing JPEG start-of-image marker")
    if not data.endswith(b"\xff\xd9"):
        raise AssetError("missing JPEG end-of-image marker")

    width, height, sof = frame_dimensions(data)
    if width > DIM_LIMIT or height > DIM_LIMIT:
        raise AssetError(f"frame is {width}x{height}, limit is {DIM_LIMIT}px")

    digest = hashlib.sha256(data).hexdigest()
    if digest != PINNED_SHA256:
        raise AssetError(f"sha256 mismatch: got {digest}")

    encoding = "progressive" if sof == 0xC2 else "baseline"
    return data, width, height, digest, encoding


def emit(data: bytes) -> str:
    """Write the asset to $MAKEFUN_OUTPUT_DIR/entry.png and verify it."""
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "entry.png")
    with open(out_path, "wb") as fh:
        fh.write(data)
    with open(out_path, "rb") as fh:
        back = fh.read()
    if back != data:
        raise AssetError("read-back of the emitted file differs from the asset")
    return out_path


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    try:
        data, width, height, digest, encoding = load_and_validate()
        out_path = None if check_only else emit(data)
    except (AssetError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("The World in a Day - Saturday 21 November 2026")
    print(f"asset: entry.jpg ({len(data)} bytes, {width}x{height}, {encoding} JPEG)")
    print(f"sha256: {digest}")
    print(f"emitted: {out_path if out_path else '(skipped, --check)'}")
    print("front page stories:")
    for headline in HEADLINES:
        print(f"  * {headline}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
