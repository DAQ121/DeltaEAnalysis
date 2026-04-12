# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

试纸色差检测系统 —— 基于计算机视觉，自动检测试纸变色区域并用 CIE76 标准计算色差值（ΔE）。支持单张图片分析和视频流实时检测两种模式。

## 开发命令

```bash
# 后端（Flask，端口 5002）
cd backend
python3 -m venv ../venv && source ../venv/bin/activate  # 首次
pip install -r requirements.txt
python3 app.py                    # http://localhost:5002

# 前端（静态文件，端口 8080）
cd frontend
python3 -m http.server 8080       # http://localhost:8080
```

**注意**：项目根目录有 `venv/` 虚拟环境，激活方式为 `source venv/bin/activate`。

## 架构说明

### 后端（Flask + OpenCV）

**app.py** — Flask 入口，四组 API：
- `/api/analyze` POST — 单张图片分析（接收 base64 图片，返回分步结果 + 最终色差数据）
  - 参数：`image`(base64)、`threshold`(默认10)、`grid_size`(默认10)、`score_weights`(可选，归一化权重字典)
- `/api/stream/start` POST、`/api/stream/stop/<id>` POST、`/api/stream/events/<id>` GET (SSE)、`/api/stream/frame/<id>/<index>` GET — 视频流检测
  - start 参数：`source_type`(`opencv`/`hikvision`/`mock`)、`source`(opencv模式)、`source_config`(hikvision/mock模式)、`interval`(秒)、`threshold`、`grid_size`、`score_weights`
- `/api/stream/video/<session_id>` GET — MJPEG 实时预览流
- `/api/camera/devices` GET — 枚举网络中可用的海康 GigE Vision 相机

**image_processor.py** — 核心图像处理流水线，5 个步骤：
1. `extract_roi()` — 多策略二值化 + 矩形度评分选取最佳轮廓 + 透视变换提取 ROI
2. `find_hole_and_crop()` — 检测暗色黑洞，裁掉黑洞及其左侧区域（支持黑洞在左端或右端，右端时自动翻转）
3. `split_left_right()` — 从中点将裁剪图分为左右两半
4. `calculate_delta_e_grid()` — 在 LAB 色彩空间用 CIE76 公式计算每个网格的 ΔE
5. `detect_color_change()` — 标记超过阈值的网格，仅统计右侧网格

**stream_processor.py** — 双线程视频流处理：
- `_create_source()` — 根据 `source_type` 创建对应的 `BaseCameraSource` 实例（`opencv`/`hikvision`/`mock`）
- `_video_read_loop()` — 持续调用 `source.read_frame()` 更新 `latest_frame`
- `_capture_loop()` — 按配置间隔抓帧，调用 `analyze_image()` 进行色差分析
- 用 `threading.Lock` 同步两个线程对帧的读写

**camera/** — 相机适配层模块：
- `camera/base.py` — `BaseCameraSource` 抽象基类，定义 `open()/read_frame()/close()/is_opened()` 接口
- `camera/opencv_source.py` — 基于 `cv2.VideoCapture` 的视频源，支持本地文件（循环播放）和 RTSP URL
- `camera/hikvision_source.py` — 海康 MVS SDK 集成（GigE Vision），软触发模式抓图；SDK 未安装时优雅降级
- `camera/mock_source.py` — 从 `mediamtx/test-img/` 循环读取图片模拟相机，支持配置图片切换间隔
- `camera/MvImport/` — 从 MVS 安装目录复制的 SDK Python 封装文件（不提交到 Git）

### 核心算法

**ROI 提取**（`extract_roi()` → `_generate_candidates()` + `_score_contour()`）：
- 三种二值化策略并行生成候选轮廓：
  - 自适应高斯阈值（`blockSize=51, C=10`，正/反两极性）
  - Canny 边缘检测（`30, 100`）+ 形态学闭合
  - Otsu 全局阈值
- `_score_contour()` 加权评分：矩形度 4% / 顶点数 4% / 长宽比 16% / 面积占比 0% / 亮度 76%
- 透视变换使用 `BORDER_REPLICATE` 避免黑色边框，mask 经二值化阈值处理消除插值伪影

**色差计算**（CIE76）：`ΔE = √((L₂-L₁)² + (a₂-a₁)² + (b₂-b₁)²)`

**参考色基准**：黑洞裁剪后，左半区域的平均 LAB 值作为参考色（`compute_mean_lab()`）。

### 前端（原生 JS，无构建步骤）

- `frontend/js/main.js` — 单图分析：图片上传（base64）、参数配置、API 调用、步骤可视化渲染、Toast 通知
- `frontend/js/stream.js` — 视频流检测：SSE 连接管理、帧卡片渲染、MJPEG 预览（canvas）、详情 Modal、Tab 切换
- `frontend/css/style.css` — 深色/浅色主题（`data-theme` 属性切换），深色用 `#080a0d` 背景 + 琥珀色 `#f5a623` 强调色
- `frontend/index.html` — 单页应用，两个 Tab 面板（单图 / 视频流）

### 数据流

**单图分析**：前端将图片转 base64 → POST `/api/analyze` → 后端执行 5 步管线 → 返回每步 base64 图片 + 数值数据 → 前端渲染步骤卡片和结果卡片

**视频流检测**：POST `/api/stream/start` 启动会话 → 前端通过 SSE `/api/stream/events/<id>` 接收 `frame` / `completed` / `stopped` / `error` 事件 → MJPEG 预览通过 `<img>` 标签连接 `/api/stream/video/<id>`

## 注意事项

- 后端端口为 **5002**，前端 JS 中硬编码了 `http://localhost:5002`
- OpenCV 默认 BGR，色差计算前需转换 BGR → RGB → LAB（通过 `skimage.color.rgb2lab`）
- `app.run()` 必须加 `use_reloader=False`，否则 Flask debug 模式会 fork 两个进程，导致 SSE 事件被推送两次
- 视频流会话用 UUID 短 ID（前 8 位）管理，会话状态存在内存 `sessions` 字典中
- MJPEG 预览以 ~20fps 推送，色差分析按用户配置的间隔独立运行
- `mediamtx/` 目录包含 MediaMTX 二进制和配置，可用于本地 RTSP 推流测试
- `mediamtx/test-img/` 中有测试用试纸图片（1.jpg ~ 7.jpg）

### 权重归一化

前端滑块为 0~100 的整数原始值（默认 5/5/20/0/95），发送到后端前由 `getScoreWeights()` 归一化为 sum=1.0 的比例字典。后端 `DEFAULT_SCORE_WEIGHTS` 存储的是归一化后的值。修改默认权重时需同步更新：
1. `backend/image_processor.py` 的 `DEFAULT_SCORE_WEIGHTS`（归一化值）
2. `frontend/index.html` 中两组滑块的 `value` 属性和显示 `<span>`（原始整数值，单图 + 视频流各一组）
