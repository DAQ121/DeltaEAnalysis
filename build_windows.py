"""
Windows打包启动脚本
将Flask后端和前端HTTP服务器整合到一个程序中
"""
import os
import sys
import webbrowser
import threading
import time
from pathlib import Path

# 添加backend目录到路径
backend_dir = Path(__file__).parent / 'backend'
sys.path.insert(0, str(backend_dir))

def start_backend():
    """启动Flask后端"""
    from backend.app import app
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
