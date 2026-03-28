# 试纸色差检测 Web Demo 设计方案

## 项目架构

### 技术栈
- **前端**：HTML + CSS + JavaScript (原生/Vue.js)
- **后端**：Flask (Python)
- **图像处理**：OpenCV + scikit-image + NumPy
- **通信**：RESTful API

### 架构图
```
前端 (Web UI)
    ↓ HTTP Request (上传图片 + 阈值)
后端 (Flask API)
    ↓ 图像处理管道
    ↓ 返回每步结果 (JSON + Base64图片)
前端 (可视化展示)
```

---

## 功能模块设计

### 1. 参数设置区
**功能**：
- ΔE 阈值滑块（范围：5-30，默认：10）
- 网格大小选择（10×10, 20×20, 30×30）
- 参考区域比例（10%-25%）

**UI 组件**：
```html
<div class="settings-panel">
  <label>ΔE 阈值: <span id="threshold-value">10</span></label>
  <input type="range" id="threshold" min="5" max="30" value="10">

  <label>网格大小:</label>
  <select id="grid-size">
    <option value="10">10×10</option>
    <option value="20" selected>20×20</option>
    <option value="30">30×30</option>
  </select>
</div>
```

---

### 2. 图片上传区
**功能**：
- 拖拽上传 / 点击上传
- 预览原始图片
- 显示图片信息（尺寸、大小）

**UI 组件**：
```html
<div class="upload-area" id="upload-area">
  <input type="file" id="file-input" accept="image/*">
  <p>拖拽图片到此处或点击上传</p>
</div>
<div class="preview">
  <img id="original-image" src="" alt="原始图片">
</div>
```

---

### 3. 分析按钮
**功能**：
- 触发后端分析
- 显示加载状态
- 禁用重复点击

**UI 组件**：
```html
<button id="analyze-btn" disabled>开始视觉分析</button>
<div class="loading" id="loading" style="display:none;">
  <span>分析中...</span>
</div>
```

---

### 4. 分步可视化展示区

#### 步骤1：ROI 提取
**展示内容**：
- 原始图片
- 二值化结果
- 轮廓检测结果
- 最终 ROI 区域

**说明文字**：
```
步骤1：ROI 提取
- 对图像进行灰度化和高斯去噪
- 使用 Otsu 方法自动二值化
- 检测轮廓并筛选最大轮廓
- 提取试纸区域（绿色框标注）
```

#### 步骤2：参考色提取
**展示内容**：
- ROI 图像
- 参考区域标注（红色框）
- 参考色色块展示
- LAB 值显示

**说明文字**：
```
步骤2：参考色提取
- 从试纸上部 15% 区域提取参考色
- 参考色 LAB 值：L=85.2, a=2.1, b=-3.5
- 该区域代表试纸的正常颜色
```

#### 步骤3：网格划分
**展示内容**：
- ROI 图像 + 网格线叠加
- 网格尺寸信息

**说明文字**：
```
步骤3：网格划分
- 将 ROI 划分为 20×20 网格
- 每个网格独立计算色差
- 总计 400 个网格单元
```

#### 步骤4：色差计算
**展示内容**：
- 色差热力图（蓝→绿→黄→红）
- 颜色条（Color Bar）
- ΔE 值范围标注

**说明文字**：
```
步骤4：色差计算
- 计算每个网格与参考色的 ΔE 值
- 蓝色：ΔE 接近 0（无变色）
- 红色：ΔE 较大（明显变色）
```

#### 步骤5：变色区域识别
**展示内容**：
- 原始 ROI 图像
- 变色区域高亮标注（红色遮罩）
- 阈值线标注

**说明文字**：
```
步骤5：变色区域识别
- 阈值：ΔE > 10
- 红色区域：超过阈值的变色区域
- 变色比例：35%
```

---

### 5. 最终结果展示区

**展示内容**：
```html
<div class="result-panel">
  <div class="result-card">
    <h3>色差值 (ΔE)</h3>
    <div class="result-value">18.3</div>
    <div class="result-label">变色区域平均色差</div>
  </div>

  <div class="result-card">
    <h3>变色比例</h3>
    <div class="result-value">35%</div>
    <div class="result-label">变色区域占总面积</div>
  </div>

  <div class="result-status success">
    <span>✓ 实验成功</span>
    <p>色差值超过设定阈值 (10)</p>
  </div>
</div>
```

**判断逻辑**：
- ΔE ≥ 阈值 → 显示"✓ 实验成功"（绿色）
- ΔE < 阈值 → 显示"✗ 实验失败"（红色）

---

## 页面布局设计

