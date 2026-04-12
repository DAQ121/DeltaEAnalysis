import os
import glob
import time
import cv2
import numpy as np

from .base import BaseCameraSource


class MockCameraSource(BaseCameraSource):
    """从本地图片目录循环读取，模拟相机抓图（用于开发测试）"""

    def __init__(self, image_dir: str = None, frame_interval: float = 1.0):
        """
        Args:
            image_dir: 图片目录路径，默认使用 mediamtx/test-img/
            frame_interval: 图片切换间隔（秒），控制多久换下一张图
        """
        if image_dir is None:
            image_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'mediamtx', 'test-img')
        self.image_dir = os.path.abspath(image_dir)
        self.frame_interval = max(0.1, frame_interval)
        self._images = []
        self._index = 0
        self._opened = False
        self._last_switch_time = 0
        self._current_frame = None

    def open(self) -> bool:
        patterns = ['*.jpg', '*.jpeg', '*.png', '*.bmp']
        files = []
        for pat in patterns:
            files.extend(glob.glob(os.path.join(self.image_dir, pat)))
        self._images = sorted(files)
        if not self._images:
            print(f"[MockCameraSource] 未找到图片: {self.image_dir}")
            return False
        self._opened = True
        self._index = 0
        self._current_frame = cv2.imread(self._images[0])
        self._last_switch_time = time.time()
        print(f"[MockCameraSource] 已加载 {len(self._images)} 张测试图片，切换间隔 {self.frame_interval}s")
        return True

    def read_frame(self) -> np.ndarray | None:
        if not self._opened or not self._images:
            return None
        now = time.time()
        if now - self._last_switch_time >= self.frame_interval:
            self._index = (self._index + 1) % len(self._images)
            self._current_frame = cv2.imread(self._images[self._index])
            self._last_switch_time = now
        return self._current_frame

    def close(self) -> None:
        self._opened = False
        self._index = 0

    def is_opened(self) -> bool:
        return self._opened
