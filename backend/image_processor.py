import cv2
import numpy as np
from skimage import color
import base64
from io import BytesIO
from PIL import Image


def decode_image(base64_string):
    """解码base64图片"""
    img_data = base64.b64decode(base64_string.split(',')[1] if ',' in base64_string else base64_string)
    img = Image.open(BytesIO(img_data))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def encode_image(img):
    """编码图片为base64"""
    _, buffer = cv2.imencode('.png', img)
    return base64.b64encode(buffer).decode('utf-8')


def extract_roi(image):
    """步骤1: 提取ROI区域"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)  # 增加模糊强度
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = np.ones((3, 3), np.uint8)  # 减小核大小
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        raise ValueError("未检测到试纸区域")

    largest_contour = max(contours, key=cv2.contourArea)

    # 创建掩码
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [largest_contour], -1, 255, -1)

    # 使用旋转矩形摆正标签
    rect = cv2.minAreaRect(largest_contour)
    box = cv2.boxPoints(rect)
    box = np.int0(box)

    # 获取宽高
    width = int(rect[1][0])
    height = int(rect[1][1])
    if width < height:
        width, height = height, width

    # 透视变换摆正
    src_pts = box.astype("float32")
    dst_pts = np.array([[0, height-1], [0, 0], [width-1, 0], [width-1, height-1]], dtype="float32")
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    roi = cv2.warpPerspective(image, M, (width, height))
    roi_mask = cv2.warpPerspective(mask, M, (width, height))

    # 试纸外区域设为白色
    roi[roi_mask == 0] = [255, 255, 255]

    # 绘制轮廓
    contour_img = image.copy()
    cv2.drawContours(contour_img, [box], 0, (0, 255, 0), 3)

    return {
        "roi_image": roi,
        "roi_mask": roi_mask,
        "binary": binary,
        "contour_img": contour_img,
        "roi_coords": (int(rect[0][0]), int(rect[0][1]), width, height)
    }


def extract_reference_color(roi_image, roi_mask, reference_ratio=0.3, fill_holes=True):
    """步骤2: 提取参考色（CLAHE增强 + K-means聚类）"""
    h, w = roi_image.shape[:2]
    roi_original = roi_image.copy()

    # CLAHE光照校正
    lab = cv2.cvtColor(roi_original, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l)
    enhanced = cv2.merge([l_enhanced, a, b])
    roi_enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    # 提取掩码内的像素用于聚类
    valid_pixels = roi_enhanced[roi_mask > 0].reshape(-1, 3).astype(np.float32)

    if len(valid_pixels) < 100:
        ref_bgr_mean = np.array([200, 200, 200])
        lab_mean = np.array([80, 0, 0])
        best_region = None
    else:
        # K-means聚类（K=2：正常区域 vs 变色区域）
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
        _, labels, centers = cv2.kmeans(valid_pixels, 2, None, criteria, 10, cv2.KMEANS_PP_CENTERS)

        # 选择亮度更高（偏白色）的类作为正常区域
        center_gray_0 = cv2.cvtColor(np.uint8([[centers[0]]]), cv2.COLOR_BGR2GRAY)[0, 0]
        center_gray_1 = cv2.cvtColor(np.uint8([[centers[1]]]), cv2.COLOR_BGR2GRAY)[0, 0]

        normal_label = 0 if center_gray_0 > center_gray_1 else 1
        ref_bgr_mean = centers[normal_label]

        # 转换为LAB
        ref_rgb = cv2.cvtColor(np.uint8([[ref_bgr_mean]]), cv2.COLOR_BGR2RGB)
        ref_lab = color.rgb2lab(ref_rgb / 255.0)
        lab_mean = ref_lab[0, 0]

        # 找到正常区域的代表性位置用于可视化
        normal_mask = np.zeros(roi_mask.shape, dtype=np.uint8)
        normal_mask[roi_mask > 0] = (labels.flatten() == normal_label).astype(np.uint8) * 255
        contours, _ = cv2.findContours(normal_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            x, y, w_box, h_box = cv2.boundingRect(largest)
            best_region = (y, min(y + h_box, h), x, min(x + w_box, w))
        else:
            best_region = None

    # 找到黑洞并用参考色填充（可选）
    roi_filled = roi_original.copy()

    if fill_holes:
        gray_roi = cv2.cvtColor(roi_original, cv2.COLOR_BGR2GRAY)
        _, hole_mask = cv2.threshold(gray_roi, 50, 255, cv2.THRESH_BINARY_INV)
        hole_mask = cv2.bitwise_and(hole_mask, roi_mask)

        # 找到黑洞轮廓
        contours, _ = cv2.findContours(hole_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            for contour in contours:
                # 获取轮廓的中心和边界框
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])

                    # 获取轮廓的最大尺寸
                    x, y, w_box, h_box = cv2.boundingRect(contour)
                    max_size = max(w_box, h_box)

                    # 以中心为基准，填充正方形区域
                    half_size = max_size // 2 + 60  # 扩大60像素
                    y1 = max(0, cy - half_size)
                    y2 = min(h, cy + half_size)
                    x1 = max(0, cx - half_size)
                    x2 = min(w, cx + half_size)

                    roi_filled[y1:y2, x1:x2] = ref_bgr_mean

    # 可视化：标注选中的区域
    roi_with_box = roi_filled.copy()
    if best_region:
        y1, y2, x1, x2 = best_region
        cv2.rectangle(roi_with_box, (x1, y1), (x2, y2), (0, 0, 255), 2)

    ref_color_block = np.full((100, 100, 3), ref_bgr_mean, dtype=np.uint8)

    return {
        "lab_values": lab_mean.tolist(),
        "roi_with_reference": roi_with_box,
        "reference_color_block": ref_color_block,
        "reference_region": ref_color_block,
        "roi_filled": roi_filled,
        "ref_bgr_mean": ref_bgr_mean  # 返回参考色BGR值
    }


def divide_into_grid(roi_image, grid_size):
    """步骤3: 网格划分"""
    h, w = roi_image.shape[:2]

    # 自适应计算正方形网格大小
    min_dim = min(h, w)
    cell_size = min_dim // grid_size

    # 计算实际网格数量
    grid_h = h // cell_size
    grid_w = w // cell_size

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


def fill_outer_border(roi_image, roi_mask, ref_bgr_mean, grid_size, border_width=2):
    """填充ROI最外围的网格为参考色"""
    h, w = roi_image.shape[:2]
    min_dim = min(h, w)
    cell_size = min_dim // grid_size

    roi_filled = roi_image.copy()

    # 填充外围border_width圈网格
    border_pixels = cell_size * border_width

    # 上边界
    roi_filled[0:border_pixels, :] = np.where(
        roi_mask[0:border_pixels, :, np.newaxis] > 0,
        ref_bgr_mean,
        roi_filled[0:border_pixels, :]
    )

    # 下边界
    roi_filled[h-border_pixels:h, :] = np.where(
        roi_mask[h-border_pixels:h, :, np.newaxis] > 0,
        ref_bgr_mean,
        roi_filled[h-border_pixels:h, :]
    )

    # 左边界
    roi_filled[:, 0:border_pixels] = np.where(
        roi_mask[:, 0:border_pixels, np.newaxis] > 0,
        ref_bgr_mean,
        roi_filled[:, 0:border_pixels]
    )

    # 右边界
    roi_filled[:, w-border_pixels:w] = np.where(
        roi_mask[:, w-border_pixels:w, np.newaxis] > 0,
        ref_bgr_mean,
        roi_filled[:, w-border_pixels:w]
    )

    return roi_filled


def calculate_delta_e_pixelwise(roi_image, roi_mask, ref_lab):
    """计算每个像素的色差（用于轮廓检测）"""
    h, w = roi_image.shape[:2]

    roi_rgb = cv2.cvtColor(roi_image, cv2.COLOR_BGR2RGB)
    roi_lab = color.rgb2lab(roi_rgb / 255.0)

    # 计算每个像素的ΔE
    delta_e_map = np.zeros((h, w), dtype=np.float32)

    for i in range(h):
        for j in range(w):
            if roi_mask[i, j] > 0:
                pixel_lab = roi_lab[i, j]
                delta_e = np.sqrt(np.sum((pixel_lab - ref_lab) ** 2))
                delta_e_map[i, j] = delta_e

    return delta_e_map


def calculate_delta_e(roi_image, roi_mask, ref_lab, grid_data):
    """步骤4: 计算色差（网格版本）"""
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


def detect_color_change_by_contour(roi_image, roi_mask, delta_e_map, threshold):
    """基于轮廓检测变色区域"""
    h, w = roi_image.shape[:2]

    # 二值化：ΔE > 阈值的区域
    _, binary = cv2.threshold(delta_e_map, threshold, 255, cv2.THRESH_BINARY)
    binary = binary.astype(np.uint8)

    # 只保留试纸内的区域
    binary = cv2.bitwise_and(binary, roi_mask)

    # 形态学操作去噪
    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    # 检测轮廓
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 创建变色区域掩码和可视化
    change_mask = np.zeros((h, w), dtype=np.uint8)
    highlighted = roi_image.copy()

    changed_area = 0
    total_area = np.sum(roi_mask > 0)

    if contours:
        # 绘制所有轮廓
        cv2.drawContours(change_mask, contours, -1, 255, -1)
        cv2.drawContours(highlighted, contours, -1, (0, 0, 255), 2)

        # 红色半透明遮罩
        mask_overlay = np.zeros_like(roi_image)
        mask_overlay[change_mask > 0] = [0, 0, 255]
        highlighted = cv2.addWeighted(highlighted, 0.7, mask_overlay, 0.3, 0)

        changed_area = np.sum(change_mask > 0)

    return {
        "highlighted_area": highlighted,
        "change_mask": change_mask,
        "changed_area": changed_area,
        "total_area": total_area,
        "contours": contours
    }

    """步骤4: 计算色差"""
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


def detect_color_change(roi_image, delta_e_matrix, threshold, grid_data):
    """步骤5: 检测变色区域"""
    h, w = roi_image.shape[:2]
    cell_size = grid_data["cell_size"]
    grid_h, grid_w = grid_data["grid_size"]

    mask = np.zeros((h, w, 3), dtype=np.uint8)
    changed_cells = 0

    for i in range(grid_h):
        for j in range(grid_w):
            if delta_e_matrix[i, j] > threshold:
                y1, y2 = i * cell_size, min((i + 1) * cell_size, h)
                x1, x2 = j * cell_size, min((j + 1) * cell_size, w)
                mask[y1:y2, x1:x2] = [0, 0, 255]
                changed_cells += 1

    highlighted = cv2.addWeighted(roi_image, 0.7, mask, 0.3, 0)

    return {
        "highlighted_area": highlighted,
        "changed_cells": changed_cells,
        "total_cells": grid_h * grid_w
    }


def analyze_image(image_data, threshold=10, grid_size=20, reference_ratio=0.15, manual_lab=None, fill_holes=True):
    """主分析函数"""
    image = decode_image(image_data)

    roi_data = extract_roi(image)

    if manual_lab:
        # 使用手动指定的LAB值
        ref_lab = np.array(manual_lab)
        # 转换为BGR用于填充
        ref_rgb = color.lab2rgb(np.array([[ref_lab]]))
        ref_bgr = cv2.cvtColor((ref_rgb * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)[0, 0]

        roi_filled = roi_data["roi_image"].copy()
        ref_color_block = np.full((100, 100, 3), ref_bgr, dtype=np.uint8)

        ref_data = {
            "lab_values": manual_lab,
            "roi_with_reference": roi_filled,
            "reference_color_block": ref_color_block,
            "roi_filled": roi_filled,
            "ref_bgr_mean": ref_bgr
        }
    else:
        # 自动识别参考色
        ref_data = extract_reference_color(roi_data["roi_image"], roi_data["roi_mask"], reference_ratio, fill_holes)

    # 使用填充后的图像进行后续处理
    roi_filled = ref_data["roi_filled"]

    # 填充最外围两圈网格为参考色
    roi_filled = fill_outer_border(roi_filled, roi_data["roi_mask"], ref_data["ref_bgr_mean"], grid_size, border_width=2)

    grid_data = divide_into_grid(roi_filled, grid_size)
    delta_e_data = calculate_delta_e(roi_filled, roi_data["roi_mask"], np.array(ref_data["lab_values"]), grid_data)
    change_data = detect_color_change(roi_filled, delta_e_data["delta_e_matrix"], threshold, grid_data)

    changed_ratio = change_data["changed_cells"] / change_data["total_cells"]
    changed_delta_e = np.mean(delta_e_data["delta_e_matrix"][delta_e_data["delta_e_matrix"] > threshold]) if changed_ratio > 0 else 0

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
            "step2_reference_color": {
                "title": "参考色提取（K-means聚类）",
                "description": "使用K-means聚类自动识别正常区域，提取参考色",
                "images": {
                    "roi_with_reference": encode_image(ref_data["roi_with_reference"]),
                    "reference_color_block": encode_image(ref_data["reference_color_block"])
                },
                "data": {"lab_values": ref_data["lab_values"]}
            },
            "step3_grid_division": {
                "title": "网格划分",
                "description": f"将ROI划分为自适应正方形网格，每个网格独立计算色差",
                "images": {"grid_overlay": encode_image(grid_data["grid_overlay"])},
                "data": {"grid_size": grid_data["grid_size"], "total_cells": grid_data["grid_size"][0] * grid_data["grid_size"][1]}
            },
            "step4_delta_e_calculation": {
                "title": "色差计算",
                "description": "计算每个网格与参考色的ΔE值，生成热力图",
                "images": {"heatmap": encode_image(delta_e_data["heatmap"])},
                "data": {"delta_e_range": delta_e_data["delta_e_range"]}
            },
            "step5_color_change_detection": {
                "title": "变色区域识别",
                "description": f"阈值：ΔE > {threshold}，红色区域为超过阈值的变色区域",
                "images": {"highlighted_area": encode_image(change_data["highlighted_area"])},
                "data": {"threshold": threshold, "changed_cells": change_data["changed_cells"]}
            }
        },
        "final_results": {
            "overall_delta_e": float(np.mean(delta_e_data["delta_e_matrix"])),
            "changed_area_delta_e": float(changed_delta_e),
            "color_change_ratio": float(changed_ratio),
            "experiment_success": float(changed_delta_e) >= threshold,
            "threshold_used": threshold
        }
    }
