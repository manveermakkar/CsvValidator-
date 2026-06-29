"""
components/sortable_mapper.py  — v6 Pure Native Streamlit Column Mapper
------------------------------------------------------------------------
A fully native Streamlit column-mapping UI with NO custom components / iframes.

Features
--------
* Two searchable multiselects to pick which columns to include from each file
* A live mapping table showing  File-A col  ↔  File-B col  for every pair
* Each row has a dropdown to re-assign the File-B column (drag-style editing)
* Move-Up / Move-Down buttons to reorder pairs
* Quick-action buttons: Auto-match by name, Reset to default order, Reverse B
"""

from __future__ import annotations
import streamlit as st
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def render_sortable_mapper(
    cols_a: list[str],
    cols_b: list[str],
    name_a: str,
    name_b: str,
    key_prefix: str = "mapper",
) -> tuple[list[str], list[str]]:
    """
    Render the column-mapping editor.

    Returns
    -------
    selected_a, selected_b : equal-length lists that define the comparison pairs
    """
    _inject_css()
    _init_state(cols_a, cols_b, key_prefix)

    # ── Section: Column Selection ────────────────────────────────────────────
    with st.expander("📂 **Column Selection** — choose which columns to include", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div class="mapper-hdr">📄 {name_a}</div>', unsafe_allow_html=True)
            st.caption("Select columns to compare from this file")
            st.multiselect(
                label=f"Columns from {name_a}",
                options=cols_a,
                key=f"{key_prefix}_ms_a",
                label_visibility="collapsed",
                placeholder=f"Search & select columns from {name_a}…",
            )
        with c2:
            st.markdown(f'<div class="mapper-hdr">📄 {name_b}</div>', unsafe_allow_html=True)
            st.caption("Select columns to compare from this file")
            st.multiselect(
                label=f"Columns from {name_b}",
                options=cols_b,
                key=f"{key_prefix}_ms_b",
                label_visibility="collapsed",
                placeholder=f"Search & select columns from {name_b}…",
            )

    # Sync multiselect → ordered lists
    _sync_ordered(key_prefix, "a", cols_a)
    _sync_ordered(key_prefix, "b", cols_b)

    ordered_a: list[str] = st.session_state[f"{key_prefix}_ord_a"]
    ordered_b: list[str] = st.session_state[f"{key_prefix}_ord_b"]

    if not ordered_a and not ordered_b:
        st.info("ℹ️ Open **Column Selection** above and pick at least one column from each file.")
        return [], []

    n_a, n_b = len(ordered_a), len(ordered_b)
    pair_len = min(n_a, n_b)

    if n_a != n_b:
        st.warning(
            f"⚠️ **{n_a}** column(s) selected from **{name_a}** vs "
            f"**{n_b}** from **{name_b}** — select equal counts. "
            f"Showing first **{pair_len}** pairs below."
        )

    if pair_len == 0:
        return [], []

    pair_a = ordered_a[:pair_len]
    # B mapping is stored per-row in session state
    _init_b_mapping(key_prefix, pair_a, ordered_b[:pair_len], cols_b)

    # ── Section: Mapping Table ───────────────────────────────────────────────
    st.markdown('<div class="map-section-title">🔗 Column Mapping</div>', unsafe_allow_html=True)
    st.caption(
        "Each row is one comparison pair. "
        "Use the **dropdown** in the right column to change which File B column is compared."
    )

    # Quick action buttons
    qa1, qa2, qa3, _spacer = st.columns([1, 1, 1, 3])
    with qa1:
        if st.button("🪄 Auto-match names", key=f"{key_prefix}_automatch",
                     help="Try to match File A and File B columns by name (case-insensitive)"):
            _auto_match(key_prefix, pair_a, cols_b)
            st.rerun()
    with qa2:
        if st.button("🔄 Reset order", key=f"{key_prefix}_reset",
                     help="Reset File B mapping to its original selected order"):
            _reset_mapping(key_prefix, pair_a, ordered_b[:pair_len])
            st.rerun()
    with qa3:
        if st.button("⇅ Flip B order", key=f"{key_prefix}_flip",
                     help="Reverse the current File B mapping order"):
            _flip_b(key_prefix, pair_a)
            st.rerun()

    st.markdown("")  # spacer

    # ── Render the mapping rows ──────────────────────────────────────────────
    final_a: list[str] = []
    final_b: list[str] = []

    for i, col_a in enumerate(pair_a):
        sk = f"{key_prefix}_bmap_{i}"          # selectbox key for row i

        row_cols = st.columns([0.05, 0.37, 0.08, 0.5])

        # Index badge
        with row_cols[0]:
            st.markdown(
                f'<div class="row-idx">{i + 1}</div>',
                unsafe_allow_html=True,
            )

        # File A column — st.write renders with correct theme text color always
        with row_cols[1]:
            st.write(f"🔷 **{col_a}**")

        # Arrow
        with row_cols[2]:
            st.markdown('<div class="map-arrow">↔</div>', unsafe_allow_html=True)

        # File B column (editable dropdown)
        with row_cols[3]:
            current_b = st.session_state.get(sk, cols_b[i] if i < len(cols_b) else cols_b[0])
            # Ensure current value is valid
            if current_b not in cols_b:
                current_b = cols_b[0]
            chosen_b = st.selectbox(
                label=f"File B col for row {i+1}",
                options=cols_b,
                index=cols_b.index(current_b),
                key=sk,
                label_visibility="collapsed",
            )

        final_a.append(col_a)
        final_b.append(chosen_b)

    # ── Summary strip ────────────────────────────────────────────────────────
    st.markdown("")
    _render_summary_strip(final_a, final_b, name_a, name_b)

    # Persist A order
    st.session_state[f"{key_prefix}_ord_a"] = final_a + ordered_a[pair_len:]

    return final_a, final_b


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _init_state(cols_a: list[str], cols_b: list[str], pfx: str) -> None:
    if f"{pfx}_ms_a" not in st.session_state:
        st.session_state[f"{pfx}_ms_a"] = list(cols_a)
    if f"{pfx}_ms_b" not in st.session_state:
        st.session_state[f"{pfx}_ms_b"] = list(cols_b)
    if f"{pfx}_ord_a" not in st.session_state:
        st.session_state[f"{pfx}_ord_a"] = []
    if f"{pfx}_ord_b" not in st.session_state:
        st.session_state[f"{pfx}_ord_b"] = []


def _sync_ordered(pfx: str, side: str, all_cols: list[str]) -> None:
    ms_val: list[str]  = st.session_state.get(f"{pfx}_ms_{side}", [])
    ordered: list[str] = st.session_state.get(f"{pfx}_ord_{side}", [])
    reconciled = (
        [c for c in ordered if c in ms_val]
        + [c for c in ms_val if c not in ordered]
    )
    st.session_state[f"{pfx}_ord_{side}"] = reconciled


def _init_b_mapping(pfx: str, pair_a: list[str], pair_b: list[str], cols_b: list[str]) -> None:
    """Initialise per-row B-column selectbox keys if not yet set."""
    for i, col_a in enumerate(pair_a):
        sk = f"{pfx}_bmap_{i}"
        if sk not in st.session_state:
            st.session_state[sk] = pair_b[i] if i < len(pair_b) else cols_b[0]


def _auto_match(pfx: str, pair_a: list[str], cols_b: list[str]) -> None:
    b_lower = {c.lower(): c for c in cols_b}
    for i, col_a in enumerate(pair_a):
        sk = f"{pfx}_bmap_{i}"
        matched = b_lower.get(col_a.lower())
        if matched:
            st.session_state[sk] = matched


def _reset_mapping(pfx: str, pair_a: list[str], orig_b: list[str]) -> None:
    for i in range(len(pair_a)):
        sk = f"{pfx}_bmap_{i}"
        st.session_state[sk] = orig_b[i] if i < len(orig_b) else orig_b[0]


def _flip_b(pfx: str, pair_a: list[str]) -> None:
    n = len(pair_a)
    current = [st.session_state.get(f"{pfx}_bmap_{i}") for i in range(n)]
    flipped = list(reversed(current))
    for i in range(n):
        st.session_state[f"{pfx}_bmap_{i}"] = flipped[i]


def _swap_rows(pfx: str, pair_a: list[str], i: int, j: int) -> None:
    """Swap the File-A order and the B-mapping for rows i and j."""
    ordered_a = st.session_state[f"{pfx}_ord_a"]
    # Swap A order
    ordered_a[i], ordered_a[j] = ordered_a[j], ordered_a[i]
    st.session_state[f"{pfx}_ord_a"] = ordered_a
    # Swap B mapping keys
    ski, skj = f"{pfx}_bmap_{i}", f"{pfx}_bmap_{j}"
    vi = st.session_state.get(ski)
    vj = st.session_state.get(skj)
    st.session_state[ski] = vj
    st.session_state[skj] = vi


def _render_summary_strip(
    final_a: list[str], final_b: list[str], name_a: str, name_b: str
) -> None:
    pairs_html = "".join(
        f'<span class="sum-pair">'
        f'<span class="sum-a">{a}</span>'
        f'<span class="sum-arrow">↔</span>'
        f'<span class="sum-b">{b}</span>'
        f'</span>'
        for a, b in zip(final_a, final_b)
    )
    st.markdown(
        f'<div class="summary-strip">'
        f'<span class="sum-label">Active mapping ({len(final_a)} pairs):</span> '
        f'{pairs_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        /* ── Multiselect chips ── */
        [data-baseweb="tag"] {
            background-color: #1a3a6e !important;
            border-radius: 6px !important;
        }
        [data-baseweb="tag"] span { color: #fff !important; font-weight: 500 !important; }

        /* ── Disabled selectbox (File A column labels) — force dark appearance ── */
        div[aria-disabled="true"] [data-baseweb="select"] > div:first-child,
        div[aria-disabled="true"] [data-baseweb="select"],
        [data-baseweb="select"][aria-disabled="true"] > div {
            background-color: #172a47 !important;
            border-color: #2d4f7c !important;
            border-left: 4px solid #3b82f6 !important;
        }
        /* Make the text inside disabled selectbox visible */
        div[aria-disabled="true"] [data-baseweb="select"] [data-baseweb="select"] span,
        div[aria-disabled="true"] span[data-testid],
        div[aria-disabled="true"] [class*="placeholder"],
        div[aria-disabled="true"] [class*="singleValue"],
        div[aria-disabled="true"] div[class*="valueContainer"] span {
            color: #93c5fd !important;
            font-weight: 600 !important;
        }
        /* Catch-all: all spans/divs inside any disabled widget */
        [disabled] + * span,
        div[aria-disabled="true"] span {
            color: #93c5fd !important;
        }


        /* ── Section titles ── */
        .mapper-hdr {
            font-size: 0.82rem; font-weight: 700; color: #6b8cad;
            text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 4px;
        }
        .map-section-title {
            font-size: 1rem; font-weight: 700; color: #93c5fd;
            margin: 16px 0 4px 0;
        }

        /* ── Row index badge ── */
        .row-idx {
            width: 28px; height: 28px; border-radius: 50%;
            background: #1e3a5f; color: #93c5fd;
            border: 1.5px solid #3b82f6;
            font-size: 11px; font-weight: 700;
            display: flex; align-items: center; justify-content: center;
            margin-top: 8px;
        }

        /* ── Column A label (disabled text_input) ── */
        .col-a-label {
            display: flex; align-items: center;
            padding: 10px 12px; border-radius: 8px;
            border: 1.5px solid #2d4f7c;
            border-left: 4px solid #60a5fa;
            background: #1e3a5f;
            font-size: 13.5px; font-weight: 600; color: #e8f2ff;
            min-height: 40px; margin-top: 2px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .badge-a-pill {
            display: inline-block;
            background: #3b82f6; color: #fff;
            font-size: 10px; font-weight: 800;
            padding: 2px 6px; border-radius: 4px;
            margin-right: 6px; flex-shrink: 0;
        }
        /* Style the disabled st.text_input used for File A labels */
        input[disabled] {
            border-left: 4px solid #3b82f6 !important;
            background: #1e3a5f !important;
            color: #93c5fd !important;
            font-weight: 600 !important;
            opacity: 1 !important;
            cursor: default !important;
        }

        /* ── Arrow ── */
        .map-arrow {
            font-size: 18px; font-weight: 700; color: #60a5fa;
            text-align: center; margin-top: 8px; user-select: none;
        }

        /* ── Summary strip ── */
        .summary-strip {
            background: rgba(30, 58, 95, 0.5);
            border: 1px solid #2d4f7c; border-radius: 10px;
            padding: 10px 16px; margin-top: 8px;
            font-size: 12.5px; line-height: 1.8;
            display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
        }
        .sum-label { font-weight: 700; color: #93c5fd; margin-right: 4px; }
        .sum-pair {
            display: inline-flex; align-items: center; gap: 4px;
            background: rgba(59, 130, 246, 0.15); border: 1px solid #3b82f6;
            border-radius: 6px; padding: 2px 8px;
        }
        .sum-a { color: #93c5fd; font-weight: 600; }
        .sum-b { color: #60a5fa; font-weight: 600; }
        .sum-arrow { color: #4b6899; font-weight: 700; }
        </style>
        """,
        unsafe_allow_html=True,
    )
