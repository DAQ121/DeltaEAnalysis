# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

试纸色差检测系统 —— 基于计算机视觉，自动检测试纸变色区域并用 CIE76 标准计算色差值（ΔE）。

## 开发命令

### 后端
```bash
cd backend
pip install -r requirements.txt
python3 app.py  # 运行在 http://localhost:5002
```

### 前端
```bash
cd frontend
python3 -m http.server 8080  # 访问 http://localhost:8080
```

## 架构说明

### 后端（Flask + OpenCV）

**app.py** — Flask 入口，三组 API：
- `/api/analyze` — 单张图片分析
- `/api/stream/*` — 视频流检测（启动、停止、事件推送、帧详情）
- `/api/stream/video/<session_id>` — MJPEG 实时预览流

**image_processor.py** — 核心图像处理流水线，5 个步骤：
1. `extract_roi()` — Otsu 二值化 + 轮廓检测 + 透视变换提取 ROI
2. `find_hole_and_crop()` — 检测暗色黑洞（灰度 < 50），裁掉黑洞及其左侧区域
3. `split_left_right()` — 从中点将裁剪图分为左右两半
4. `calculate_delta_e_grid()` — 在 LAB 色彩空间用 CIE76 公式计算每个网格的 ΔE
5. `detect_color_change()` — 标记超过阈值的网格，仅统计右侧网格

**stream_processor.py** — 双线程视频流处理：
- `_video_read_loop()` — 持续以 ~30fps 读取帧，更新 `latest_frame`
- `_capture_loop()` — 按配置间隔抓帧进行色差分析
- 用 `threading.Lock` 同步两个线程对帧的读写
- 本地视频文件读到末尾后循环播放；也支持 RTSP 流

### 核心算法

**色差计算**（CIE76，CIELAB 色彩空间）：
```
ΔE = √((L₂-L₁)² + (a₂-a₁)² + (b₂-b₁)²)
```

**参考色基准**：黑洞裁剪后，左半区域的平均 LAB 值作为参考色。

**网格分析**：右侧网格与左侧基准比较，超过阈值即判定为变色。

### 前端（原生 JS）

- `frontend/js/main.js` — 单图分析：图片上传、参数配置、API 调用、步骤可视化渲染
- `frontend/js/stream.js` — 视频流检测：SSE 连接管理、帧卡片渲染、MJPEG 预览、详情 Modal
- `frontend/css/style.css` — 全局样式，暗色主题（`#080a0d` 背景 + 琥珀色 `#f5a623` 强调色）

**SSE 事件流**（`stream.js` ↔ `app.py`）：
- `frame` — 每次抓帧分析完成，携带缩略图和色差数据，前端追加帧卡片
- `completed` — 检测到变色时触发，仅携带汇总结果（不重复携带帧数据）
- `stopped` / `error` — 流结束或异常

## 注意事项

- 后端端口为 **5002**，不是默认的 5000
- OpenCV 默认 BGR，色差计算前需转换为 RGB → LAB
- 视频流会话用 UUID 短 ID 管理，支持并发多路流
- MJPEG 预览以 ~20fps 推送，色差分析按用户配置的间隔独立运行
- `app.run()` 必须加 `use_reloader=False`，否则 Flask debug 模式会 fork 两个进程，导致每个 SSE 事件被推送两次
