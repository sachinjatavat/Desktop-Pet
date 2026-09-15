"""
video_utils.py
Frame loading + green-screen (chroma key) removal.

Works on:
  - .png / .webp with existing alpha channel -> used as-is
  - .gif -> played frame by frame via QMovie (no chroma key needed,
           since GIFs used for this purpose are usually already transparent)
  - .mp4 / .mov / .webm / .avi with a green screen -> chroma keyed
           frame-by-frame into a transparent QImage
"""
import os
import cv2
import numpy as np
from PyQt5.QtGui import QImage

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
STATIC_IMAGE_EXTS = {".png", ".webp"}
GIF_EXTS = {".gif"}


def media_kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in GIF_EXTS:
        return "gif"
    if ext in STATIC_IMAGE_EXTS:
        return "image"
    return "unknown"


def bgr_frame_to_qimage(frame_bgr, lower, upper) -> QImage:
    """
    Removes a green-screen background from a raw OpenCV BGR frame and
    returns a QImage with a proper alpha channel.
    `lower`/`upper` are HSV bounds, e.g. [35,40,40] / [90,255,255].
    """
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))

    # Soften the mask edges a touch so the cutout doesn't look jagged
    mask = cv2.GaussianBlur(mask, (3, 3), 0)

    alpha = 255 - mask
    b, g, r = cv2.split(frame_bgr)

    # QImage.Format_ARGB32 stores bytes as B,G,R,A in memory (little-endian),
    # so merging in this exact order gives a correct image without a manual
    # byte-swap step.
    bgra = cv2.merge([b, g, r, alpha]).astype(np.uint8)
    bgra = np.ascontiguousarray(bgra)

    h, w = bgra.shape[:2]
    qimg = QImage(bgra.data, w, h, bgra.strides[0], QImage.Format_ARGB32)
    return qimg.copy()  # copy so the buffer isn't freed from under Qt


class VideoSpriteReader:
    """Thin wrapper around cv2.VideoCapture that loops forever."""

    def __init__(self, path):
        self.path = path
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise IOError(f"Could not open video: {path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 24.0

    def read_next_frame(self):
        ok, frame = self.cap.read()
        if not ok:
            # loop back to the start
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
            if not ok:
                return None
        return frame

    def release(self):
        self.cap.release()
