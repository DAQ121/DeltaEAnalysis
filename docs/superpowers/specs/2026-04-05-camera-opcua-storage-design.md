# 设计文档：海康相机接入 + OPC UA 触发 + 数据持久化

**日期**：2026-04-05  
**状态**：已批准，待实现

---

## 背景与目标

当前系统的三个核心缺口：

1. **相机接入**：`stream_processor.py` 使用 `cv2.VideoCapture()`，无法接入海康 MV-CU060-10GC（GigE Vision，不支持 RTSP），工厂场景无法落地。
2. **触发机制**：现有定时抓帧不满足产线需求，需要读取 PLC 的 OPC UA 节点信号来驱动抓图。
3. **数据持久化**：所有过程数据存在内存 `sessions` 字典中，重启即丢失，无法追溯历史。

**部署场景**：工厂产线（Windows 工控机 + 海康 GigE Vision 相机 + OPC UA PLC，离线）和实验室（手动上传单图 / 本地视频文件，联网）两种场景均需支持。

---

## 架构概览

在现有三文件（`app.py` / `stream_processor.py` / `image_processor.py`）基础上新增：

```
backend/
  camera/
    __init__.py
    base.py              # BaseCameraSource 抽象基类
    opencv_source.py     # 封装现有 cv2.VideoCapture 逻辑
    hikvision_source.py  # MVS SDK 接入
  opcua_trigger.py       # OPC UA 触发监听
  storage.py             # SQLite + 图片归档 + CSV 导出
  data/
    shijue.db            # SQLite 数据库文件
    images/              # 结果图片归档目录
frontend/
  js/history.js          # 历史记录 Tab 逻辑（新增）
  index.html             # 新增第三个 Tab
```

`image_processor.py` 不做任何修改。

---

## 第一部分：相机适配层

### BaseCameraSource（camera/base.py）

所有相机源实现的统一接口：

```python
class BaseCameraSource:
    def open(self) -> bool: ...          # 初始化并打开相机，返回是否成功
    def read_frame(self) -> np.ndarray | None: ...  # 取最新帧，无帧返回 None
    def close(self) -> None: ...         # 释放资源
    def is_opened(self) -> bool: ...     # 当前是否处于打开状态
```

### OpenCVSource（camera/opencv_source.py）

将 `stream_processor.py` 中现有的 `cv2.VideoCapture` 逻辑迁移至此，行为不变：
- 支持本地视频文件路径和 RTSP URL
- 本地文件读到末尾后循环播放
- 后台线程持续读帧，`read_frame()` 返回最新帧

### HikVisionSource（camera/hikvision_source.py）

通过海康 MVS SDK 接入 GigE Vision 相机：

- `open()`：`MvCamera.MV_CC_EnumDevices()` 枚举设备，按配置的序号或 IP 选取目标相机，`MV_CC_OpenDevice()` 打开，设置为**软触发模式**（`TriggerMode=On, TriggerSource=Software`）并开始取流。
- `read_frame()`：调用 `MV_CC_TriggerSoftwareExecute()` 发出软触发，`MV_CC_GetImageBuffer()` 取帧，转换为 BGR numpy 数组后返回。
- `close()`：停止取流，关闭设备，释放缓冲区。
- MVS SDK（`MvCameraControl`）未安装时，`open()` 返回 `False` 并打印明确提示，不影响其他功能。

**配置参数**（通过 `/api/stream/start` 的 `source_config` 字段传入）：

```json
{
  "source_type": "hikvision",
  "device_index": 0,
  "exposure_time": 10000
}
```

---

## 第二部分：OPC UA 触发器（opcua_trigger.py）

### 功能

订阅 PLC 的 OPC UA 节点，节点值变为触发值时向 `trigger_queue` 放入事件，驱动 `stream_processor` 抓图。

### 工作流程

1. 使用 `asyncua` 库连接 OPC UA Server（URL + NodeId 可配置）
2. 订阅目标节点的 DataChange 事件
3. 收到触发值（默认 `1`）时，往线程安全的 `queue.Queue` 放一个 `{"type": "trigger", "timestamp": ...}` 事件
4. 等收到复位值（默认 `0`）后才重新接受下次触发（防抖）
5. 断线时指数退避重连，间隔 1s → 2s → 4s，最长 30s

### 配置参数

```json
{
  "trigger_mode": "opcua",
  "opc_url": "opc.tcp://192.168.1.10:4840",
  "node_id": "ns=2;i=1001",
  "trigger_value": 1,
  "reset_value": 0
}
```

