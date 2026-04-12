# 试纸色差检测系统

## 项目简介

基于计算机视觉的试纸色差检测系统，自动识别试纸变色区域并计算色差值（ΔE），支持自定义参数和多种检测模式。

## 核心功能

- 自动ROI提取与角度校正
- CIE76 标准色差计算（ΔE）
- 自适应网格划分与热力图可视化
- 单张图片上传分析
- 视频流实时检测（支持三种视频源）
  - 视频文件 / RTSP 流
  - 海康工业相机（MVS SDK，GigE Vision）
  - 模拟相机（测试图片循环）
- 海康相机设备自动枚举
- ROI 评分权重可配置

## 快速启动

### 1. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 启动后端服务

```bash
python3 app.py
```

后端将运行在 `http://localhost:5002`

### 3. 启动前端

打开新终端：

```bash
cd frontend
python3 -m http.server 8080
```

### 4. 访问应用

打开浏览器访问：`http://localhost:8080`

## 使用说明

### 参数配置

1. **ΔE 阈值**：设置色差判断阈值（0-30，默认10）
2. **网格大小**：设置分析网格数量（3-50，默认10）
3. **参考色模式**：
   - 自动识别：使用CLAHE+K-means自动提取参考色
   - 手动指定：输入自定义LAB值
4. **填充黑洞**：是否填充试纸上的黑洞区域

### 分析流程

1. 上传试纸图片（支持拖拽）
2. 调整参数（可选）
3. 点击"开始视觉分析"
4. 查看5步可视化结果：
   - 步骤1：ROI提取
   - 步骤2：参考色提取
   - 步骤3：网格划分
   - 步骤4：色差计算
   - 步骤5：变色区域识别
5. 查看最终结果（色差值、变色比例、实验成功/失败）

## 技术栈

### 后端
- Python 3.8+
- Flask - Web框架
- OpenCV - 图像处理
- scikit-image - 色彩空间转换
- NumPy - 数值计算

### 前端
- 原生HTML/CSS/JavaScript
- 响应式布局

## 核心算法

1. **ROI提取**：Otsu二值化 + 轮廓检测 + 透视变换
2. **参考色提取**：CLAHE光照校正 + K-means聚类（选择亮度更高的类）
3. **色差计算**：CIE76色差公式（CIELAB色彩空间）
4. **边缘处理**：自动填充ROI最外围两圈网格为参考色
5. **黑洞填充**：可选的黑洞区域智能填充

## 项目结构

```
shijuedemo/
├── backend/
│   ├── app.py                    # Flask主程序（端口5002）
│   ├── image_processor.py        # 图像处理核心逻辑
│   ├── stream_processor.py       # 视频流处理（双线程架构）
│   ├── camera/                   # 相机适配层
│   │   ├── base.py               # BaseCameraSource 抽象基类
│   │   ├── opencv_source.py      # OpenCV 视频源（文件/RTSP）
│   │   ├── hikvision_source.py   # 海康 MVS SDK 集成
│   │   ├── mock_source.py        # 模拟相机（测试用）
│   │   └── MvImport/             # MVS SDK Python 封装（需手动复制）
│   └── requirements.txt          # Python依赖
├── frontend/
│   ├── index.html               # 主页面
│   ├── css/style.css            # 样式文件
│   ├── js/main.js               # 单图分析逻辑
│   └── js/stream.js             # 视频流检测逻辑
├── mediamtx/
│   └── test-img/                # 测试用试纸图片
├── docs/                        # 设计文档
├── 使用手册.md                   # 使用手册
├── 试纸色差检测技术方案.md        # 技术方案文档
├── Web_Demo设计方案.md           # 设计方案文档
└── README.md                    # 项目说明
```

## 更新日志

### v3.0 (2026-04-11)
- 新增相机适配层（BaseCameraSource 抽象基类）
- 集成海康 MVS SDK，支持 GigE Vision 工业相机接入
- 新增模拟相机模式（测试图片循环，可配置切换间隔）
- 新增设备枚举 API（`/api/camera/devices`）
- 前端视频源类型可切换（海康相机 / 视频文件 / 模拟相机）
- 跨平台支持（Windows + Linux）

### v2.0 (2026-03-28)
- ✅ 优化参考色提取：CLAHE增强 + K-means聚类
- ✅ 添加手动指定LAB参考值功能
- ✅ 添加填充黑洞开关
- ✅ 自动填充ROI最外围两圈网格
- ✅ 优先选择偏白色区域作为参考色

### v1.0
- ✅ 基础ROI提取和色差计算
- ✅ 网格划分和热力图可视化
- ✅ Web界面实现
```