```
┌─────────────────────────────────────────────────┐
│              试纸色差检测系统                      │
├─────────────────────────────────────────────────┤
│  参数设置区                                       │
│  [ΔE阈值: 10] [网格: 20×20]                      │
├─────────────────────────────────────────────────┤
│  图片上传区                                       │
│  ┌─────────────────┐                            │
│  │  拖拽或点击上传   │                            │
│  └─────────────────┘                            │
│  [原始图片预览]                                   │
│  [开始视觉分析]                                   │
├─────────────────────────────────────────────────┤
│  分步可视化展示区                                 │
│  ┌──────────┬──────────┬──────────┐            │
│  │ 步骤1    │ 步骤2    │ 步骤3    │            │
│  │ ROI提取  │ 参考色   │ 网格划分  │            │
│  └──────────┴──────────┴──────────┘            │
│  ┌──────────┬──────────┐                       │
│  │ 步骤4    │ 步骤5    │                       │
│  │ 色差计算  │ 变色识别  │                       │
│  └──────────┴──────────┘                       │
├─────────────────────────────────────────────────┤
│  最终结果展示区                                   │
│  ┌──────────┬──────────┬──────────┐            │
│  │ ΔE: 18.3 │ 比例: 35%│ ✓ 成功   │            │
│  └──────────┴──────────┴──────────┘            │
└─────────────────────────────────────────────────┘
```

---

## API 接口设计

### 接口：`/api/analyze`

**请求方式**：POST

**请求参数**：
```json
{
  "image": "base64_encoded_image_data",
  "threshold": 10,
  "grid_size": 20,
  "reference_ratio": 0.15
}
```

**响应格式**：
```json
{
  "success": true,
  "steps": {
    "step1_roi_extraction": {
      "title": "ROI 提取",
      "description": "对图像进行灰度化和高斯去噪...",
      "images": {
        "original": "base64_image",
        "binary": "base64_image",
        "contours": "base64_image",
        "roi": "base64_image"
      },
      "data": {
        "roi_size": [800, 400]
      }
    },
    "step2_reference_color": {
      "title": "参考色提取",
      "description": "从试纸上部 15% 区域提取参考色...",
      "images": {
        "roi_with_reference": "base64_image",
        "reference_color_block": "base64_image"
      },
      "data": {
        "lab_values": [85.2, 2.1, -3.5]
      }
    },
    "step3_grid_division": {
      "title": "网格划分",
      "description": "将 ROI 划分为 20×20 网格...",
      "images": {
        "grid_overlay": "base64_image"
      },
      "data": {
        "grid_size": [20, 20],
        "total_cells": 400
      }
    },
    "step4_delta_e_calculation": {
      "title": "色差计算",
      "description": "计算每个网格与参考色的 ΔE 值...",
      "images": {
        "heatmap": "base64_image"
      },
      "data": {
        "delta_e_range": [0.5, 25.3]
      }
    },
    "step5_color_change_detection": {
      "title": "变色区域识别",
      "description": "阈值：ΔE > 10...",
      "images": {
        "highlighted_area": "base64_image"
      },
      "data": {
        "threshold": 10,
        "changed_cells": 140
      }
    }
  },
  "final_results": {
    "overall_delta_e": 12.5,
    "changed_area_delta_e": 18.3,
    "color_change_ratio": 0.35,
    "experiment_success": true,
    "threshold_used": 10
  }
}
```

---

## 前端交互流程

```
用户打开页面
    ↓
设置 ΔE 阈值（可选）
    ↓
上传图片（拖拽/点击）
    ↓
预览原始图片
    ↓
点击"开始视觉分析"按钮
    ↓
显示加载动画
    ↓
发送 POST 请求到后端
    ↓
后端处理并返回结果
    ↓
隐藏加载动画
    ↓
逐步展示每个步骤的可视化结果
  - 步骤1：ROI 提取（淡入动画）
  - 步骤2：参考色提取（淡入动画）
  - 步骤3：网格划分（淡入动画）
  - 步骤4：色差计算（淡入动画）
  - 步骤5：变色区域识别（淡入动画）
    ↓
展示最终结果（高亮动画）
    ↓
用户可下载报告或重新分析
```

---

## 后端处理流程

```python
def analyze_image(image_data, threshold, grid_size, reference_ratio):
    """
    主处理函数
    """
    results = {
        "success": False,
        "steps": {},
        "final_results": {}
    }

    # 步骤1：ROI 提取
    roi_data = extract_roi(image_data)
    results["steps"]["step1_roi_extraction"] = roi_data

    # 步骤2：参考色提取
    ref_data = extract_reference_color(roi_data["roi_image"], reference_ratio)
    results["steps"]["step2_reference_color"] = ref_data

    # 步骤3：网格划分
    grid_data = divide_into_grid(roi_data["roi_image"], grid_size)
    results["steps"]["step3_grid_division"] = grid_data

    # 步骤4：色差计算
    delta_e_data = calculate_delta_e(grid_data, ref_data["lab_values"])
    results["steps"]["step4_delta_e_calculation"] = delta_e_data

    # 步骤5：变色区域识别
    change_data = detect_color_change(delta_e_data, threshold)
    results["steps"]["step5_color_change_detection"] = change_data

    # 最终结果
    results["final_results"] = calculate_final_results(
        delta_e_data, change_data, threshold
    )
    results["success"] = True

    return results
```

