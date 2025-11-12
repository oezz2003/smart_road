# vision_select_and_count.py
# OpenCV: select 4 ROIs (N,S,E,W), do background subtraction and line-crossing counting per ROI.

import cv2, numpy as np, time, json, os, queue, threading, math
from dataclasses import dataclass

# ---- Settings ----
CAM_INDEX = 0
FRAME_W, FRAME_H = 1280, 720
MIN_AREA = 500          # minimum contour area inside each ROI
LINE_POS = 0.6          # counting line position (fraction inside ROI)
BAND_FRAC = 0.08        # +/- band around the line (fraction of min(w,h))
PRINT_EVERY = 1.0       # seconds
ROI_CFG = "roi_config.json"

# A simple queue to publish live counts to other modules (iot_publisher will import get_counts_queue)
_counts_q = queue.Queue(maxsize=1)

def get_counts_queue():
    """Other modules import this to read the latest counts."""
    return _counts_q

@dataclass
class ROIState:
    name: str
    rect: tuple   # (x,y,w,h) in the original frame
    orient: str   # 'h' for N/S, 'v' for E/W
    bs: any       # background subtractor
    line_px: int  # computed per frame
    band_px: int
    tracks: dict
    next_id: int

def _within(val, center, band):
    return abs(val - center) <= band

def _select_or_load_rois(frame):
    if os.path.exists(ROI_CFG):
        with open(ROI_CFG, "r") as f:
            data = json.load(f)
        return {k: tuple(v) for k, v in data.items()}

    print("Select 4 ROIs in order: N, S, E, W (drag mouse, ENTER after each, ESC to finish)")
    rects = cv2.selectROIs("Select 4 ROIs", frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow("Select 4 ROIs")
    if len(rects) != 4:
        raise RuntimeError("You must select exactly 4 ROIs (N,S,E,W).")
    rois = {"N": tuple(map(int, rects[0])),
            "S": tuple(map(int, rects[1])),
            "E": tuple(map(int, rects[2])),
            "W": tuple(map(int, rects[3]))}
    with open(ROI_CFG, "w") as f:
        json.dump(rois, f, indent=2)
    print("
