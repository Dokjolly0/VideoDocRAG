from __future__ import annotations

from pathlib import Path

from PIL import Image

# Spatial Hamming distance (out of hash_size**2 bits, 64 for the default 8x8
# hash) at or below which two frames are considered near-duplicates for
# this phase's adjacent-frame dedup pass. ~6% of 64 bits -- loose enough to
# catch a static screen re-captured a moment apart, tight enough not to
# conflate genuinely different frames.
HASH_DEDUP_MAX_DISTANCE = 4

# Maximum difference in quantized mean brightness (0..255) for two frames to
# still count as near-duplicates. A *numeric* threshold, not a bit-count
# one: unlike the spatial bits (independent pass/fail comparisons, where
# Hamming distance is the right measure), brightness is a single magnitude,
# and raw bit-XOR distance on a magnitude value does not correlate with how
# numerically close two values are (e.g. 63 vs 64 differ in every bit).
BRIGHTNESS_DEDUP_MAX_DELTA = 10

_BRIGHTNESS_HEX_DIGITS = 2  # the trailing 8-bit brightness suffix, in hex


def average_hash(image_path: Path, *, hash_size: int = 8) -> str:
    """Average hash (aHash) of an image, returned as a zero-padded hex
    string: hash_size**2 spatial bits (64 for the default 8x8) followed by
    an 8-bit quantized mean brightness suffix. Downscales to a tiny
    grayscale hash_size x hash_size thumbnail, then sets one spatial bit per
    pixel based on whether it's above or below the thumbnail's own mean
    brightness -- a classic, cheap perceptual hash that survives JPEG
    recompression noise and minor encoding differences, which is all this
    phase needs (adjacent near-duplicate detection, not exact matching).

    Classic aHash's per-pixel-relative-to-own-mean rule has a real blind
    spot this phase actually hits: any perfectly (or near-)flat image --
    common in screen recordings (a blank terminal, a solid-color title
    slide) -- has every pixel equal to its own mean, so two DIFFERENT flat
    colors (e.g. a solid red frame and a solid blue frame) hash identically
    on spatial bits alone, since absolute brightness is discarded by
    construction. The brightness suffix appended here -- compared
    numerically by is_near_duplicate, not by bit-XOR -- fixes that specific
    case (still grayscale, so two flat colors of coincidentally identical
    luminance remain indistinguishable -- an accepted limitation shared by
    every grayscale-based perceptual hash, not something spatial bits alone
    could ever fix)."""
    with Image.open(image_path) as img:
        thumbnail = img.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
        pixels = list(thumbnail.getdata())

    mean = sum(pixels) / len(pixels)
    spatial_bits = "".join("1" if p >= mean else "0" for p in pixels)
    spatial_hex = f"{int(spatial_bits, 2):0{len(spatial_bits) // 4}x}"
    brightness_hex = f"{round(mean) & 0xFF:0{_BRIGHTNESS_HEX_DIGITS}x}"
    return spatial_hex + brightness_hex


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Bit-level Hamming distance between two same-length hex hash strings
    (spatial bits and brightness suffix alike). A generic bitwise-distance
    utility -- for this phase's actual near-duplicate decision, which needs
    the brightness suffix compared numerically instead, see
    is_near_duplicate."""
    int_a = int(hash_a, 16)
    int_b = int(hash_b, 16)
    return bin(int_a ^ int_b).count("1")


def is_near_duplicate(
    hash_a: str,
    hash_b: str,
    *,
    max_spatial_distance: int = HASH_DEDUP_MAX_DISTANCE,
    max_brightness_delta: int = BRIGHTNESS_DEDUP_MAX_DELTA,
) -> bool:
    """True if two average_hash() values represent near-duplicate frames:
    both a small spatial Hamming distance AND a small numeric brightness
    difference. Splitting the two checks (instead of one Hamming distance
    over the whole concatenated hash) is what makes two flat, differently
    colored frames (e.g. solid red vs. solid blue, identical spatial bits --
    both all-1s -- but very different brightness) correctly NOT count as
    duplicates: their brightness values can differ by dozens while still
    only flipping a handful of bits in a raw XOR, which is not a meaningful
    "closeness" measure for a magnitude value."""
    spatial_a, brightness_a = hash_a[:-_BRIGHTNESS_HEX_DIGITS], hash_a[-_BRIGHTNESS_HEX_DIGITS:]
    spatial_b, brightness_b = hash_b[:-_BRIGHTNESS_HEX_DIGITS], hash_b[-_BRIGHTNESS_HEX_DIGITS:]
    spatial_distance = hamming_distance(spatial_a, spatial_b)
    brightness_delta = abs(int(brightness_a, 16) - int(brightness_b, 16))
    return spatial_distance <= max_spatial_distance and brightness_delta <= max_brightness_delta