---

## 文件结构

```
shijuedemo/
├── backend/
│   ├── app.py                 # Flask 主程序
│   ├── image_processor.py     # 图像处理核心逻辑
│   ├── utils.py               # 工具函数
│   └── requirements.txt       # Python 依赖
├── frontend/
│   ├── index.html             # 主页面
│   ├── css/
│   │   └── style.css          # 样式文件
│   └── js/
│       ├── main.js            # 主逻辑
│       └── visualizer.js      # 可视化模块
├── static/
│   └── sample_images/         # 示例图片
└── docs/
    ├── 试纸色差检测技术方案.md
    └── Web_Demo设计方案.md
```

---

## 样式设计要点

### 配色方案
- 主色调：蓝色系（#2196F3）
- 成功色：绿色（#4CAF50）
- 失败色：红色（#F44336）
- 背景色：浅灰（#F5F5F5）

### 动画效果
- 步骤展示：淡入动画（fade-in）
- 结果高亮：缩放动画（scale-up）
- 加载状态：旋转动画（spin）

### 响应式设计
- 桌面端：多列布局
- 移动端：单列堆叠布局

---

## 优化建议

### 性能优化
1. 图片压缩：前端上传前压缩到合理尺寸
2. 异步处理：后端使用异步任务队列
3. 缓存机制：相同参数的结果缓存 5 分钟

### 用户体验
1. 进度条：显示处理进度（0-100%）
2. 错误提示：友好的错误信息
3. 导出功能：下载分析报告（PDF/JSON）

### 扩展功能
1. 批量处理：支持多张图片同时分析
2. 历史记录：保存最近 10 次分析结果
3. 对比模式：对比不同参数的分析结果

---

## 开发步骤

### 第一阶段：后端开发
1. 搭建 Flask 框架
2. 实现图像处理核心逻辑
3. 实现 API 接口
4. 测试各步骤输出

### 第二阶段：前端开发
1. 搭建 HTML 结构
2. 实现 CSS 样式
3. 实现 JavaScript 交互
4. 集成后端 API

### 第三阶段：联调与优化
1. 前后端联调
2. 性能优化
3. 用户体验优化
4. 部署上线

---

## 最终实现总结

### 已完成功能

#### 前端界面
- ✅ 参数设置区
  - ΔE阈值：0-30（滑块调节）
  - 网格大小：3-50（数字输入）
  - 参考色模式：自动识别/手动指定LAB值
  - 填充黑洞开关（复选框）
- ✅ 图片上传（拖拽/点击上传）
- ✅ 原始图片预览
- ✅ 开始分析按钮 + 加载动画

#### 分步可视化
- ✅ 步骤1：ROI提取（二值化、轮廓检测、旋转矩形）
- ✅ 步骤2：参考色提取（CLAHE + K-means聚类、参考色块）
- ✅ 步骤3：网格划分（自适应正方形网格）
- ✅ 步骤4：色差计算（热力图可视化）
- ✅ 步骤5：变色区域识别（红色高亮标注）

#### 结果展示
- ✅ 色差值（ΔE）
- ✅ 变色比例（%）
- ✅ 实验结果判断（成功/失败）

### 技术实现

#### 后端（Flask）
- 端口：5002
- API：`/api/analyze`
- 图像处理：OpenCV + scikit-image
- 核心算法：CLAHE + K-means + CIE76色差

#### 前端（原生JS）
- 端口：8080
- 响应式布局
- 动画效果（淡入、缩放）
- 实时参数调整

### 项目文件结构

```
shijuedemo/
├── backend/
│   ├── app.py                    # Flask主程序
│   ├── image_processor.py        # 图像处理核心（已优化）
│   └── requirements.txt          # Python依赖
├── frontend/
│   ├── index.html               # 主页面
│   ├── css/style.css            # 样式文件
│   └── js/main.js               # 前端逻辑
├── static/uploads/              # 上传目录
├── 试纸色差检测技术方案.md       # 技术方案文档
├── Web_Demo设计方案.md          # 设计方案文档
└── README.md                    # 使用说明
```

### 核心优化

1. **CLAHE光照校正**：消除阴影和光照不均影响
2. **K-means聚类**：自动分离正常区域和变色区域
3. **亮度优先选择**：选择亮度更高的类作为参考色（偏白色）
4. **ROI边缘填充**：填充最外围两圈网格排除轮廓干扰
5. **可选黑洞填充**：支持配置是否填充黑洞区域
6. **手动参考色**：支持手动指定LAB参考值
7. **自适应网格**：正方形网格自适应尺寸（3-50可调）
8. **掩码过滤**：只计算试纸内像素

### 使用方法

1. 启动后端：`cd backend && python3 app.py`
2. 启动前端：`cd frontend && python3 -m http.server 8080`
3. 访问：`http://localhost:8080`
4. 设置阈值 → 上传图片 → 开始分析

---

**文档版本**：v2.0
**最后更新**：2026-03-28
**状态**：✅ 已完成并测试
