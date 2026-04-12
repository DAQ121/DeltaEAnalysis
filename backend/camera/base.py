import numpy as np
from abc import ABC, abstractmethod


class BaseCameraSource(ABC):
    """相机源抽象基类，所有相机实现必须继承此接口"""

    @abstractmethod
    def open(self) -> bool:
        """初始化并打开相机/视频源，返回是否成功"""
        ...

    @abstractmethod
    def read_frame(self) -> np.ndarray | None:
        """取最新帧（BGR numpy 数组），无帧时返回 None"""
        ...

    @abstractmethod
    def close(self) -> None:
        """释放资源"""
        ...

    @abstractmethod
    def is_opened(self) -> bool:
        """当前是否处于打开状态"""
        ...
