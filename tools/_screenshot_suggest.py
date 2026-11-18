"""Heuristic starting rectangles for cropping an SSMS result screenshot.

Used only by tools/crop_tool.py to pre-fill the two crop boxes (query pane, results
pane) that the person then adjusts by hand. Not part of the report build.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

RESULTS_TOP_FRAC = 0.4899
STATUS_TOP_FRAC = 0.9663
TOP_MARGIN = 15
BOTTOM_MARGIN = 22
MIN_RESULTS_HEIGHT = 70
BORDER_MARGIN = 28
SCROLLBAR_MARGIN = 25
RIGHT_MARGIN = 30


def _has_content(row, thresh=235):
    return bool((row.min(axis=1) < thresh).any())


def _last_content_col(block, thresh=235):
    colmask = (block.min(axis=2) < thresh).any(axis=0)
    idx = np.where(colmask)[0]
    return int(idx.max()) if len(idx) else -1


def _find_left_border(arr):
    h, w, _ = arr.shape
    mn = arr.min(axis=2)
    shadow = (mn >= 195) & (mn <= 245)
    frac = shadow.mean(axis=0)
    lo, hi = int(0.15 * w), int(0.42 * w)
    return lo + int(np.argmax(frac[lo:hi])) + BORDER_MARGIN


def suggest(path) -> dict:
    """Returns {width, height, query: {left,top,right,bottom}, results: {left,top,right,bottom}}."""
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im)
    h, w, _ = arr.shape

    left = _find_left_border(arr)
    results_top = int(round(RESULTS_TOP_FRAC * h))
    status_top = int(round(STATUS_TOP_FRAC * h))

    region = arr[:, left:max(left + 1, w - SCROLLBAR_MARGIN)]

    last_code_y = 0
    for y in range(results_top - 1, -1, -1):
        if _has_content(region[y]):
            last_code_y = y
            break
    top_cut = min(results_top, max(last_code_y + TOP_MARGIN, 40))

    status_search_limit = status_top - 18
    last_data_y = results_top
    for y in range(status_search_limit - 1, results_top - 1, -1):
        if _has_content(region[y]):
            last_data_y = y
            break
    bottom_keep = min(status_top, last_data_y + BOTTOM_MARGIN)
    bottom_keep = max(bottom_keep, results_top + MIN_RESULTS_HEIGHT)

    rx1 = _last_content_col(region[0:top_cut])
    rx2 = _last_content_col(region[results_top:bottom_keep])
    rx = max(rx1, rx2)
    right = min(region.shape[1], rx + RIGHT_MARGIN) if rx >= 0 else region.shape[1]
    right = max(right, 150)

    return {
        "width": w,
        "height": h,
        "query": {"left": left, "top": 0, "right": left + right, "bottom": top_cut},
        "results": {"left": left, "top": results_top, "right": left + right, "bottom": bottom_keep},
    }
