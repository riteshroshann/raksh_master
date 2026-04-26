import io
import math
from typing import Optional

import cv2
import numpy as np
from PIL import Image

import structlog

from models.enums import ImageQuality

logger = structlog.get_logger()

TARGET_DPI = 300
OPTIMAL_WIDTH_PX = 2550
OPTIMAL_HEIGHT_PX = 3300


def prepare_for_ocr(image_bytes: bytes) -> np.ndarray:
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        try:
            pil_img = Image.open(io.BytesIO(image_bytes))
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception:
            raise ValueError("Unable to decode image data")

    quality = assess_quality(img)
    logger.info("image_quality_assessed", quality=quality.value, dimensions=f"{img.shape[1]}x{img.shape[0]}")

    img = normalize_resolution(img)
    img = correct_orientation(img)
    img = deskew(img)
    img = remove_noise(img)
    img = enhance_contrast(img)
    img = binarize_adaptive(img)

    return img


def assess_quality(img: np.ndarray) -> ImageQuality:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

    mean_brightness = np.mean(gray)

    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist_normalized = hist.ravel() / hist.sum()
    non_zero_bins = hist_normalized[hist_normalized > 0]
    entropy = -np.sum(non_zero_bins * np.log2(non_zero_bins))

    height, width = gray.shape
    resolution_score = min(width / OPTIMAL_WIDTH_PX, height / OPTIMAL_HEIGHT_PX, 1.0)

    if laplacian_var > 500 and 50 < mean_brightness < 200 and entropy > 6 and resolution_score > 0.8:
        return ImageQuality.EXCELLENT
    elif laplacian_var > 200 and 40 < mean_brightness < 220 and entropy > 5:
        return ImageQuality.GOOD
    elif laplacian_var > 50 and 30 < mean_brightness < 230:
        return ImageQuality.ACCEPTABLE
    elif laplacian_var > 10:
        return ImageQuality.POOR
    else:
        return ImageQuality.UNUSABLE


def normalize_resolution(img: np.ndarray) -> np.ndarray:
    height, width = img.shape[:2]

    if width < 1000:
        scale_factor = OPTIMAL_WIDTH_PX / width
        new_width = OPTIMAL_WIDTH_PX
        new_height = int(height * scale_factor)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        logger.info("resolution_normalized", original=f"{width}x{height}", new=f"{new_width}x{new_height}")

    elif width > 5000:
        scale_factor = OPTIMAL_WIDTH_PX / width
        new_width = OPTIMAL_WIDTH_PX
        new_height = int(height * scale_factor)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
        logger.info("resolution_downscaled", original=f"{width}x{height}", new=f"{new_width}x{new_height}")

    return img


def correct_orientation(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)

    if lines is None:
        return img

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = math.atan2(y2 - y1, x2 - x1) * 180 / math.pi
        if abs(angle) < 45:
            angles.append(angle)
        elif abs(angle - 90) < 45 or abs(angle + 90) < 45:
            angles.append(angle - 90 if angle > 0 else angle + 90)

    if not angles:
        return img

    median_angle = np.median(angles)

    if abs(median_angle) > 85:
        height, width = img.shape[:2]
        center = (width // 2, height // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, 90, 1.0)
        img = cv2.warpAffine(img, rotation_matrix, (height, width), borderMode=cv2.BORDER_REPLICATE)
        logger.info("orientation_corrected", rotation=90)

    return img


def deskew(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)

    if lines is None:
        return img

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = math.atan2(y2 - y1, x2 - x1) * 180 / math.pi
        if abs(angle) < 10:
            angles.append(angle)

    if not angles:
        return img

    median_angle = np.median(angles)

    if abs(median_angle) < 0.5:
        return img

    height, width = img.shape[:2]
    center = (width // 2, height // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    deskewed = cv2.warpAffine(img, rotation_matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)

    logger.info("deskew_applied", angle=round(median_angle, 2))

    return deskewed


def remove_noise(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 3:
        denoised = cv2.fastNlMeansDenoisingColored(img, None, h=10, hForColorComponents=10, templateWindowSize=7, searchWindowSize=21)
    else:
        denoised = cv2.fastNlMeansDenoising(img, None, h=10, templateWindowSize=7, searchWindowSize=21)

    kernel = np.ones((2, 2), np.uint8)
    denoised = cv2.morphologyEx(denoised, cv2.MORPH_OPEN, kernel)

    denoised = cv2.medianBlur(denoised, 3)

    return denoised


def enhance_contrast(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 3:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
    else:
        l_channel = img
        a_channel = None
        b_channel = None

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(l_channel)

    if a_channel is not None and b_channel is not None:
        enhanced_lab = cv2.merge([enhanced_l, a_channel, b_channel])
        enhanced = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
    else:
        enhanced = enhanced_l

    return enhanced


def binarize_adaptive(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 11
    )

    return binary


def remove_borders(img: np.ndarray, border_percent: float = 0.02) -> np.ndarray:
    height, width = img.shape[:2]
    top = int(height * border_percent)
    bottom = int(height * (1 - border_percent))
    left = int(width * border_percent)
    right = int(width * (1 - border_percent))

    return img[top:bottom, left:right]


def extract_text_regions(img: np.ndarray) -> list[dict]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 3))
    dilated = cv2.dilate(binary, kernel, iterations=3)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w > 50 and h > 10:
            regions.append({"x": x, "y": y, "width": w, "height": h, "area": w * h})

    regions.sort(key=lambda r: (r["y"], r["x"]))

    return regions


def detect_table_structure(img: np.ndarray) -> list[dict]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)

    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)

    table_mask = cv2.add(horizontal_lines, vertical_lines)

    contours, _ = cv2.findContours(table_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    cells = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w > 30 and h > 15:
            cells.append({"x": x, "y": y, "width": w, "height": h})

    cells.sort(key=lambda c: (c["y"], c["x"]))

    return cells


def detect_handwriting_regions(img: np.ndarray) -> list[dict]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    text_regions = extract_text_regions(img)

    handwriting_regions = []
    for region in text_regions:
        roi = binary[region["y"]:region["y"] + region["height"], region["x"]:region["x"] + region["width"]]

        if roi.size == 0:
            continue

        contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if len(contours) < 3:
            continue

        heights = [cv2.boundingRect(c)[3] for c in contours if cv2.boundingRect(c)[3] > 5]
        if not heights:
            continue

        height_variance = np.var(heights)
        mean_height = np.mean(heights)

        if mean_height > 0 and (height_variance / mean_height) > 5:
            region["is_handwritten"] = True
            handwriting_regions.append(region)

    return handwriting_regions


def preprocess_for_handwriting(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)

    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)

    sharpening_kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    sharpened = cv2.filter2D(blurred, -1, sharpening_kernel)

    return sharpened
