# -*- coding: utf-8 -*-
"""转换核心自动化测试（当前目标格式：GIF）。

生成含丰富色彩 + 透明区域的静图/动图 webp（无损编码），验证：
1. webp → GIF（动图）：帧数、每帧时长、循环次数逐项一致；透明保真；
   可见像素色差在抖动预期内；
2. webp → GIF（静图）：可正常生成单帧 GIF；
3. 注册表 API：仅 GIF 可用，文档目标正确标记为不可用，无残留的
   apng/png-static 目标。

说明：完全透明像素的 RGB 分量不参与比较——WebP 编码器依法可改写不可见
分量（任何查看器下显示完全相同），不属于质量损失。
运行：python tests/test_core.py
"""
import math
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageSequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.converters.image import convert_gif  # noqa: E402
from core.registry import REGISTRY  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
FIX.mkdir(parents=True, exist_ok=True)
FAILED = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def make_frame(i: int, w=120, h=90) -> Image.Image:
    im = Image.new("RGBA", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            r = (x * 2 + i * 9) % 256
            g = (y * 2 + i * 3) % 256
            b = int(128 + 127 * math.sin((x + i * 5) / 9)) & 0xFF
            a = 255 if (x + i * 11) % 48 < 36 else 0  # 每帧移动的透明条带
            px[x, y] = (r, g, b, a)
    return im


def build_fixtures():
    # 动图：12 帧，80ms/帧，无限循环，无损编码，色彩远超 256 色
    frames = [make_frame(i) for i in range(12)]
    anim = FIX / "anim.webp"
    frames[0].save(anim, save_all=True, append_images=frames[1:],
                   duration=80, loop=0, lossless=True)
    # 静图：无损 webp
    static = FIX / "static.webp"
    make_frame(0).save(static, lossless=True)
    return frames, anim, static


def read_frames(path: Path):
    im = Image.open(path)
    frames = [fr.convert("RGBA") for fr in ImageSequence.Iterator(im)]
    durations = [int(fr.info.get("duration") or 0) for fr in ImageSequence.Iterator(im)]
    loop = int(im.info.get("loop", -1))
    return im, frames, durations, loop


def gif_visible_error(truth: list, out: list):
    """可见像素平均通道差（0-255）与透明保真。"""
    tot = cnt = 0
    trans_ok = True
    for tf, gf in zip(truth, out):
        tb, gb = tf.tobytes(), gf.tobytes()
        ta = tf.getchannel("A").tobytes()
        ga = gf.getchannel("A").tobytes()
        for p in range(len(ta)):
            j = p * 4
            if ta[p] > 0:
                for c in range(3):
                    tot += abs(tb[j + c] - gb[j + c])
                    cnt += 1
            elif ga[p] != 0:
                trans_ok = False
    return (tot / cnt if cnt else 0), trans_ok


def main():
    _, anim, static = build_fixtures()
    _, truth, _, _ = read_frames(anim)

    # ---- 1. 动图 webp → GIF ----
    gif = FIX / "out_anim.gif"
    convert_gif(anim, gif)
    gim, gframes, gd, gloop = read_frames(gif)
    check("GIF 格式与帧数一致", gim.format == "GIF" and getattr(gim, "n_frames", 1) == 12)
    check("GIF 循环次数一致(无限)", gloop == 0, f"got {gloop}")
    check("GIF 时长一致", gd == [80] * 12, f"got {gd}")
    avg, trans_ok = gif_visible_error(truth, gframes)
    check("GIF 透明保真", trans_ok)
    # 全色域移动渐变是 256 色量化的最刁钻场景；实际图片误差远低于此阈值
    check(f"GIF 可见像素平均色差 {avg:.2f} < 10（抖动预期内）", avg < 10)

    # ---- 2. 静图 → GIF ----
    sgif = FIX / "out_static.gif"
    convert_gif(static, sgif)
    sim = Image.open(sgif)
    check("静态 GIF 可生成", sim.format == "GIF" and getattr(sim, "n_frames", 1) == 1)

    # ---- 3. 注册表 ----
    targets = REGISTRY.list_targets()
    keys = {t["key"] for t in targets}
    check("注册表仅 GIF 一个可用图片目标",
          [t["key"] for t in targets if t["available"]] == ["gif"])
    check("已移除 apng / png-static 目标", not ({"apng", "png-static"} & keys))
    check("文档目标正确标记为不可用", all(
        not t["available"] for t in targets if t["category"] == "文档"))

    print()
    if FAILED:
        print(f"结果：{len(FAILED)} 项失败 -> {FAILED}")
        sys.exit(1)
    print("结果：全部通过")
    shutil.rmtree(FIX, ignore_errors=True)


if __name__ == "__main__":
    main()
