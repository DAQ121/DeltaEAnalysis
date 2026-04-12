import json
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from image_processor import analyze_image, ImageProcessingError
from stream_processor import start_session, stop_session, get_frame_detail, generate_preview_stream, sessions

app = Flask(__name__)
CORS(app)


@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        image_data = data.get('image')
        threshold = data.get('threshold', 10)
        grid_size = data.get('grid_size', 10)
        score_weights = data.get('score_weights')

        result = analyze_image(image_data, threshold, grid_size, score_weights)
        return jsonify(result)

    except ImageProcessingError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception:
        return jsonify({"success": False, "error": "服务器内部错误，请稍后重试"}), 500


@app.route('/api/stream/start', methods=['POST'])
def stream_start():
    data = request.json
    source_type = data.get('source_type', 'opencv')

    # 构建 config
    config = {
        'source_type': source_type,
        'interval': float(data.get('interval', 5)),
        'threshold': float(data.get('threshold', 10)),
        'grid_size': int(data.get('grid_size', 10)),
        'score_weights': data.get('score_weights'),
    }

    if source_type == 'opencv':
        source = data.get('source', '').strip()
        if not source:
            return jsonify({'success': False, 'error': '视频源不能为空'}), 400
        config['source'] = source
    elif source_type == 'hikvision':
        config['source_config'] = data.get('source_config', {})
    elif source_type == 'mock':
        config['source_config'] = data.get('source_config', {})
    else:
        return jsonify({'success': False, 'error': f'不支持的源类型: {source_type}'}), 400

    try:
        session_id = start_session(config)
    except RuntimeError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({'success': True, 'session_id': session_id})


@app.route('/api/stream/events/<session_id>')
def stream_events(session_id):
    if session_id not in sessions:
        return jsonify({'error': 'Session not found'}), 404

    def generate():
        q = sessions[session_id]['queue']
        while True:
            try:
                event = q.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event['type'] in ('completed', 'stopped', 'error'):
                    break
            except Exception:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


@app.route('/api/stream/stop/<session_id>', methods=['POST'])
def stream_stop(session_id):
    stop_session(session_id)
    return jsonify({'success': True})


@app.route('/api/stream/frame/<session_id>/<int:frame_index>')
def stream_frame_detail(session_id, frame_index):
    frame = get_frame_detail(session_id, frame_index)
    if frame is None:
        return jsonify({'error': 'Frame not found'}), 404
    return jsonify({'success': True, 'analysis': frame['analysis']})


@app.route('/api/stream/video/<session_id>')
def stream_video(session_id):
    if session_id not in sessions:
        return jsonify({'error': 'Session not found'}), 404
    return Response(generate_preview_stream(session_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/camera/devices')
def camera_devices():
    """枚举网络中可用的海康 GigE Vision 相机"""
    try:
        from camera.hikvision_source import is_sdk_available, enumerate_devices
    except ImportError:
        return jsonify({'success': True, 'devices': [], 'sdk_available': False,
                        'message': 'MVS SDK 未安装'})

    if not is_sdk_available():
        return jsonify({'success': True, 'devices': [], 'sdk_available': False,
                        'message': 'MVS SDK 未安装，请先安装海康 MVS 客户端'})

    devices = enumerate_devices()
    return jsonify({'success': True, 'devices': devices, 'sdk_available': True})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002, threaded=True, use_reloader=False)
