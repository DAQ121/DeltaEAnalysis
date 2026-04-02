import cv2
import base64
import time
import threading
import queue
import uuid

from image_processor import analyze_image

# { session_id: { config, status, start_time, frames, queue, thread, latest_frame, frame_lock } }
sessions = {}


def _make_thumbnail(frame, width=200):
    h, w = frame.shape[:2]
    new_h = int(h * width / w)
    thumb = cv2.resize(frame, (width, new_h))
    _, buf = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode('utf-8')


def _video_read_loop(session_id):
    """持续读取视频帧，更新 latest_frame，供预览流和分析使用"""
    session = sessions[session_id]
    config = session['config']
    cap = cv2.VideoCapture(config['source'])

    if not cap.isOpened():
        session['cap_opened'] = False
        return

    session['cap_opened'] = True
    while session['status'] == 'running':
        ret, frame = cap.read()
        if not ret:
            # 本地视频读到末尾，循环播放
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        with session['frame_lock']:
            session['latest_frame'] = frame
        time.sleep(0.033)  # ~30fps

    cap.release()


def _capture_loop(session_id):
    """按设定间隔抓取当前帧进行色差分析"""
    session = sessions[session_id]
    config = session['config']
    q = session['queue']

    # 等待视频读取线程打开视频源（最多5秒）
    for _ in range(50):
        if session['cap_opened'] is not None:
            break
        time.sleep(0.1)

    if not session.get('cap_opened'):
        q.put({'type': 'error', 'message': '无法打开视频源，请检查路径或 RTSP 地址'})
        session['status'] = 'error'
        return

    session['start_time'] = time.time()
    frame_index = 0
    interval = config['interval']

    while session['status'] == 'running':
        with session['frame_lock']:
            frame = session.get('latest_frame')

        if frame is None:
            time.sleep(0.1)
            continue

        capture_time = round(time.time() - session['start_time'], 1)
        thumbnail = _make_thumbnail(frame)

        _, buf = cv2.imencode('.jpg', frame)
        frame_b64 = 'data:image/jpeg;base64,' + base64.b64encode(buf).decode('utf-8')

        try:
            analysis = analyze_image(frame_b64, config['threshold'], config['grid_size'], config.get('score_weights'))
        except Exception as e:
            q.put({'type': 'frame_error', 'frame_index': frame_index,
                   'capture_time': capture_time, 'message': str(e)})
            frame_index += 1
            next_capture_wall_time = session['start_time'] + frame_index * interval
            sleep_secs = next_capture_wall_time - time.time()
            if sleep_secs > 0:
                time.sleep(sleep_secs)
            continue

        delta_e = analysis['final_results']['overall_delta_e']
        threshold = config['threshold']
        is_changed = delta_e >= threshold

        result = {
            'is_changed': is_changed,
            'change_time': capture_time,
            'deltaE': delta_e,
            'deltaE_ratio': round(delta_e / max(threshold, 0.001), 4),
            'change_ratio': analysis['final_results']['color_change_ratio']
        }

        frame_data = {
            'frame_index': frame_index,
            'capture_time': capture_time,
            'thumbnail': thumbnail,
            'result': result
        }

        session['frames'].append({**frame_data, 'analysis': analysis})
        q.put({'type': 'frame', 'data': frame_data})

        frame_index += 1

        if is_changed:
            session['status'] = 'completed'
            q.put({'type': 'completed', 'data': {'result': result}})
            break

        next_capture_wall_time = session['start_time'] + frame_index * interval
        sleep_secs = next_capture_wall_time - time.time()
        if sleep_secs > 0:
            time.sleep(sleep_secs)

    if session['status'] == 'running':
        session['status'] = 'stopped'
        q.put({'type': 'stopped'})


def start_session(config):
    session_id = str(uuid.uuid4())[:8]
    sessions[session_id] = {
        'config': config,
        'status': 'running',
        'start_time': None,
        'frames': [],
        'queue': queue.Queue(),
        'latest_frame': None,
        'frame_lock': threading.Lock(),
        'thread': None,
        'cap_opened': None  # None=未知, True=成功, False=失败
    }

    t_read = threading.Thread(target=_video_read_loop, args=(session_id,), daemon=True)
    t_analyze = threading.Thread(target=_capture_loop, args=(session_id,), daemon=True)
    sessions[session_id]['thread'] = t_analyze
    t_read.start()
    t_analyze.start()
    return session_id


def stop_session(session_id):
    if session_id in sessions:
        sessions[session_id]['status'] = 'stopped'


def get_frame_detail(session_id, frame_index):
    if session_id not in sessions:
        return None
    frames = sessions[session_id]['frames']
    if 0 <= frame_index < len(frames):
        return frames[frame_index]
    return None


def generate_preview_stream(session_id):
    """生成 MJPEG 流供前端实时预览"""
    if session_id not in sessions:
        return

    session = sessions[session_id]

    while session['status'] in ('running', 'completed'):
        with session['frame_lock']:
            frame = session.get('latest_frame')
        if frame is not None:
            ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
        time.sleep(0.05)  # ~20fps
