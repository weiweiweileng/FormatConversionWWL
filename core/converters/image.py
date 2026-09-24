# -*- coding: utf-8 -*-
"""图像类转换器（当前仅 GIF）。

- GIF：受格式上限每帧最多 256 色，采用逐帧自适应调色板 +
  Floyd–Steinberg 误差扩散抖动（视觉无损）；透明按 128 阈值二值化
  （GIF 仅支持全透/不透明）。兼容性最好：手机相册、微信均可播放。
  动图完整保留帧数、每帧时长与循环次数。

移除的目标（如需恢复，git 历史或按 document.py 模板重新注册即可）：
- APNG / PNG：真·无损目标，因实际使用中选择 GIF 已足够而移除。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageSequence

from core.registry import REGISTRY, Target

IMAGE_SOURCE_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif"}


def _load_animation(im: Image.Image) -> tuple[list[Image.Image], list[int], int]:
    """读出全部合成帧（RGBA）、每帧时长 ms、循环次数（0 = 无限）。"""
    frames: list[Image.Image] = []
    durations: list[int] = []
    for fr in ImageSequence.Iterator(im):
        frames.append(fr.convert("RGBA"))
        durations.append(int(fr.info.get("duration") or 100))
    loop = int(im.info.get("loop", 0))
    return frames, durations, loop


def _is_animated(im: Image.Image) -> bool:
    return getattr(im, "n_frames", 1) > 1


def _rgba_to_gif_palette(frame: Image.Image) -> Image.Image:
    """RGBA 帧 → 256 色 P 模式：自适应调色板 + 抖动，透明像素占一个专用索引。"""
    has_alpha = frame.mode in ("RGBA", "LA") and frame.getchannel("A").getextrema()[0] < 255
    if not has_alpha:
        return frame.convert("RGB").quantize(colors=256, dither=Image.Dither.FLOYDSTEINBERG)

    # 255 色给画面 + 末尾 1 个槽做纯透明
    p = frame.convert("RGB").quantize(colors=255, dither=Image.Dither.FLOYDSTEINBERG)
    palette = p.getpalette("RGB")
    palette = (palette + [0, 0, 0])[: 256 * 3]
    p.putpalette(palette)
    transparent_mask = frame.getchannel("A").point(lambda a: 255 if a < 128 else 0)
    p.paste(255, mask=transparent_mask)
    p.info["transparency"] = 255
    return p


def convert_gif(src: Path, dst: Path) -> Path:
    """来源 → GIF。动图保留全部帧、时长与循环；256 色 + 抖动。"""
    im = Image.open(src)
    if _is_animated(im):
        frames, durations, loop = _load_animation(im)
        pframes = [_rgba_to_gif_palette(f) for f in frames]
        pframes[0].save(
            dst,
            save_all=True,
            append_images=pframes[1:],
            duration=durations,
            loop=loop,
            disposal=2,
            transparency=255,
        )
    else:
        _rgba_to_gif_palette(im.convert("RGBA")).save(dst, transparency=255)
    return dst


def register() -> None:
    REGISTRY.register(Target(
        key="gif",
        category="图片",
        label="GIF",
        ext="gif",
        source_exts=IMAGE_SOURCE_EXTS,
        note="256 色 + 抖动（视觉无损）· 兼容性最好，手机相册 / 微信可播；动图完整保留帧、时长与循环",
        convert=convert_gif,
    ))


register()
