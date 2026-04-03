import cv2
import numpy as np
from skimage import color
import base64
from io import BytesIO
from PIL import Image


class ImageProcessingError(ValueError):
    """用户可见的图像处理错误"""
    pass


def decode_image(base64_string):
    """解码base64图片"""
    try:
        img_data = base64.b64decode(base64_string.split(',')[1] if ',' in base64_string else base64_string)
        img = Image.open(BytesIO(img_data))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    except Exception:
        raise ImageProcessingError("图片解码失败，请确认上传的是有效的图片文件")


def encode_image(img):
    """编码图片为base64"""
    _, buffer = cv2.imencode('.png', img)
    return base64.b64encode(buffer).decode('utf-8')


DEFAULT_SCORE_WEIGHTS = {
    'rectangularity': 0.04,
    'vertex': 0.04,
    'aspect': 0.16,
    'size': 0.0,
    'brightness': 0.76
}


def order_points(pts):
    """将4个角点排序为 [左上, 右上, 右下, 左下]，不受 boxPoints 旋转角度影响"""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).flatten()
    ordered = np.zeros((4, 2), dtype="float32")
    ordered[0] = pts[np.argmin(s)]   # 左上：x+y 最小
    ordered[1] = pts[np.argmin(d)]   # 右上：y-x 最小
    ordered[2] = pts[np.argmax(s)]   # 右下：x+y 最大
    ordered[3] = pts[np.argmax(d)]   # 左下：y-x 最大
    return ordered


def _score_contour(contour, image_area, gray, weights=None):
    """
    对轮廓按"矩形相似度 + 亮度"打分，用于从多个候选中选出最像试纸的矩形轮廓。
    返回 (score, rect, approx)，score ∈ [0, 1]，越高越像试纸。
    不合格的轮廓返回 (0, None, None)。
    """
    if weights is None:
        weights = DEFAULT_SCORE_WEIGHTS
    area = cv2.contourArea(contour)

    # 硬过滤：太小（< 0.5% 图像面积）或太大（> 85%，可能是背景/光照）
    if area < image_area * 0.005:
        return 0.0, None, None
    if area > image_area * 0.85:
        return 0.0, None, None

    rect = cv2.minAreaRect(contour)
    rect_w, rect_h = rect[1]
    rect_area = rect_w * rect_h
    if rect_area < 1:
        return 0.0, None, None

    # ① 矩形度：轮廓面积 / 最小外接矩形面积（矩形≈1.0，不规则光斑远小于1）
    rectangularity = area / rect_area

    # ② 顶点数：多边形近似应为 ~4 个顶点
    peri = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
    n_vertices = len(approx)
    if n_vertices == 4:
        vertex_score = 1.0
    elif n_vertices in (3, 5):
        vertex_score = 0.6
    elif n_vertices in (6, 7):
        vertex_score = 0.3
    else:
        vertex_score = 0.1

    # ③ 长宽比：试纸通常为长条矩形
    if min(rect_w, rect_h) < 1:
        return 0.0, None, None
    aspect = max(rect_w, rect_h) / min(rect_w, rect_h)
    if 1.5 <= aspect <= 10.0:
        aspect_score = 1.0
    elif 1.2 <= aspect <= 15.0:
        aspect_score = 0.5
    else:
        aspect_score = 0.15

    # ④ 面积占比：中等大小优先
    size_ratio = area / image_area
    if 0.02 <= size_ratio <= 0.60:
        size_score = 1.0
    elif 0.01 <= size_ratio <= 0.75:
        size_score = 0.5
    else:
        size_score = 0.2

    # ⑤ 亮度：试纸通常为浅色，优先选择内部亮度较高的轮廓
    contour_mask = np.zeros(gray.shape[:2], dtype=np.uint8)
    cv2.drawContours(contour_mask, [contour], -1, 255, -1)
    mean_brightness = cv2.mean(gray, mask=contour_mask)[0]
    brightness_score = mean_brightness / 255.0

    # 加权综合评分
    score = (weights['rectangularity'] * rectangularity +
             weights['vertex'] * vertex_score +
             weights['aspect'] * aspect_score +
             weights['size'] * size_score +
             weights['brightness'] * brightness_score)

    return score, rect, approx


