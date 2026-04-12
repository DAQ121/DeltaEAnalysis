import sys
import os
import numpy as np

from .base import BaseCameraSource

# 尝试导入 MVS SDK，未安装时标记为不可用
_MVS_AVAILABLE = False
try:
    # MvImport 目录可能在 backend/camera/MvImport/ 或 MVS 安装目录中
    _mv_import_path = os.path.join(os.path.dirname(__file__), 'MvImport')
    if os.path.isdir(_mv_import_path):
        sys.path.insert(0, _mv_import_path)

    from MvCameraControl_class import MvCamera, MV_CC_DEVICE_INFO_LIST
    from CameraParams_header import (
        MV_GIGE_DEVICE, MV_ACCESS_Exclusive,
        MV_TRIGGER_SOURCE_SOFTWARE,
    )
    from PixelType_header import PixelType_Gvsp_BGR8_Packed, PixelType_Gvsp_Mono8
    from MvErrorDefine_const import MV_OK
    _MVS_AVAILABLE = True
except ImportError:
    pass


def is_sdk_available() -> bool:
    return _MVS_AVAILABLE


def enumerate_devices() -> list[dict]:
    """枚举网络中所有海康 GigE Vision 相机，返回设备信息列表"""
    if not _MVS_AVAILABLE:
        return []

    device_list = MV_CC_DEVICE_INFO_LIST()
    ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE, device_list)
    if ret != MV_OK:
        return []

    devices = []
    for i in range(device_list.nDeviceNum):
        info = device_list.pDeviceInfo[i]
        gige_info = info.SpecialInfo.stGigEInfo
        ip_bytes = gige_info.nCurrentIp
        ip = f"{(ip_bytes >> 24) & 0xFF}.{(ip_bytes >> 16) & 0xFF}.{(ip_bytes >> 8) & 0xFF}.{ip_bytes & 0xFF}"
        name = gige_info.chUserDefinedName.decode('utf-8', errors='ignore').strip('\x00')
        model = gige_info.chModelName.decode('utf-8', errors='ignore').strip('\x00')
        serial = gige_info.chSerialNumber.decode('utf-8', errors='ignore').strip('\x00')
        devices.append({
            'index': i,
            'ip': ip,
            'name': name or f'Camera_{i}',
            'model': model,
            'serial': serial,
        })
    return devices


