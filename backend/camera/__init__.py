from .base import BaseCameraSource
from .opencv_source import OpenCVSource
from .mock_source import MockCameraSource

__all__ = ['BaseCameraSource', 'OpenCVSource', 'MockCameraSource']

# HikVisionSource 仅在 MVS SDK 可用时导出
try:
    from .hikvision_source import HikVisionSource
    __all__.append('HikVisionSource')
except ImportError:
    HikVisionSource = None
