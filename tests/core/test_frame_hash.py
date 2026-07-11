from PIL import Image

from videodoc.core.utils.frame_hash import average_hash, hamming_distance, is_near_duplicate


def _make_image(path, fill):
    Image.new("RGB", (32, 32), color=fill).save(path)


def _make_half_split(path, *, vertical):
    """A 32x32 image, half black half white, split either vertically (left
    black / right white) or horizontally (top black / bottom white). Used
    instead of two flat single colors: aHash thresholds each pixel against
    its own image's mean, so two perfectly flat (single-color) images
    always hash identically regardless of their absolute brightness --
    only images with internal structure can meaningfully differ."""
    img = Image.new("L", (32, 32), color=0)
    if vertical:
        for x in range(16, 32):
            for y in range(32):
                img.putpixel((x, y), 255)
    else:
        for x in range(32):
            for y in range(16, 32):
                img.putpixel((x, y), 255)
    img.save(path)


def test_average_hash_returns_hex_string_of_expected_length(tmp_path):
    path = tmp_path / "a.jpg"
    _make_image(path, (128, 128, 128))
    hash_hex = average_hash(path)
    assert isinstance(hash_hex, str)
    assert len(hash_hex) == 18  # (64 spatial + 8 brightness) bits / 4 bits-per-hex-digit for the default hash_size=8


def test_flat_images_of_different_brightness_are_not_near_duplicates(tmp_path):
    """Regression test (found via a real end-to-end run against a video
    with a hard cut from a solid red frame to a solid blue frame): plain
    aHash sets each spatial bit relative to the image's own mean, so two
    perfectly flat (single-color) images always hash identically on
    spatial bits alone regardless of their actual brightness -- a real
    problem for screen recordings, which are full of flat regions (blank
    terminals, solid-color slides). Two genuinely different flat colors
    must not be classified as near-duplicates, even though their spatial
    bits alone are identical (both all-1s: every pixel equals its own
    mean) -- this is exactly what is_near_duplicate's separate numeric
    brightness comparison is for; a raw Hamming distance over the whole
    hash (spatial bits + brightness suffix XORed together) is NOT a
    reliable way to tell these apart, since bit-XOR distance does not
    correlate with numeric closeness for a magnitude value."""
    dark = tmp_path / "dark.jpg"
    light = tmp_path / "light.jpg"
    _make_image(dark, (20, 20, 20))
    _make_image(light, (220, 220, 220))
    assert not is_near_duplicate(average_hash(dark), average_hash(light))


def test_identical_flat_images_are_near_duplicates(tmp_path):
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    _make_image(a, (128, 128, 128))
    _make_image(b, (128, 128, 128))
    assert is_near_duplicate(average_hash(a), average_hash(b))


def test_identical_images_have_zero_hamming_distance(tmp_path):
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    _make_image(a, (200, 50, 50))
    _make_image(b, (200, 50, 50))
    assert hamming_distance(average_hash(a), average_hash(b)) == 0


def test_very_different_images_have_large_hamming_distance(tmp_path):
    vertical = tmp_path / "vertical.jpg"
    horizontal = tmp_path / "horizontal.jpg"
    _make_half_split(vertical, vertical=True)
    _make_half_split(horizontal, vertical=False)
    # A vertical vs. a horizontal half-split should differ in roughly half
    # the bits (the rows/columns that agree by symmetry don't count) --
    # loosely bounded rather than an exact figure to avoid coupling the
    # test to LANCZOS resampling's exact edge behavior.
    assert hamming_distance(average_hash(vertical), average_hash(horizontal)) > 20


def test_hamming_distance_is_symmetric(tmp_path):
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    _make_image(a, (10, 20, 30))
    _make_image(b, (200, 210, 220))
    hash_a, hash_b = average_hash(a), average_hash(b)
    assert hamming_distance(hash_a, hash_b) == hamming_distance(hash_b, hash_a)
