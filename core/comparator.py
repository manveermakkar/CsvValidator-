"""
core/comparator.py
------------------
Cell-level diff engine.

Given two *already-aligned* DataFrames (same shape, same column order),
this module produces:

1. ``diff_mask``     — a boolean DataFrame (True = mismatch)
2. ``mismatch_list`` — a list of dicts, one per mismatched cell, containing:
      row_number, column_name, value_a, value_b

Numeric tolerance
-----------------
When `tolerance > 0`, columns whose values look like numbers are compared
with ``abs(a - b) <= tolerance`` instead of strict equality.  Non-numeric
or non-parseable cells always use string equality.
"""

import pandas as pd
import numpy as np
from core.aligner import STATUS_COL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    tolerance: float = 0.0,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Compare two aligned DataFrames cell by cell.

    Parameters
    ----------
    df_a, df_b : pd.DataFrame
        Must have the same shape and column order.  Should already be
        the column-mapped, aligned outputs from ``aligner``.
    tolerance : float
        If > 0, numeric cells within this absolute difference are treated
        as matching.  Set to 0 (default) for strict string equality.

    Returns
    -------
    diff_mask : pd.DataFrame[bool]
        True where cell values differ.
    mismatch_list : list[dict]
        One dict per mismatched cell with keys:
        ``row``, ``column``, ``value_a``, ``value_b``.
    """
    # Work on copies so we don't mutate the caller's data
    a = df_a.copy().reset_index(drop=True)
    b = df_b.copy().reset_index(drop=True)

    # Exclude the injected status column from comparison
    compare_cols = [c for c in a.columns if c != STATUS_COL]

    # ── Build the boolean diff mask ─────────────────────────────────────────
    diff_mask = pd.DataFrame(False, index=a.index, columns=compare_cols)

    for col in compare_cols:
        col_a = a[col]
        col_b = b[col] if col in b.columns else pd.Series([""] * len(a))

        if tolerance > 0:
            diff_mask[col] = _compare_column_with_tolerance(col_a, col_b, tolerance)
        else:
            # Simple string inequality (both DFs loaded as str)
            diff_mask[col] = col_a != col_b

    # ── Build the human-readable mismatch list ──────────────────────────────
    mismatch_list: list[dict] = []
    rows, cols = np.where(diff_mask.values)

    for row_idx, col_idx in zip(rows, cols):
        col_name = compare_cols[col_idx]
        mismatch_list.append(
            {
                "row": int(row_idx) + 1,          # 1-based for human display
                "column": col_name,
                "value_a": str(a.at[row_idx, col_name]),
                "value_b": str(b.at[row_idx, col_name]) if col_name in b.columns else "",
            }
        )

    # Sort by row then column for a predictable report order
    mismatch_list.sort(key=lambda x: (x["row"], x["column"]))

    return diff_mask, mismatch_list


def summary_stats(
    diff_mask: pd.DataFrame,
    df_a: pd.DataFrame,
) -> dict:
    """
    Return high-level statistics about the comparison.

    Returns a dict with:
    - total_rows        : int
    - total_cells       : int
    - mismatched_cells  : int
    - match_rate_pct    : float  (0–100)
    - cols_with_diffs   : list[str]
    """
    compare_cols = [c for c in diff_mask.columns if c != STATUS_COL]
    mask = diff_mask[compare_cols]

    total_rows  = len(df_a)
    total_cells = mask.size
    mismatched  = int(mask.values.sum())

    return {
        "total_rows":       total_rows,
        "total_cells":      total_cells,
        "mismatched_cells": mismatched,
        "match_rate_pct":   round(100 * (total_cells - mismatched) / total_cells, 2)
                            if total_cells > 0 else 100.0,
        "cols_with_diffs":  [c for c in compare_cols if mask[c].any()],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compare_column_with_tolerance(
    col_a: pd.Series,
    col_b: pd.Series,
    tolerance: float,
) -> pd.Series:
    """
    Return a boolean Series (True = mismatch) applying numeric tolerance
    where possible and falling back to string comparison otherwise.
    """
    result = pd.Series(False, index=col_a.index)

    for idx in col_a.index:
        val_a = col_a.at[idx]
        val_b = col_b.at[idx] if idx in col_b.index else ""

        try:
            num_a = float(val_a)
            num_b = float(val_b)
            # Numeric comparison with tolerance
            result.at[idx] = abs(num_a - num_b) > tolerance
        except (ValueError, TypeError):
            # Non-numeric: fall back to string comparison
            result.at[idx] = str(val_a) != str(val_b)

    return result