def _generate_candidates(gray, blurred):
    """
    运行多种二值化策略，收集所有候选轮廓。
    返回 [(contour, strategy_name, binary_image), ...] 列表。
    """
    candidates = []

    # 策略 A：自适应高斯阈值（核心——处理光照不均）
    adaptive_binary = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=51,
        C=10
    )
    adaptive_inv = cv2.bitwise_not(adaptive_binary)

    kernel_close = np.ones((5, 5), np.uint8)
    for bin_img in [adaptive_binary, adaptive_inv]:
        closed = cv2.morphologyEx(bin_img, cv2.MORPH_CLOSE, kernel_close)
        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            candidates.append((c, "adaptive", closed))

    # 策略 B：Canny 边缘检测 + 形态学闭合（边缘对渐变光照鲁棒）
    edges = cv2.Canny(blurred, 30, 100)
    kernel_canny = np.ones((5, 5), np.uint8)
    edges_closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_canny)
    contours, _ = cv2.findContours(edges_closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        candidates.append((c, "canny", edges_closed))

    # 策略 C：Otsu（原方法，均匀光照下最优）
    _, otsu_binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel_otsu = np.ones((3, 3), np.uint8)
    otsu_closed = cv2.morphologyEx(otsu_binary, cv2.MORPH_CLOSE, kernel_otsu)
    contours, _ = cv2.findContours(otsu_closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        candidates.append((c, "otsu", otsu_closed))

    return candidates


def extract_roi(image, score_weights=None):
    """步骤1: 提取ROI区域（多策略二值化 + 矩形度评分）"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    image_area = gray.shape[0] * gray.shape[1]

    # Phase 1: 多策略生成候选轮廓
    candidates = _generate_candidates(gray, blurred)

    if not candidates:
        raise ImageProcessingError("未检测到试纸区域，请确认图片中包含试纸")

    # Phase 2: 对所有候选按矩形度评分，选最优
    best_score = 0
    best_contour = None
    best_rect = None
    best_approx = None
    best_binary = None

    for contour, strategy_name, binary_img in candidates:
        score, rect, approx = _score_contour(contour, image_area, gray, score_weights)
        if score > best_score:
            best_score = score
            best_contour = contour
            best_rect = rect
            best_approx = approx
            best_binary = binary_img

    MIN_SCORE_THRESHOLD = 0.3
    if best_score < MIN_SCORE_THRESHOLD or best_contour is None:
        raise ImageProcessingError(
            "未检测到矩形试纸区域，请确认图片中包含完整的试纸并避免强烈的光照不均"
        )

    # Phase 3: 透视变换
    binary = best_binary
    rect = best_rect

    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [best_contour], -1, 255, -1)

    # 优先用轮廓多边形近似的 4 顶点（紧贴轮廓），否则回退到 minAreaRect 外接矩形
    if best_approx is not None and len(best_approx) == 4:
        src_corner_pts = best_approx.reshape(4, 2).astype("float32")
        ordered = order_points(src_corner_pts)
    else:
        box = cv2.boxPoints(rect)
        ordered = order_points(box.astype("float32"))

    # 用于可视化的外接矩形框
    vis_box = np.int0(cv2.boxPoints(rect))

    # 从实际点距计算宽高，保持正确宽高比
    width = int(max(np.linalg.norm(ordered[1] - ordered[0]),
                    np.linalg.norm(ordered[2] - ordered[3])))
    height = int(max(np.linalg.norm(ordered[3] - ordered[0]),
                     np.linalg.norm(ordered[2] - ordered[1])))

    if width < 2 or height < 2:
        raise ImageProcessingError("检测到的试纸区域过小，请确认图片中包含完整的试纸")

    # 确保横向输出（width > height）
    if height > width:
        # 旋转点映射：[左上,右上,右下,左下] → [左下,左上,右上,右下]
        ordered = np.array([ordered[3], ordered[0], ordered[1], ordered[2]])
        width, height = height, width

    src_pts = ordered
    dst_pts = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
    try:
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        # BORDER_REPLICATE：边缘像素复制填充，避免黑色越界
        roi = cv2.warpPerspective(image, M, (width, height),
                                  borderMode=cv2.BORDER_REPLICATE)
        roi_mask = cv2.warpPerspective(mask, M, (width, height))
    except cv2.error:
        raise ImageProcessingError("试纸区域校正失败，轮廓形状异常，请调整拍摄角度后重试")

    # 重新二值化 mask，消除插值产生的半透明边缘（0~255 → 纯 0/255）
    _, roi_mask = cv2.threshold(roi_mask, 127, 255, cv2.THRESH_BINARY)
    roi[roi_mask == 0] = [255, 255, 255]

    contour_img = image.copy()
    cv2.drawContours(contour_img, [vis_box], 0, (0, 255, 0), 3)

    return {
        "roi_image": roi,
        "roi_mask": roi_mask,
        "binary": binary,
        "contour_img": contour_img,
        "roi_coords": (int(rect[0][0]), int(rect[0][1]), width, height)
    }


def find_hole_and_crop(roi_image, roi_mask):
    """
    步骤2: 找到黑洞位置，裁掉黑洞及其左侧所有区域，保留黑洞右侧部分。
    黑洞定义：试纸内部的暗色区域，阈值根据 ROI 亮度自适应计算。
    黑洞可能在试纸的左端或右端；如果在右端，先水平翻转使其位于左端。
    """
    h, w = roi_image.shape[:2]
    gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)

    # 自适应阈值：取 ROI 掩码内灰度中位数的 40%，下限 15 上限 50
    valid_gray = gray[roi_mask > 0]
    if len(valid_gray) > 0:
        median_val = float(np.median(valid_gray))
        hole_thresh = int(np.clip(median_val * 0.4, 15, 50))
    else:
        hole_thresh = 50

    # 在试纸掩码内找暗区域
    _, hole_mask = cv2.threshold(gray, hole_thresh, 255, cv2.THRESH_BINARY_INV)
    hole_mask = cv2.bitwise_and(hole_mask, roi_mask)

    # 形态学去噪，保留较大的黑洞
    kernel = np.ones((5, 5), np.uint8)
    hole_mask = cv2.morphologyEx(hole_mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(hole_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    hole_right_x = None
    largest_hole = None
    if contours:
        largest_hole = max(contours, key=cv2.contourArea)
        hole_area = cv2.contourArea(largest_hole)
        roi_area = h * w
        # 黑洞面积不应超过 ROI 的 20%，否则说明图片太暗导致误检
        if hole_area > roi_area * 0.2:
            largest_hole = None
        else:
            x, y, wh, hh = cv2.boundingRect(largest_hole)
            padding = wh // 4

            # 判断黑洞在哪端：如果在右半边，翻转图像使其到左端
            hole_center_x = x + wh // 2
            if hole_center_x > w // 2:
                roi_image = cv2.flip(roi_image, 1)
                roi_mask = cv2.flip(roi_mask, 1)
                # 在翻转后的图像上重新检测黑洞位置
                gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
                valid_gray = gray[roi_mask > 0]
                if len(valid_gray) > 0:
                    median_val = float(np.median(valid_gray))
                    hole_thresh = int(np.clip(median_val * 0.4, 15, 50))
                else:
                    hole_thresh = 50
                _, hole_mask = cv2.threshold(gray, hole_thresh, 255, cv2.THRESH_BINARY_INV)
                hole_mask = cv2.bitwise_and(hole_mask, roi_mask)
                hole_mask = cv2.morphologyEx(hole_mask, cv2.MORPH_OPEN, kernel)
                contours, _ = cv2.findContours(hole_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    largest_hole = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(largest_hole) > roi_area * 0.2:
                        largest_hole = None
                    else:
                        x, y, wh, hh = cv2.boundingRect(largest_hole)
                        padding = wh // 4
                        hole_right_x = min(x + wh + padding, w)
                else:
                    largest_hole = None
            else:
                hole_right_x = min(x + wh + padding, w)

    # 可视化
    vis_img = roi_image.copy()
    if hole_right_x is not None:
        cv2.line(vis_img, (hole_right_x, 0), (hole_right_x, h), (0, 0, 255), 2)
        cv2.drawContours(vis_img, [largest_hole], -1, (0, 255, 255), 2)
        # 裁剪：保留膨胀后右边界以右，确保剩余宽度 > 0
        remaining_width = w - hole_right_x
        if remaining_width < 2:
            cropped = roi_image.copy()
            cropped_mask = roi_mask.copy()
            hole_right_x = None
        else:
            cropped = roi_image[:, hole_right_x:].copy()
            cropped_mask = roi_mask[:, hole_right_x:].copy()
    else:
        cropped = roi_image.copy()
        cropped_mask = roi_mask.copy()

    return {
        "cropped_image": cropped,
        "cropped_mask": cropped_mask,
        "hole_right_x": hole_right_x,
        "vis_img": vis_img
    }


def split_left_right(cropped_image, cropped_mask):
    """
    步骤3: 从中间将裁剪后的图像分为左右两部分。
    """
    h, w = cropped_image.shape[:2]
    if w < 4 or h < 2:
        raise ImageProcessingError("裁剪后的试纸区域过小，无法进行左右分割分析")
    mid = w // 2

    left_img = cropped_image[:, :mid]
    right_img = cropped_image[:, mid:]
    left_mask = cropped_mask[:, :mid]
    right_mask = cropped_mask[:, mid:]

    # 可视化：画中线
    vis = cropped_image.copy()
    cv2.line(vis, (mid, 0), (mid, h), (0, 255, 0), 2)

    return {
        "left_img": left_img,
        "right_img": right_img,
        "left_mask": left_mask,
        "right_mask": right_mask,
        "split_vis": vis,
        "mid_x": mid
    }


def compute_mean_lab(img_bgr, mask):
    """计算掩码内区域的平均 LAB 值"""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_lab = color.rgb2lab(img_rgb / 255.0)
    valid = img_lab[mask > 0]
    if len(valid) == 0:
        return np.array([0.0, 0.0, 0.0])
    return np.mean(valid, axis=0)


def divide_into_grid(roi_image, grid_size):
    """网格划分"""
    h, w = roi_image.shape[:2]
    min_dim = min(h, w)
    cell_size = max(1, min_dim // grid_size)

    grid_h = h // cell_size
    grid_w = w // cell_size

    if grid_h < 1 or grid_w < 1:
        raise ImageProcessingError("图像太小，无法划分有效的分析网格，请尝试减小网格数")

    grid_overlay = roi_image.copy()
    for i in range(1, grid_h):
        cv2.line(grid_overlay, (0, i * cell_size), (w, i * cell_size), (255, 255, 0), 1)
    for j in range(1, grid_w):
        cv2.line(grid_overlay, (j * cell_size, 0), (j * cell_size, h), (255, 255, 0), 1)

    return {
        "grid_overlay": grid_overlay,
        "grid_size": [grid_h, grid_w],
        "cell_size": cell_size
    }


def calculate_delta_e_grid(roi_image, roi_mask, ref_lab, grid_data):
    """计算每个网格与参考色的 ΔE，返回矩阵和热力图"""
    h, w = roi_image.shape[:2]
    cell_size = grid_data["cell_size"]
    grid_h, grid_w = grid_data["grid_size"]

    roi_rgb = cv2.cvtColor(roi_image, cv2.COLOR_BGR2RGB)
    roi_lab = color.rgb2lab(roi_rgb / 255.0)

    delta_e_matrix = np.zeros((grid_h, grid_w))

    for i in range(grid_h):
        for j in range(grid_w):
            y1, y2 = i * cell_size, min((i + 1) * cell_size, h)
            x1, x2 = j * cell_size, min((j + 1) * cell_size, w)
            cell_lab = roi_lab[y1:y2, x1:x2]
            cell_mask = roi_mask[y1:y2, x1:x2]
            valid_pixels = cell_lab[cell_mask > 0]
            if len(valid_pixels) > 0:
                cell_mean = np.mean(valid_pixels, axis=0)
                delta_e = np.sqrt(np.sum((cell_mean - ref_lab) ** 2))
            else:
                delta_e = 0
            delta_e_matrix[i, j] = delta_e

    heatmap = cv2.applyColorMap(
        cv2.normalize(delta_e_matrix, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8),
        cv2.COLORMAP_JET
    )
    heatmap_resized = cv2.resize(heatmap, (w, h), interpolation=cv2.INTER_NEAREST)

    return {
        "delta_e_matrix": delta_e_matrix,
        "heatmap": heatmap_resized,
        "delta_e_range": [float(np.min(delta_e_matrix)), float(np.max(delta_e_matrix))]
    }


def detect_color_change(roi_image, delta_e_matrix, threshold, grid_data, mid_x=0, ref_side="left"):
    """标注变色侧超过阈值的网格，统计数量。ref_side 为基准侧，统计另一侧。"""
    h, w = roi_image.shape[:2]
    cell_size = grid_data["cell_size"]
    grid_h, grid_w = grid_data["grid_size"]

    mask = np.zeros((h, w, 3), dtype=np.uint8)
    changed_cells = 0

    for i in range(grid_h):
        for j in range(grid_w):
            x1 = j * cell_size
            # 基准是左侧 → 统计右侧（x >= mid_x）；基准是右侧 → 统计左侧（x < mid_x）
            if ref_side == "left" and x1 < mid_x:
                continue
            if ref_side == "right" and x1 >= mid_x:
                continue
            if delta_e_matrix[i, j] > threshold:
                y1, y2 = i * cell_size, min((i + 1) * cell_size, h)
                x2 = min((j + 1) * cell_size, w)
                mask[y1:y2, x1:x2] = [0, 0, 255]
                changed_cells += 1

    highlighted = cv2.addWeighted(roi_image, 0.7, mask, 0.3, 0)

    return {
        "highlighted_area": highlighted,
        "changed_cells": changed_cells,
        "total_cells": grid_h * grid_w
    }


def analyze_image(image_data, threshold=10, grid_size=10, score_weights=None):
    """主分析函数"""
    try:
        image = decode_image(image_data)

        # 步骤1: ROI 提取
        roi_data = extract_roi(image, score_weights)

        # 步骤2: 找黑洞，裁掉黑洞以上部分
        crop_data = find_hole_and_crop(roi_data["roi_image"], roi_data["roi_mask"])

        # 步骤3: 左右分割
        split_data = split_left_right(crop_data["cropped_image"], crop_data["cropped_mask"])

        # 计算左右平均 LAB
        left_lab = compute_mean_lab(split_data["left_img"], split_data["left_mask"])
        right_lab = compute_mean_lab(split_data["right_img"], split_data["right_mask"])

        # 自动判定基准侧：L 值更大（更亮）的一侧为基准色，另一侧为变色区域
        if left_lab[0] >= right_lab[0]:
            ref_lab = left_lab
            test_lab = right_lab
            ref_side = "left"
        else:
            ref_lab = right_lab
            test_lab = left_lab
            ref_side = "right"

        # 步骤4: 用基准 LAB vs 变色侧 LAB 算整体 ΔE
        overall_delta_e = float(np.sqrt(np.sum((test_lab - ref_lab) ** 2)))

        # 步骤5: 对完整裁剪图划网格，变色侧网格算 ΔE，分母为全部网格数
        full_grid_data = divide_into_grid(crop_data["cropped_image"], grid_size)
        mid_x = split_data["mid_x"]
        delta_e_data = calculate_delta_e_grid(
            crop_data["cropped_image"], crop_data["cropped_mask"], ref_lab, full_grid_data
        )
        # 变色侧：如果基准是左侧，统计右侧网格（x >= mid_x）；反之统计左侧网格（x < mid_x）
        change_data = detect_color_change(
            crop_data["cropped_image"], delta_e_data["delta_e_matrix"],
            threshold, full_grid_data, mid_x, ref_side
        )

        total_cells = full_grid_data["grid_size"][0] * full_grid_data["grid_size"][1]
        changed_ratio = change_data["changed_cells"] / max(total_cells, 1)

        return {
            "success": True,
            "steps": {
                "step1_roi_extraction": {
                    "title": "ROI 提取",
                    "description": "检测试纸轮廓，旋转矩形校正角度，提取试纸区域",
                    "images": {
                        "binary": encode_image(roi_data["binary"]),
                        "contours": encode_image(roi_data["contour_img"]),
                        "roi": encode_image(roi_data["roi_image"])
                    },
                    "data": {"roi_size": [roi_data["roi_coords"][2], roi_data["roi_coords"][3]]}
                },
                "step2_crop": {
                    "title": "黑洞定位与裁剪",
                    "description": "找到试纸上的黑洞，裁掉黑洞及其左侧区域，保留右侧有效检测区域",
                    "images": {
                        "hole_detection": encode_image(crop_data["vis_img"]),
                        "cropped": encode_image(crop_data["cropped_image"])
                    },
                    "data": {
                        "hole_right_x": crop_data["hole_right_x"],
                        "cropped_size": [crop_data["cropped_image"].shape[1], crop_data["cropped_image"].shape[0]]
                    }
                },
                "step3_split": {
                    "title": "左右分割与色差计算",
                    "description": f"从中间分为左右两部分，自动以较亮侧（{'左' if ref_side == 'left' else '右'}侧）为基准计算整体 ΔE（CIE76）",
                    "images": {
                        "split_view": encode_image(split_data["split_vis"])
                    },
                    "data": {
                        "formula": "ΔE = √((L₂-L₁)² + (a₂-a₁)² + (b₂-b₁)²)",
                        "ref_side": "左侧" if ref_side == "left" else "右侧",
                        "ref_lab": [round(v, 2) for v in ref_lab.tolist()],
                        "test_lab": [round(v, 2) for v in test_lab.tolist()],
                        "delta_e": round(overall_delta_e, 2)
                    }
                },
                "step5_color_change": {
                    "title": "网格色差与变色统计",
                    "description": f"划分网格，计算每格 ΔE，统计超过阈值 {threshold} 的网格比例",
                    "images": {
                        "grid_overlay": encode_image(full_grid_data["grid_overlay"]),
                        "heatmap": encode_image(delta_e_data["heatmap"]),
                        "highlighted_area": encode_image(change_data["highlighted_area"])
                    },
                    "data": {
                        "threshold": threshold,
                        "total_cells": total_cells,
                        "changed_cells": change_data["changed_cells"],
                        "ratio": round(changed_ratio * 100, 2)
                    }
                }
            },
            "final_results": {
                "ref_side": "左侧" if ref_side == "left" else "右侧",
                "ref_lab": [round(v, 2) for v in ref_lab.tolist()],
                "test_lab": [round(v, 2) for v in test_lab.tolist()],
                "overall_delta_e": round(overall_delta_e, 2),
                "changed_cells": change_data["changed_cells"],
                "total_cells": total_cells,
                "color_change_ratio": round(float(changed_ratio), 4),
                "threshold_used": threshold
            }
        }
    except ImageProcessingError:
        raise
    except Exception:
        raise ImageProcessingError("图像分析过程中发生未知错误，请检查图片质量后重试")
