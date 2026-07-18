from __future__ import annotations

import hashlib
import math
import re

HASHING_EMBEDDING_DIMENSIONS = 256
HASHING_EMBEDDING_BACKEND = "feature-hashing"

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_./:@#-]+")


def embed_text_hashing(text: str, *, dimensions: int = HASHING_EMBEDDING_DIMENSIONS) -> list[float]:
    if dimensions <= 0:
        raise ValueError("dimensions must be positive")

    vector = [0.0] * dimensions
    tokens = [token.lower() for token in _TOKEN_RE.findall(text)]
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [round(value / norm, 8) for value in vector]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
