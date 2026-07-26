#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_video.py
================================================================
GEN2 TECH 开场视频处理脚本
----------------------------------------------------------------
功能：
  1. 读取任意尺寸/方向的输入视频（例如手机竖屏视频）。
  2. 自动检测并去除画面角落的水印（例如 "wan ai"），
     优先使用文字识别(OCR)定位水印区域后做 inpaint 修复；
     若没有安装 OCR 依赖或没有识别到文字，则退化为直接对
     该角落固定区域做模糊/裁去处理，确保水印一定会被处理掉。
  3. 生成 1920x1080 的深空星空背景：纯黑色(#000000)底 + 300~500 颗
     大小 1~4 像素的星星，均匀铺满整个画布；星星只会极其缓慢地向
     右侧漂移（模拟宇宙飞船视角向右移动），并随时间做透明度正弦
     波动实现闪烁效果，背景完全铺满，不留任何黑边。
  4. 将去水印后的原始视频叠加在星空背景正中央：
       - 'fit'  模式（默认，推荐）：完整保留原视频画面内容，
         按比例缩放到画布内（不会变形、不会裁掉任何内容），
         多余部分露出星空背景，适合竖屏/非 16:9 素材。
       - 'crop' 模式：严格按需求做「居中裁剪为 16:9」，
         即先等比缩放到完全盖满 1920x1080，再从正中央裁掉
         超出画布的部分（等同于 CSS 的 object-fit: cover）。
         注意：如果原视频是竖屏，这种裁法会裁掉大部分画面内容
         （只保留中间一条横向窄带），仅建议在原片本身接近
         16:9 时使用。
  5. 保留原始视频的音轨，音画同步；若原视频没有音轨，
     则自动生成一段等长的静音音轨，保证输出文件音视频轨道完整。
  6. 输出 H.264 编码、24fps、总时长与原视频一致的 MP4 文件。

依赖安装：
  pip install opencv-python numpy moviepy
  # 如需启用「文字识别定位水印」这个更精准的检测方式（可选，非必须）：
  pip install pytesseract
  # 并确保系统已安装 tesseract-ocr 可执行程序，例如：
  #   Ubuntu/Debian:  sudo apt-get install tesseract-ocr
  #   macOS (brew):   brew install tesseract
  #   Windows:        从 https://github.com/UB-Mannheim/tesseract/wiki 下载安装
  # 没有安装 pytesseract 也完全可以运行本脚本，只是水印检测会自动
  # 退化为「固定角落裁切」的方式，仍然能把水印处理掉。

运行方法：
  python process_video.py 输入视频.mp4 输出视频.mp4
  python process_video.py 输入视频.mp4 输出视频.mp4 --mode crop   # 严格居中裁剪为16:9
  python process_video.py 输入视频.mp4 输出视频.mp4 --stars 300   # 自定义星星数量
  python process_video.py 输入视频.mp4 输出视频.mp4 --no-watermark-removal  # 跳过去水印

本脚本基于 moviepy 2.x 版本的 API 编写（import 方式与 1.x 略有不同，
1.x 版本请改用 `from moviepy.editor import ...` 并将
`clip.resized(...)` / `clip.with_audio(...)` 等新版方法名替换为
旧版的 `clip.resize(...)` / `clip.set_audio(...)`）。
================================================================
"""

import os
import sys
import argparse
import random
import math

import numpy as np
import cv2

try:
    from moviepy import (
        VideoFileClip, VideoClip, CompositeVideoClip, AudioClip
    )
except ImportError:
    print("错误：未安装 moviepy，请先运行：pip install moviepy opencv-python numpy")
    sys.exit(1)

# 尝试导入 pytesseract（可选依赖，用于更精准地定位水印文字位置）
try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


# ----------------------------------------------------------------
# 第一部分：水印检测与去除
# ----------------------------------------------------------------

def detect_watermark_bbox_via_ocr(sample_frames):
    """
    用 OCR 在若干帧的右下角区域寻找文字（水印通常是半透明文字/图标），
    返回检测到的水印外接矩形 (x0, y0, x1, y1)（像素坐标，基于原始帧尺寸），
    如果所有采样帧都没有识别到文字，返回 None。
    """
    if not HAS_OCR:
        return None

    h, w = sample_frames[0].shape[:2]
    # 只在右下角 45% 宽 x 20% 高的区域内找，既能完整覆盖"图标+文字"
    # 组合水印的常见位置，又能避免把画面中间动态的星光/特效误判成文字
    region_x0 = int(w * 0.55)
    region_y0 = int(h * 0.80)

    boxes = []
    for frame in sample_frames:
        crop = frame[region_y0:h, region_x0:w]
        if crop.size == 0:
            continue
        # 放大 3 倍再识别，小字更容易被 OCR 认出来
        pil_img = Image.fromarray(crop).resize(
            (crop.shape[1] * 3, crop.shape[0] * 3), Image.LANCZOS
        )
        data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
        for i, text in enumerate(data["text"]):
            if text.strip():
                x = data["left"][i] / 3.0 + region_x0
                y = data["top"][i] / 3.0 + region_y0
                bw = data["width"][i] / 3.0
                bh = data["height"][i] / 3.0
                boxes.append((x, y, x + bw, y + bh))

    if not boxes:
        return None

    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)

    # 四周各留一些余量，确保把水印（包括图标部分）完整包住
    pad_x = (x1 - x0) * 0.6 + 10
    pad_y = (y1 - y0) * 0.6 + 10
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(w, x1 + pad_x)
    y1 = min(h, y1 + pad_y)
    return (int(x0), int(y0), int(x1), int(y1))


def default_corner_bbox(frame_shape):
    """
    退化方案：识别不到文字时，直接给出右下角一个固定比例的矩形区域，
    「如果检测不到则裁剪该区域」——确保水印一定会被处理掉。
    """
    h, w = frame_shape[:2]
    x0 = int(w * 0.72)
    y0 = int(h * 0.86)
    x1 = w
    y1 = h
    return (x0, y0, x1, y1)


def detect_watermark_bbox(clip):
    """
    综合检测入口：优先 OCR，找不到则退化为固定角落区域。
    从原始视频里均匀取 16 帧用于检测（水印通常只在视频后半段才
    逐渐显现，取样太少容易只捕捉到文字的一部分，导致水印图标
    部分没被识别、没被去除干净，所以这里适当增加取样密度）。
    """
    n_samples = 16
    duration = clip.duration
    sample_times = [duration * i / n_samples for i in range(n_samples)]
    frames = [clip.get_frame(t) for t in sample_times]

    bbox = detect_watermark_bbox_via_ocr(frames)
    if bbox is not None:
        print(f"[水印检测] 通过 OCR 定位到水印区域: {bbox}")
        return bbox

    bbox = default_corner_bbox(frames[0].shape)
    print(f"[水印检测] 未识别到文字（可能未安装 pytesseract，或水印不含文字），"
          f"改用固定角落区域: {bbox}")
    return bbox


def remove_watermark_from_frame(frame, bbox):
    """
    用 OpenCV 的 inpaint（图像修复）算法，把 bbox 区域「抹掉」并用周围
    像素自然填补，而不是简单地涂一个纯色方块，观感更自然。
    """
    x0, y0, x1, y1 = bbox
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    mask[y0:y1, x0:x1] = 255

    # frame 是 RGB（moviepy 格式），inpaint 对通道顺序不敏感，可直接使用
    result = cv2.inpaint(frame, mask, inpaintRadius=6, flags=cv2.INPAINT_TELEA)
    return result


# ----------------------------------------------------------------
# 第二部分：深空星空背景生成
# ----------------------------------------------------------------

def make_star_field(width, height, n_stars, duration, seed=42):
    """
    生成一个 1920x1080、纯黑色(#000000)底的星空背景视频片段（VideoClip）。
    每颗星星有：
      - 只向右缓慢漂移的速度（模拟"宇宙飞船向右侧移动"的视角感，
        不会有星星往左走，也基本不做垂直方向的漂移）
      - 独立的闪烁相位与频率（用不透明度 alpha 随时间做正弦波动来
        模拟闪烁——因为背景是纯黑，用 alpha 与纯黑混合，效果等同于
        直接调节亮度，但语义上更贴近"透明度闪烁"）
      - 随机大小，范围 1~4 像素
      - 均匀铺满整张 1920x1080 画布（包括正中央视频将会覆盖的区域），
        因为合成时星空背景在下层、原始视频在上层，星星不会透到
        视频上面，只会在视频左右两侧露出来
    """
    rng = random.Random(seed)
    stars = []
    for _ in range(n_stars):
        x = rng.uniform(0, width)
        y = rng.uniform(0, height)
        # 只向右漂移：速度恒为正值，且非常慢（每秒仅几像素）
        vx = rng.uniform(0.6, 3.2)
        vy = rng.uniform(-0.15, 0.15)  # 几乎不动，只有极轻微的垂直抖动
        base_brightness = rng.uniform(150, 255)
        twinkle_freq = rng.uniform(0.15, 0.8)   # 闪烁频率（赫兹）
        phase = rng.uniform(0, 2 * math.pi)
        # 大小 1~4 像素，权重上让小星星更常见、大星星更少见，更接近真实星空
        size = rng.choices([1, 2, 3, 4], weights=[45, 30, 17, 8])[0]
        stars.append([x, y, vx, vy, base_brightness, twinkle_freq, phase, size])

    def make_frame(t):
        # 纯黑色(#000000)底图，铺满整个 1920x1080 画布，不留任何黑边之外的区域
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        for (x, y, vx, vy, base_b, freq, phase, size) in stars:
            # 位置随时间推进，向右漂移，超出画布右边界后从左边循环出现
            px = (x + vx * t) % width
            py = (y + vy * t) % height
            # 闪烁：alpha 在 0~1 之间做正弦波动，再与纯黑背景混合
            alpha = 0.5 + 0.5 * math.sin(2 * math.pi * freq * t + phase)
            alpha = 0.25 + 0.75 * alpha  # 避免完全熄灭，保留一点常亮的底光
            brightness = int(base_b * alpha)
            brightness = max(0, min(255, brightness))
            color = (brightness, brightness, brightness)
            if size <= 1:
                canvas[int(py) % height, int(px) % width] = color
            else:
                cv2.circle(canvas, (int(px), int(py)), size, color, -1, lineType=cv2.LINE_AA)
        return canvas

    return VideoClip(make_frame, duration=duration)


# ----------------------------------------------------------------
# 第三部分：主流程
# ----------------------------------------------------------------

def build_intro_video(input_path, output_path, mode="fit",
                       n_stars=400, remove_watermark=True,
                       canvas_size=(1920, 1080), out_fps=24):

    # ---- 输入校验：文件是否存在、能否被正确读取 ----
    if not os.path.isfile(input_path):
        print(f"错误：找不到输入文件 -> {input_path}")
        sys.exit(1)

    try:
        clip = VideoFileClip(input_path)
    except Exception as e:
        print(f"错误：无法读取输入视频，请确认文件格式是否正确（需为可被 ffmpeg 解码的视频，"
              f"例如 mp4/mov 等）。\n详细信息: {e}")
        sys.exit(1)

    if clip.duration is None or clip.duration <= 0:
        print("错误：读取到的视频时长为 0 或无效，请检查源文件是否损坏。")
        sys.exit(1)

    W, H = canvas_size
    duration = clip.duration
    src_w, src_h = clip.w, clip.h
    print(f"[信息] 输入视频: {input_path}  尺寸: {src_w}x{src_h}  时长: {duration:.2f}s")

    # ---- 第一步：去水印 ----
    if remove_watermark:
        bbox = detect_watermark_bbox(clip)

        def _clean_frame(get_frame, t):
            frame = get_frame(t)
            return remove_watermark_from_frame(frame, bbox)

        clip_clean = clip.transform(_clean_frame, apply_to=["video"])
        clip_clean = clip_clean.with_duration(duration)
    else:
        clip_clean = clip

    # ---- 第二步：按选定模式缩放/裁剪原视频，使其适配到 16:9 画布 ----
    if mode == "crop":
        # 严格「居中裁剪为 16:9」：先等比缩放到完全盖满画布，再从中心裁掉多余部分
        scale = max(W / src_w, H / src_h)
        resized = clip_clean.resized(scale)
        new_w, new_h = resized.w, resized.h
        x_center = new_w / 2
        y_center = new_h / 2
        fg = resized.cropped(
            x_center=x_center, y_center=y_center, width=W, height=H
        )
        fg = fg.with_position("center")
    else:
        # 'fit' 模式（推荐）：完整保留画面内容，按比例缩放到画布内，不裁剪、不变形
        scale = min(W / src_w, H / src_h)
        fg = clip_clean.resized(scale)
        fg = fg.with_position("center")

    # ---- 第三步：生成星空背景，并与前景合成 ----
    starfield = make_star_field(W, H, n_stars, duration)
    final_video = CompositeVideoClip([starfield, fg], size=(W, H))
    final_video = final_video.with_duration(duration)

    # ---- 第四步：处理音频（保留原音轨；若无音轨则生成静音音轨） ----
    if clip.audio is not None:
        final_audio = clip.audio.with_duration(duration)
        print("[信息] 已保留原始视频的音轨。")
    else:
        # 生成与视频等长的静音音轨，避免部分播放器/网页因缺少音轨而报错
        final_audio = AudioClip(lambda t: 0.0, duration=duration, fps=44100)
        print("[信息] 原始视频没有音轨，已生成等长的静音音轨。")

    final_video = final_video.with_audio(final_audio)
    final_video = final_video.with_fps(out_fps)

    # ---- 第五步：导出 H.264 编码的 MP4 ----
    print(f"[信息] 正在导出: {output_path} ({W}x{H}, {out_fps}fps, mode={mode}) ...")
    final_video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        fps=out_fps,
        preset="medium",
        threads=4,
        logger=None,
    )

    clip.close()
    print(f"[完成] 已生成新的开场视频: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="GEN2 TECH 开场视频处理：生成 1920x1080 星空背景开场视频（去水印 + 保留音频）"
    )
    parser.add_argument("input", help="输入视频文件路径，例如 gen2tech-intro.mp4")
    parser.add_argument("output", help="输出视频文件路径，例如 gen2tech-intro-1080p.mp4")
    parser.add_argument("--mode", choices=["fit", "crop"], default="fit",
                         help="fit=完整保留内容并按比例缩放(推荐，默认)；"
                              "crop=严格居中裁剪为16:9(竖屏素材会裁掉大部分内容)")
    parser.add_argument("--stars", type=int, default=400, help="星星数量，默认400颗（建议300~500范围内）")
    parser.add_argument("--no-watermark-removal", action="store_true",
                         help="跳过去水印处理（默认会自动检测并去除）")
    args = parser.parse_args()

    build_intro_video(
        args.input, args.output,
        mode=args.mode,
        n_stars=args.stars,
        remove_watermark=not args.no_watermark_removal,
    )


if __name__ == "__main__":
    main()
