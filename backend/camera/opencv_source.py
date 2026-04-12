import cv2
import time
import threading
import numpy as np

from .base import BaseCameraSource


class OpenCVSource(BaseCameraSource):
    """基于 cv2.VideoCapture 的视频源，支持本地文件和 RTSP URL"""

    def __init__(self, source: str):
        self.source = source
        self._cap = None
        self._opened = False
        self._latest_frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def open(self) -> bool:
        self._cap = cv2.VideoCapture(self.source)
        if not self._cap.isOpened():
            self._opened = False
            return False
        self._opened = True
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return True

    def read_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def close(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()
        self._opened = False
        self._latest_frame = None

    def is_opened(self) -> bool:
        return self._opened

    def _read_loop(self):
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                # 本地视频读到末尾，循环播放
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            with self._lock:
                self._latest_frame = frame
            time.sleep(0.033)  # ~30fps