### stream_processor.py 改造

`_capture_loop()` 在 `trigger_mode == "opcua"` 时，将原来的 `time.sleep(interval)` 替换为 `trigger_queue.get(timeout=30)` 阻塞等待，其余抓图和分析逻辑不变。

---

## 第三部分：数据持久化层（storage.py）

### SQLite 表结构

**sessions 表**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 会话 ID（UUID 前 8 位） |
| started_at | REAL | Unix 时间戳 |
| ended_at | REAL | 结束时间，运行中为 NULL |
| status | TEXT | running / completed / stopped / error |
| source | TEXT | 视频路径或相机标识 |
| source_type | TEXT | opencv / hikvision |
| trigger_mode | TEXT | interval / opcua |
| config_json | TEXT | 完整参数快照（JSON） |

**frames 表**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| session_id | TEXT | 外键 → sessions.id |
| frame_index | INTEGER | 帧序号 |
| capture_time | REAL | 相对会话开始的秒数 |
| delta_e | REAL | 整体 ΔE 值 |
| change_ratio | REAL | 变色网格占比 |
| is_changed | INTEGER | 0/1 |
| ref_side | TEXT | left / right |
| image_path | TEXT | 结果图相对路径（data/images/{session_id}/frame_{n}_result.jpg） |
| analysis_json | TEXT | 完整步骤数据，供历史详情 Modal 渲染 |

### 图片归档

每帧保存两张图：
- `data/images/{session_id}/frame_{n:03d}_roi.jpg`：ROI 提取结果
- `data/images/{session_id}/frame_{n:03d}_result.jpg`：变色标注图

中间步骤图（二值化、热力图等）不存储，通过 `analysis_json` 在前端重渲染。

### storage.py 接口

```python
def init_db() -> None                          # 建表（幂等）
def save_session(session_id, config) -> None
def update_session_status(session_id, status, ended_at=None) -> None
def save_frame(session_id, frame_index, analysis, frame_img) -> None
def list_sessions(page=1, page_size=20) -> list[dict]
def get_session_frames(session_id) -> list[dict]
def export_csv(session_id) -> str              # 返回 CSV 文本
```

### 新增 API 端点（app.py）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/history/sessions` | GET | 分页列出会话（`?page=1&page_size=20`） |
| `/api/history/sessions/<id>/frames` | GET | 该会话所有帧摘要 |
| `/api/history/sessions/<id>/export` | GET | 下载 CSV |

历史帧详情复用现有 `/api/stream/frame/<session_id>/<frame_index>`，从 `analysis_json` 返回，无需新端点。

---

## 第四部分：前端历史记录 Tab

### 新增文件

- `frontend/js/history.js`：会话列表渲染、帧时间轴渲染、CSV 下载

### index.html 改动

新增第三个 Tab 按钮和 `tab-history` 面板，布局：左侧会话列表（固定宽度）+ 右侧帧时间轴。

### 复用策略

- 帧卡片渲染：`appendFrameCard(data, container)` 改造为接受目标容器参数（原调用处传 `document.getElementById('s-timeline')` 保持不变），`history.js` 传入历史 Tab 的时间轴容器
- 详情 Modal：`openModal(frameIndex, sessionId)` 改造为接受显式 `sessionId` 参数，不再依赖 `currentSessionId` 全局变量；`buildModalStepper()` / `buildModalResultCards()` 无需修改

### CSV 导出

点击"导出 CSV"按钮，`fetch('/api/history/sessions/{id}/export')` 后用 `Blob` + `<a download>` 触发浏览器下载，文件名为 `session_{id}_{date}.csv`。

---

## 依赖变更

```
# requirements.txt 新增
asyncua>=1.0.0        # OPC UA 客户端（异步，支持订阅）
# MVS SDK Python 封装不通过 pip 安装，需手动从 MVS 安装目录复制以下文件至 backend/：
#   C:\Program Files (x86)\MVS\Development\Samples\Python\MvCameraControl_class.py
#   C:\Program Files (x86)\MVS\Development\Samples\Python\MvErrorDefine_const.py
#   C:\Program Files (x86)\MVS\Development\Samples\Python\CameraParams_header.py
#   C:\Program Files (x86)\MVS\Development\Samples\Python\PixelType_header.py
```

---

## 不在本次范围内

- CIE76 → CIEDE2000 算法升级
- 图像质量预检（模糊度/过曝检测）
- 多用户/权限管理
- RTSP 断线重连（OpenCV 层现有行为不变）
