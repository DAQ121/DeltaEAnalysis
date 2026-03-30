import cv2
import base64
import time
import threading
import queue
import uuid

from image_processor import analyze_image

# { session_id: { config, status, start_time, frames, queue, thread } }
sessions = {}


def _make_thumbnail(frame, width=200):
    h, w = frame.shape[:2]
    new_h = int(h * width / w)
    thumb = cv2.resize(frame, (width, new_h))
    _, buf = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode('utf-8')


def _capture_loop(session_id):
    session = sessions[session_id]
    config = session['config']
    q = session['queue']

    cap = cv2.VideoCapture(config['source'])
    if not cap.isOpened():
        q.put({'type': 'error', 'message': '无法打开视频源，请检查路径或 RTSP 地址'})
        session['status'] = 'error'
        return

    session['start_time'] = time.time()
    frame_index = 0
    interval = config['interval']

    # 获取视频帧率，用于按时间跳帧
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)

    while session['status'] == 'running':
        # 计算当前应该抓取的视频时间位置（秒）
        target_video_time = frame_index * interval
        target_frame_pos = int(target_video_time * fps)

        # 如果视频有限长，循环处理
        if total_frames > 0:
            target_frame_pos = target_frame_pos % int(total_frames)

        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_pos)
        ret, frame = cap.read()
        if not ret:
            break

        capture_time = round(time.time() - session['start_time'], 1)
        thumbnail = _make_thumbnail(frame)

        _, buf = cv2.imencode('.jpg', frame)
        frame_b64 = 'data:image/jpeg;base64,' + base64.b64encode(buf).decode('utf-8')

        try:
            analysis = analyze_image(frame_b64, config['threshold'], config['grid_size'])
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

        # 内存中保存完整分析数据（含步骤图）
        session['frames'].append({**frame_data, 'analysis': analysis})

        # SSE 只推轻量数据（不含步骤图）
        q.put({'type': 'frame', 'data': frame_data})

        frame_index += 1

        if is_changed:
            session['status'] = 'completed'
            q.put({'type': 'completed', 'data': frame_data})
            break

        # 等到下一个抓拍时间点
        next_capture_wall_time = session['start_time'] + frame_index * interval
        sleep_secs = next_capture_wall_time - time.time()
        if sleep_secs > 0:
            time.sleep(sleep_secs)

    cap.release()
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
        'thread': None
    }
    t = threading.Thread(target=_capture_loop, args=(session_id,), daemon=True)
    sessions[session_id]['thread'] = t
    t.start()
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
