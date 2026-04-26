import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.preprocessing import (
    assess_quality,
    normalize_resolution,
    deskew,
    remove_noise,
    enhance_contrast,
    binarize_adaptive,
    remove_borders,
    extract_text_regions,
    detect_table_structure,
)
from models.enums import ImageQuality


def _create_test_image(width: int = 800, height: int = 600, channels: int = 3, fill: int = 200) -> np.ndarray:
    if channels == 3:
        return np.full((height, width, channels), fill, dtype=np.uint8)
    return np.full((height, width), fill, dtype=np.uint8)


def _create_noisy_image(width: int = 800, height: int = 600) -> np.ndarray:
    img = _create_test_image(width, height)
    noise = np.random.randint(0, 50, img.shape, dtype=np.uint8)
    return img + noise


def _create_text_like_image(width: int = 2550, height: int = 3300) -> np.ndarray:
    img = np.full((height, width, 3), 255, dtype=np.uint8)

    import cv2
    for y in range(200, height - 200, 50):
        cv2.line(img, (100, y), (width - 100, y), (0, 0, 0), 1)

    return img


def test_assess_quality_bright_image():
    img = _create_test_image(fill=255)
    quality = assess_quality(img)
    assert quality in (ImageQuality.ACCEPTABLE, ImageQuality.POOR, ImageQuality.UNUSABLE)


def test_assess_quality_dark_image():
    img = _create_test_image(fill=10)
    quality = assess_quality(img)
    assert quality in (ImageQuality.POOR, ImageQuality.UNUSABLE)


def test_assess_quality_uniform_image():
    img = _create_test_image(fill=128)
    quality = assess_quality(img)
    assert isinstance(quality, ImageQuality)


def test_normalize_resolution_small():
    img = _create_test_image(width=500, height=700)
    result = normalize_resolution(img)
    assert result.shape[1] == 2550


def test_normalize_resolution_large():
    img = _create_test_image(width=6000, height=8000)
    result = normalize_resolution(img)
    assert result.shape[1] == 2550


def test_normalize_resolution_already_correct():
    img = _create_test_image(width=2000, height=3000)
    result = normalize_resolution(img)
    assert result.shape == img.shape


def test_deskew_straight_image():
    img = _create_test_image()
    result = deskew(img)
    assert result.shape[:2] == img.shape[:2]


def test_remove_noise_preserves_shape():
    img = _create_noisy_image()
    result = remove_noise(img)
    assert result.shape == img.shape


def test_remove_noise_grayscale():
    img = _create_test_image(channels=1)
    result = remove_noise(img)
    assert len(result.shape) == 2


def test_enhance_contrast_color():
    img = _create_test_image()
    result = enhance_contrast(img)
    assert result.shape == img.shape


def test_enhance_contrast_grayscale():
    img = _create_test_image(channels=1)
    result = enhance_contrast(img)
    assert len(result.shape) == 2


def test_binarize_adaptive_output():
    img = _create_test_image()
    result = binarize_adaptive(img)
    assert len(result.shape) == 2
    unique_values = np.unique(result)
    assert all(v in (0, 255) for v in unique_values)


def test_remove_borders():
    img = _create_test_image(width=1000, height=1000)
    result = remove_borders(img, 0.1)
    assert result.shape[0] == 800
    assert result.shape[1] == 800


def test_extract_text_regions_empty():
    img = _create_test_image(fill=255)
    regions = extract_text_regions(img)
    assert isinstance(regions, list)


def test_detect_table_structure_empty():
    img = _create_test_image(fill=255)
    cells = detect_table_structure(img)
    assert isinstance(cells, list)
