"""
core/loader.py
--------------
Handles CSV file loading with automatic encoding detection.
Uses `chardet` to sniff the file encoding so UTF-8, UTF-16, Latin-1, etc.
all work without user intervention.
"""

import io
import chardet
import pandas as pd


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_csv(file_obj) -> tuple[pd.DataFrame, str]:
    """
    Load a CSV from a file-like object (Streamlit UploadedFile or open() handle).

    Returns
    -------
    df : pd.DataFrame
        The loaded data.
    encoding : str
        The detected encoding (e.g. 'utf-8', 'latin-1').

    Notes
    -----
    All columns are loaded as *strings* (dtype=str) so that comparisons are
    character-exact and numeric values are not silently cast.
    """
    # Read the raw bytes once so we can sniff encoding *and* then parse.
    raw_bytes: bytes = _read_bytes(file_obj)

    # ── Encoding detection ──────────────────────────────────────────────────
    detected = chardet.detect(raw_bytes)
    encoding: str = detected.get("encoding") or "utf-8"

    # ── Parse the CSV ───────────────────────────────────────────────────────
    try:
        df = pd.read_csv(
            io.BytesIO(raw_bytes),
            encoding=encoding,
            dtype=str,          # keep everything as text
            keep_default_na=False,  # treat empty strings as "" not NaN
        )
    except UnicodeDecodeError:
        # Last-resort fallback: errors='replace' never crashes
        df = pd.read_csv(
            io.BytesIO(raw_bytes),
            encoding="utf-8",
            errors="replace",
            dtype=str,
            keep_default_na=False,
        )
        encoding = "utf-8 (fallback)"

    # Strip leading/trailing whitespace from column names and cell values
    df.columns = [c.strip() for c in df.columns]
    df = df.apply(lambda col: col.str.strip() if col.dtype == object else col)

    return df, encoding


def preview(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Return the first *n* rows of a DataFrame for display purposes."""
    return df.head(n)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_bytes(file_obj) -> bytes:
    """
    Normalise various file-like objects to raw bytes.

    Supports:
    - Streamlit ``UploadedFile`` (has .read() and .seek())
    - Regular Python ``io.IOBase`` file handles
    - Plain ``bytes`` / ``bytearray``
    """
    if isinstance(file_obj, (bytes, bytearray)):
        return bytes(file_obj)

    # Seek back to the start in case the caller already read some bytes.
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)

    return file_obj.read()
