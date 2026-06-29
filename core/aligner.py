"""
core/aligner.py  —  Phase 2
----------------------------
Row-alignment engine.

Modes
-----
1. align_positional        — row-by-row, pads shorter DF
2. align_by_key            — single-column exact outer-merge  (Phase 1)
3. align_by_composite_key  — multi-column exact outer-merge  (Phase 2 NEW)

Fuzzy alignment lives in core/fuzzy_aligner.py.
"""

import pandas as pd
import numpy as np

# Column injected to flag row provenance in key-based modes.
STATUS_COL = "__row_status__"

# Temporary column name used internally by composite-key alignment.
_COMPOSITE_KEY_COL = "__composite_key__"
_SEP = "|||"   # separator when concatenating composite key parts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def align_positional(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Align by row position.  Shorter DataFrame is padded with empty-string rows.
    """
    max_len = max(len(df_a), len(df_b))
    aligned_a = _pad_to_length(df_a, max_len).reset_index(drop=True)
    aligned_b = _pad_to_length(df_b, max_len).reset_index(drop=True)
    return aligned_a, aligned_b


def align_by_key(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    key_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Align via a single shared key column (exact match, outer merge).

    Rows present in only one file are padded with empty strings and flagged
    via the ``__row_status__`` column (matched / only_in_a / only_in_b).
    """
    merged = pd.merge(
        df_a.add_suffix("__A"),
        df_b.add_suffix("__B"),
        left_on=f"{key_col}__A",
        right_on=f"{key_col}__B",
        how="outer",
    )

    cols_a = list(df_a.columns)
    cols_b = list(df_b.columns)

    def _extract(cols, suffix):
        frame = pd.DataFrame(index=merged.index)
        for col in cols:
            src = f"{col}{suffix}"
            frame[col] = merged[src].fillna("") if src in merged.columns else ""
        return frame

    out_a = _extract(cols_a, "__A")
    out_b = _extract(cols_b, "__B")

    status = _compute_status(merged, key_col)
    out_a[STATUS_COL] = status
    out_b[STATUS_COL] = status

    # Sort by the key for a deterministic display order
    sort_key = out_a[key_col] if key_col in out_a.columns else out_a.index
    order = sort_key.argsort()
    out_a = out_a.iloc[order].reset_index(drop=True)
    out_b = out_b.iloc[order].reset_index(drop=True)

    return out_a, out_b


def align_by_composite_key(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    key_cols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Align using two or more columns as a composite primary key (exact match).

    The key columns are concatenated with '|||' into a single temporary column,
    which is then used for the outer merge.  The temporary column is removed
    from both output DataFrames.

    Parameters
    ----------
    df_a, df_b : pd.DataFrame
        Already column-mapped DataFrames (same column set).
    key_cols   : list[str]
        Two or more column names whose combined value uniquely identifies a row.

    Returns
    -------
    aligned_a, aligned_b : pd.DataFrame
        Aligned frames with ``__row_status__`` column.
    """
    if len(key_cols) < 1:
        raise ValueError("key_cols must contain at least one column name.")

    if len(key_cols) == 1:
        # Delegate to single-key logic for cleanliness
        return align_by_key(df_a, df_b, key_col=key_cols[0])

    # ── Build composite key column ─────────────────────────────────────────
    df_a_aug = df_a.copy()
    df_b_aug = df_b.copy()

    df_a_aug[_COMPOSITE_KEY_COL] = _build_composite_key(df_a, key_cols)
    df_b_aug[_COMPOSITE_KEY_COL] = _build_composite_key(df_b, key_cols)

    # ── Outer merge on the composite key ─────────────────────────────────
    out_a, out_b = align_by_key(df_a_aug, df_b_aug, key_col=_COMPOSITE_KEY_COL)

    # ── Strip the helper column from outputs ──────────────────────────────
    out_a = out_a.drop(columns=[_COMPOSITE_KEY_COL], errors="ignore")
    out_b = out_b.drop(columns=[_COMPOSITE_KEY_COL], errors="ignore")

    return out_a, out_b


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_composite_key(df: pd.DataFrame, key_cols: list[str]) -> pd.Series:
    """Concatenate several columns into a single key string."""
    return (
        df[key_cols]
        .fillna("")
        .astype(str)
        .apply(lambda row: _SEP.join(row), axis=1)
    )


def _pad_to_length(df: pd.DataFrame, target_len: int) -> pd.DataFrame:
    """Append empty-string rows until ``df`` has exactly ``target_len`` rows."""
    shortage = target_len - len(df)
    if shortage <= 0:
        return df.copy()
    empty = pd.DataFrame(
        [[""] * len(df.columns)] * shortage,
        columns=df.columns,
    )
    return pd.concat([df, empty], ignore_index=True)


def _compute_status(merged: pd.DataFrame, key_col: str) -> pd.Series:
    """
    Derive per-row status from an outer-merged DataFrame.

    - only_in_a : B-side key is NaN
    - only_in_b : A-side key is NaN
    - matched   : both sides present
    """
    a_key = merged.get(f"{key_col}__A")
    b_key = merged.get(f"{key_col}__B")

    conditions = [b_key.isna(), a_key.isna()]
    choices    = ["only_in_a", "only_in_b"]

    return pd.Series(
        np.select(conditions, choices, default="matched"),
        index=merged.index,
    )
