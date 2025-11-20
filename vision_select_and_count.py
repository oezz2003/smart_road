"""ROI selection + car counting utilities for the Smart Road demo."""

from __future__ import annotations

import json
import math
import os
import queue
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Tuple

import cv2
import numpy as np

CAM_INDEX = 0
FRAME_W = 1280
FRAME_H = 720
MIN_AREA = 500
LINE_POS = 0.6
BAND_FRAC = 0.08
ERODE_ITER = 1
DILATE_ITER = 2
PRINT_EVERY = 1.0
MAX_TRACK_DIST = 40.0
TRACK_TTL = 0.8
ROI_CFG = "roi_config.json"

CountsDict = Dict[str, int]

_counts_queue: "queue.Queue[CountsDict]" = queue.Queue(maxsize=1)


def get_counts_queue() -> "queue.Queue[CountsDict]":
    """Return a queue that always holds the latest counts snapshot."""

    return _counts_queue


@dataclass
class Track:
    x: float
    y: float
    pos: float
    counted: bool
    last_seen: float


@dataclass
class ROIState:
    name: str
    rect: Tuple[int, int, int, int]
    orient_x: bool
    line_px: int
    band_px: int
    subtractor: cv2.BackgroundSubtractor
    tracks: Dict[int, Track] = field(default_factory=dict)
    next_id: int = 0


def _select_or_load_rois(frame: np.ndarray) -> Dict[str, Tuple[int, int, int, int]]:
    if os.path.exists(ROI_CFG):
        with open(ROI_CFG, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {name: tuple(map(int, rect)) for name, rect in data.items()}

    print("Select ROIs in order N, S, E, W (ENTER to confirm each, ESC to finish).")
    rois = cv2.selectROIs("Select 4 ROIs", frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow("Select 4 ROIs")
    if len(rois) != 4:
        raise RuntimeError("Need exactly 4 ROIs.")
    mapping = {
        "N": tuple(map(int, rois[0])),
        "S": tuple(map(int, rois[1])),
        "E": tuple(map(int, rois[2])),
        "W": tuple(map(int, rois[3])),
    }
    with open(ROI_CFG, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, indent=2)
    print(f"Saved ROI config to {ROI_CFG}.")
    return mapping


def _make_state(name: str, rect: Tuple[int, int, int, int]) -> ROIState:
    x, y, w, h = rect
    orient_x = name in {"E", "W"}
    extent = w if orient_x else h
    line_px = int(extent * LINE_POS)
    band_px = max(2, int(min(w, h) * BAND_FRAC))
    subtractor = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=25, detectShadows=False
    )
    return ROIState(name=name, rect=(x, y, w, h), orient_x=orient_x, line_px=line_px, band_px=band_px, subtractor=subtractor)


def _detect(state: ROIState, roi_frame: np.ndarray) -> List[Tuple[float, float]]:
    gray = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
    mask = state.subtractor.apply(gray)
    mask = cv2.erode(mask, None, iterations=ERODE_ITER)
    mask = cv2.dilate(mask, None, iterations=DILATE_ITER)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detections: List[Tuple[float, float]] = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < MIN_AREA:
            continue
        x, y, w, h = cv2.boundingRect(c)
        detections.append((x + w / 2.0, y + h / 2.0))
    return detections


def _assign_track(state: ROIState, cx: float, cy: float) -> int:
    best = -1
    best_dist = float("inf")
    for track_id, track in state.tracks.items():
        dist = math.hypot(track.x - cx, track.y - cy)
        if dist < best_dist:
            best_dist = dist
            best = track_id
    if best_dist <= MAX_TRACK_DIST:
        return best
    return -1


def _update_tracks(state: ROIState, detections: Iterable[Tuple[float, float]], now: float) -> int:
    crossings = 0
    line = state.line_px
    band = state.band_px

    for cx, cy in detections:
        track_id = _assign_track(state, cx, cy)
        if track_id == -1:
            track_id = state.next_id
            state.next_id += 1
            prev_pos = cy if not state.orient_x else cx
        else:
            prev_pos = state.tracks[track_id].pos
        pos = cy if not state.orient_x else cx
        counted = state.tracks.get(track_id, Track(cx, cy, pos, False, now)).counted
        if not counted:
            min_pos = min(prev_pos, pos)
            max_pos = max(prev_pos, pos)
            if min_pos <= line - band and max_pos >= line + band:
                counted = True
                crossings += 1
        state.tracks[track_id] = Track(x=cx, y=cy, pos=pos, counted=counted, last_seen=now)

    # Remove stale tracks
    expired = [tid for tid, track in state.tracks.items() if now - track.last_seen > TRACK_TTL]
    for tid in expired:
        state.tracks.pop(tid, None)
    return crossings


def _emit_counts(counts: CountsDict) -> None:
    try:
        _counts_queue.put_nowait(counts.copy())
    except queue.Full:
        try:
            _counts_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            _counts_queue.put_nowait(counts.copy())
        except queue.Full:
            pass


def count_stream() -> Iterator[CountsDict]:
    """Yield car counts as dictionaries keyed by N, S, E, W."""

    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open camera index {CAM_INDEX}.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)

    ok, frame = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError("Unable to read initial frame.")

    rois = _select_or_load_rois(frame)
    states = {name: _make_state(name, rect) for name, rect in rois.items()}
    window_counts: CountsDict = {"N": 0, "S": 0, "E": 0, "W": 0}
    last_emit = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            now = time.time()
            for name, state in states.items():
                x, y, w, h = state.rect
                roi_frame = frame[y : y + h, x : x + w]
                if roi_frame.size == 0:
                    continue
                detections = _detect(state, roi_frame)
                inc = _update_tracks(state, detections, now)
                if inc:
                    window_counts[name] += inc
            if now - last_emit >= PRINT_EVERY:
                _emit_counts(window_counts)
                print(f"Counts @ {time.strftime('%H:%M:%S')}: {window_counts}")
                yield window_counts.copy()
                window_counts = {k: 0 for k in window_counts}
                last_emit = now
    finally:
        cap.release()


def run_viewer() -> None:
    """Debug helper that overlays ROIs and live counts."""

    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open camera index {CAM_INDEX}.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)

    ok, frame = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError("Unable to read initial frame.")

    rois = _select_or_load_rois(frame)
    states = {name: _make_state(name, rect) for name, rect in rois.items()}
    counts = {"N": 0, "S": 0, "E": 0, "W": 0}
    last_emit = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            display = frame.copy()
            now = time.time()
            for name, state in states.items():
                x, y, w, h = state.rect
                roi_frame = frame[y : y + h, x : x + w]
                cv2.rectangle(display, (x, y), (x + w, y + h), (0, 255, 0), 2)
                detections = _detect(state, roi_frame)
                inc = _update_tracks(state, detections, now)
                if inc:
                    counts[name] += inc
                cv2.putText(
                    display,
                    f"{name}: {counts[name]}",
                    (x + 5, y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                )
            if now - last_emit >= PRINT_EVERY:
                counts = {k: 0 for k in counts}
                last_emit = now
            cv2.imshow("Smart Road - Counts", display)
            if cv2.waitKey(1) & 0xFF == 27:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    run_viewer()
