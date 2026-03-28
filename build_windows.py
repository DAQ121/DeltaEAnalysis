"""
Windows打包启动脚本
将Flask后端和前端HTTP服务器整合到一个程序中
"""
import os
import sys
import webbrowser
import threading
import time

# 直接导入Flask相关模块
from flask import Flask, request, jsonify
from flask_cors import CORS

# 导入图像处理模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from image_processor import analyze_image

# 创建Flask应用
app = Flask(__name__)
CORS(app)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        image_data = data.get('image')
        threshold = data.get('threshold', 10)
        grid_size = data.get('grid_size', 20)
        reference_ratio = data.get('reference_ratio', 0.15)
        manual_lab = data.get('manual_lab', None)
        fill_holes = data.get('fill_holes', True)

        result = analyze_image(image_data, threshold, grid_size, reference_ratio, manual_lab, fill_holes)
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

def start_backend():
    """启动Flask后端"""
    app.run(host='0.0.0.0', port=5002, debug=False, use_reloader=False)

def start_frontend():
    """启动前端HTTP服务器"""
    import http.server
    import socketserver

    frontend_dir = Path(__file__).parent / 'frontend'
    os.chdir(frontend_dir)

    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", 8080), Handler) as httpd:
        print("前端服务运行在 http://localhost:8080")
        httpd.serve_forever()

def open_browser():
    """延迟打开浏览器"""
    time.sleep(2)
    webbrowser.open('http://localhost:8080')

if __name__ == '__main__':
    print("=" * 50)
    print("试纸色差检测系统 v2.0")
    print("=" * 50)
    print("正在启动服务...")

    # 启动后端
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()

    # 启动前端
    frontend_thread = threading.Thread(target=start_frontend, daemon=True)
    frontend_thread.start()

    # 打开浏览器
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    print("\n服务已启动！")
    print("后端: http://localhost:5002")
    print("前端: http://localhost:8080")
    print("\n按 Ctrl+C 退出程序")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在关闭服务...")
        sys.exit(0)
