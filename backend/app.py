import json
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from image_processor import analyze_image
from stream_processor import start_session, stop_session, get_frame_detail, sessions

app = Flask(__name__)
CORS(app)


@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.json
        image_data = data.get('image')
        threshold = data.get('threshold', 10)
        grid_size = data.get('grid_size', 10)

        result = analyze_image(image_data, threshold, grid_size)
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/stream/start', methods=['POST'])
def stream_start():
    data = request.json
    source = data.get('source', '').strip()
    if not source:
        return jsonify({'success': False, 'error': '视频源不能为空'}), 400
    config = {
        'source': source,
        'interval': float(data.get('interval', 5)),
        'threshold': float(data.get('threshold', 10)),
        'grid_size': int(data.get('grid_size', 10))
    }
    session_id = start_session(config)
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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002, threaded=True)
