# 试纸色差检测系统

## 快速启动

### 1. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 启动后端服务

```bash
python app.py
```

后端将运行在 `http://localhost:5000`

### 3. 启动前端

打开新终端：

```bash
cd frontend
python -m http.server 8080
```

### 4. 访问应用

打开浏览器访问：`http://localhost:8080`

## 使用说明

1. 设置 ΔE 阈值（默认 10）
2. 上传试纸图片
3. 点击"开始视觉分析"
4. 查看分步可视化结果和最终色差值

## 项目结构

```
shijuedemo/
├── backend/
│   ├── app.py                 # Flask 主程序
│   ├── image_processor.py     # 图像处理核心
│   └── requirements.txt       # Python 依赖
├── frontend/
│   ├── index.html            # 主页面
│   ├── css/style.css         # 样式
│   └── js/main.js            # 前端逻辑
└── static/uploads/           # 上传目录
```
