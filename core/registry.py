# -*- coding: utf-8 -*-
"""转换器注册表（插件式架构核心）。

新增一种目标格式的步骤：
1. 在 core/converters/ 下实现 convert(src: Path, dst: Path) -> Path 函数；
2. 用 registry.register(Target(...)) 注册，界面与服务端即可自动识别，
   无需改动 app.py 和前端逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass
class Target:
    key: str                       # 唯一标识，如 "png-lossless"
    category: str                  # 分类：图片 / 文档 ...
    label: str                     # 短标签，如 "PNG / APNG"
    ext: str                       # 输出扩展名（不含点）
    source_exts: set               # 支持的来源扩展名，如 {".webp", ".png"}
    note: str                      # 质量/特性说明（展示给用户）
    convert: Optional[Callable[[Path, Path], Path]] = None
    available: bool = True         # False = 界面显示"即将支持"
    badge: str = ""                # 角标，如 "推荐"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "category": self.category,
            "label": self.label,
            "ext": self.ext,
            "note": self.note,
            "available": self.available,
            "badge": self.badge,
            "sourceExts": sorted(self.source_exts),
        }


class ConverterRegistry:
    def __init__(self) -> None:
        self._targets: dict[str, Target] = {}

    def register(self, target: Target) -> None:
        if target.key in self._targets:
            raise ValueError(f"重复注册的目标格式: {target.key}")
        self._targets[target.key] = target

    def find(self, key: str) -> Optional[Target]:
        return self._targets.get(key)

    def list_targets(self) -> list[dict]:
        return [t.to_dict() for t in self._targets.values()]

    def available_targets(self) -> list[Target]:
        return [t for t in self._targets.values() if t.available]

    def supported_source_exts(self) -> set:
        exts: set = set()
        for t in self.available_targets():
            exts |= t.source_exts
        return exts

    def convert(self, key: str, src: Path, dst: Path) -> Path:
        """执行转换。dst 是不含扩展名的目标路径，实际扩展名由目标格式决定。"""
        target = self.find(key)
        if target is None or not target.available or target.convert is None:
            raise RuntimeError(f"目标格式不可用: {key}")
        out = dst.with_suffix("." + target.ext)
        target.convert(src, out)
        return out


def unique_path(out_dir: Path, stem: str, ext: str) -> Path:
    """生成不冲突的输出路径：name.png 已存在时用 name (1).png。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate = out_dir / f"{stem}.{ext}"
    n = 1
    while candidate.exists():
        candidate = out_dir / f"{stem} ({n}).{ext}"
        n += 1
    return candidate


REGISTRY = ConverterRegistry()