class HikVisionSource(BaseCameraSource):
    """通过海康 MVS SDK 接入 GigE Vision 工业相机"""

    def __init__(self, device_index: int = 0, exposure_time: float = 10000):
        if not _MVS_AVAILABLE:
            raise ImportError(
                "MVS SDK 未安装。请安装海康 MVS 客户端，并将 MvImport/ 目录复制到 backend/camera/ 下。"
                "\nWindows: C:\\Program Files (x86)\\MVS\\Development\\Samples\\Python\\MvImport\\"
                "\nLinux: /opt/MVS/Samples/64/Python/MvImport/"
            )
        self.device_index = device_index
        self.exposure_time = exposure_time
        self._cam = MvCamera()
        self._opened = False

    def open(self) -> bool:
        # 1. 枚举 GigE 设备
        device_list = MV_CC_DEVICE_INFO_LIST()
        ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE, device_list)
        if ret != MV_OK:
            print(f"[HikVision] 枚举设备失败, ret=0x{ret:08X}")
            return False

        if device_list.nDeviceNum == 0:
            print("[HikVision] 未发现任何 GigE Vision 相机")
            return False

        if self.device_index >= device_list.nDeviceNum:
            print(f"[HikVision] 设备序号 {self.device_index} 超出范围 (共 {device_list.nDeviceNum} 台)")
            return False

        # 2. 创建句柄
        device_info = device_list.pDeviceInfo[self.device_index]
        ret = self._cam.MV_CC_CreateHandle(device_info)
        if ret != MV_OK:
            print(f"[HikVision] 创建句柄失败, ret=0x{ret:08X}")
            return False

        # 3. 打开设备（独占模式）
        ret = self._cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
        if ret != MV_OK:
            print(f"[HikVision] 打开设备失败, ret=0x{ret:08X}")
            self._cam.MV_CC_DestroyHandle()
            return False

        # 4. 设置软触发模式
        self._cam.MV_CC_SetEnumValue("TriggerMode", 1)
        self._cam.MV_CC_SetEnumValue("TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE)

        # 5. 设置曝光时间
        if self.exposure_time > 0:
            self._cam.MV_CC_SetFloatValue("ExposureTime", self.exposure_time)

        # 6. 尝试设置像素格式为 BGR8（如果相机支持）
        ret = self._cam.MV_CC_SetEnumValue("PixelFormat", PixelType_Gvsp_BGR8_Packed)
        if ret != MV_OK:
            # 部分相机不支持 BGR8，后续在 read_frame 中转换
            print("[HikVision] 无法设置 BGR8 格式，将在取帧后转换")

        # 7. 关闭帧率限制（触发模式下不需要）
        self._cam.MV_CC_SetBoolValue("AcquisitionFrameRateEnable", False)

        # 8. 开始取流
        ret = self._cam.MV_CC_StartGrabbing()
        if ret != MV_OK:
            print(f"[HikVision] 开始取流失败, ret=0x{ret:08X}")
            self._cam.MV_CC_CloseDevice()
            self._cam.MV_CC_DestroyHandle()
            return False

        self._opened = True
        print(f"[HikVision] 相机已打开 (设备 #{self.device_index})")
        return True

    def read_frame(self) -> np.ndarray | None:
        if not self._opened:
            return None

        # 发送软触发
        ret = self._cam.MV_CC_SetCommandValue("TriggerSoftware")
        if ret != MV_OK:
            print(f"[HikVision] 软触发失败, ret=0x{ret:08X}")
            return None

        # 获取图像缓冲区（超时 5 秒）
        frame_out = self._cam.MV_CC_GetImageBuffer(5000)
        if frame_out is None:
            return None

        frame_info = frame_out
        if isinstance(frame_out, tuple):
            # 某些版本 SDK 返回 (data, frame_info) 元组
            frame_data, frame_info = frame_out

        try:
            # 从缓冲区构造 numpy 数组
            buf_addr = frame_info.pBufAddr
            buf_size = frame_info.stFrameInfo.nFrameLen
            width = frame_info.stFrameInfo.nWidth
            height = frame_info.stFrameInfo.nHeight
            pixel_type = frame_info.stFrameInfo.enPixelType

            # 根据像素格式转换
            if pixel_type == PixelType_Gvsp_BGR8_Packed:
                # 直接 BGR，与 OpenCV 兼容
                img = np.ctypeslib.as_array(buf_addr, shape=(height, width, 3)).copy()
            elif pixel_type == PixelType_Gvsp_Mono8:
                # 灰度图，转为 BGR
                gray = np.ctypeslib.as_array(buf_addr, shape=(height, width)).copy()
                import cv2
                img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            else:
                # 其他格式（如 Bayer），使用 SDK 转换
                img = self._convert_to_bgr(frame_info, width, height)
        finally:
            self._cam.MV_CC_FreeImageBuffer(frame_info)

        return img

    def _convert_to_bgr(self, frame_info, width, height) -> np.ndarray | None:
        """使用 SDK 的像素格式转换功能将非 BGR 格式转为 BGR"""
        import ctypes

        buf_size = width * height * 3
        dst_buf = (ctypes.c_ubyte * buf_size)()

        stConvertParam = {
            'nWidth': width,
            'nHeight': height,
            'enSrcPixelType': frame_info.stFrameInfo.enPixelType,
            'pSrcData': frame_info.pBufAddr,
            'nSrcDataLen': frame_info.stFrameInfo.nFrameLen,
            'enDstPixelType': PixelType_Gvsp_BGR8_Packed,
            'pDstBuffer': dst_buf,
            'nDstBufferSize': buf_size,
        }

        ret = self._cam.MV_CC_ConvertPixelType(stConvertParam)
        if ret != MV_OK:
            print(f"[HikVision] 像素格式转换失败, ret=0x{ret:08X}")
            return None

        return np.frombuffer(dst_buf, dtype=np.uint8).reshape(height, width, 3).copy()

    def close(self) -> None:
        if not self._opened:
            return
        self._cam.MV_CC_StopGrabbing()
        self._cam.MV_CC_CloseDevice()
        self._cam.MV_CC_DestroyHandle()
        self._opened = False
        print("[HikVision] 相机已关闭")

    def is_opened(self) -> bool:
        return self._opened
