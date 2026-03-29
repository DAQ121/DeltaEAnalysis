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
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = np.ones((3, 3), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        raise ValueError("未检测到试纸区域")

    largest_contour = max(contours, key=cv2.contourArea)

    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [largest_contour], -1, 255, -1)

    rect = cv2.minAreaRect(largest_contour)
    box = cv2.boxPoints(rect)
    box = np.int0(box)

    width = int(rect[1][0])
    height = int(rect[1][1])
    if width < height:
        width, height = height, width

    src_pts = box.astype("float32")
    dst_pts = np.array([[0, height-1], [0, 0], [width-1, 0], [width-1, height-1]], dtype="float32")
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    roi = cv2.warpPerspective(image, M, (width, height))
    roi_mask = cv2.warpPerspective(mask, M, (width, height))

    roi[roi_mask == 0] = [255, 255, 255]

    contour_img = image.copy()
    cv2.drawContours(contour_img, [box], 0, (0, 255, 0), 3)

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
    黑洞定义：试纸内部的暗色区域（灰度值 < 50）。
    """
    h, w = roi_image.shape[:2]
    gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)

    # 在试纸掩码内找暗区域
    _, hole_mask = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)
    hole_mask = cv2.bitwise_and(hole_mask, roi_mask)

    # 形态学去噪，保留较大的黑洞
    kernel = np.ones((5, 5), np.uint8)
    hole_mask = cv2.morphologyEx(hole_mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(hole_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    hole_right_x = None
    largest_hole = None
    if contours:
        largest_hole = max(contours, key=cv2.contourArea)
        x, y, wh, hh = cv2.boundingRect(largest_hole)
        # 膨胀：右边界额外加半个孔宽作为 padding，确保黑圈完全裁掉
        padding = wh // 4
        hole_right_x = min(x + wh + padding, w)

    # 可视化
    vis_img = roi_image.copy()
    if hole_right_x is not None:
        cv2.line(vis_img, (hole_right_x, 0), (hole_right_x, h), (0, 0, 255), 2)
        cv2.drawContours(vis_img, [largest_hole], -1, (0, 255, 255), 2)
        # 裁剪：保留膨胀后右边界以右
        cropped = roi_image[:, hole_right_x:]
        cropped_mask = roi_mask[:, hole_right_x:]
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


def detect_color_change(roi_image, delta_e_matrix, threshold, grid_data, mid_x=0):
    """标注右侧超过阈值的网格（x >= mid_x），统计数量"""
    h, w = roi_image.shape[:2]
    cell_size = grid_data["cell_size"]
    grid_h, grid_w = grid_data["grid_size"]

    mask = np.zeros((h, w, 3), dtype=np.uint8)
    changed_cells = 0

    for i in range(grid_h):
        for j in range(grid_w):
            x1 = j * cell_size
            # 只统计右侧网格
            if x1 < mid_x:
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


def analyze_image(image_data, threshold=10, grid_size=10):
    """主分析函数"""
    image = decode_image(image_data)

    # 步骤1: ROI 提取
    roi_data = extract_roi(image)

    # 步骤2: 找黑洞，裁掉黑洞以上部分
    crop_data = find_hole_and_crop(roi_data["roi_image"], roi_data["roi_mask"])

    # 步骤3: 左右分割
    split_data = split_left_right(crop_data["cropped_image"], crop_data["cropped_mask"])

    # 计算左右平均 LAB
    left_lab = compute_mean_lab(split_data["left_img"], split_data["left_mask"])
    right_lab = compute_mean_lab(split_data["right_img"], split_data["right_mask"])

    # 步骤4: 直接用右侧均值 LAB vs 左侧均值 LAB 算整体 ΔE
    overall_delta_e = float(np.sqrt(np.sum((right_lab - left_lab) ** 2)))

    # 步骤5: 对完整裁剪图划网格，右侧网格算 ΔE，分母为全部网格数
    full_grid_data = divide_into_grid(crop_data["cropped_image"], grid_size)
    mid_x = split_data["mid_x"]
    delta_e_data = calculate_delta_e_grid(
        crop_data["cropped_image"], crop_data["cropped_mask"], left_lab, full_grid_data
    )
    change_data = detect_color_change(
        crop_data["cropped_image"], delta_e_data["delta_e_matrix"],
        threshold, full_grid_data, mid_x
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
                "description": "从中间分为左右两部分，分别计算平均 LAB，以左侧为基准计算整体 ΔE（CIE76）",
                "images": {
                    "split_view": encode_image(split_data["split_vis"])
                },
                "data": {
                    "formula": "ΔE = √((L₂-L₁)² + (a₂-a₁)² + (b₂-b₁)²)",
                    "left_lab": [round(v, 2) for v in left_lab.tolist()],
                    "right_lab": [round(v, 2) for v in right_lab.tolist()],
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
            "left_lab": [round(v, 2) for v in left_lab.tolist()],
            "right_lab": [round(v, 2) for v in right_lab.tolist()],
            "overall_delta_e": round(overall_delta_e, 2),
            "changed_cells": change_data["changed_cells"],
            "total_cells": total_cells,
            "color_change_ratio": round(float(changed_ratio), 4),
            "threshold_used": threshold
        }
    }
