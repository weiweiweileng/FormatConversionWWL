# -*- coding: utf-8 -*-
"""文档类转换器（预留，本期不实现）。

Word ↔ PDF 计划在这里实现，接入方式与 image.py 完全一致：
实现 convert(src, dst) 函数后，把下面 register() 中对应 Target 的
available 改为 True（并填好 convert），界面与服务端即可自动识别，
无需改动 app.py 与前端。

推荐实现路径（按还原度排序）：
1. docx → pdf：调用本机 Microsoft Office COM（pywin32，Word 另存为 PDF），
   版式还原度最高，需要电脑装有 Office；
2. 无 Office 时：LibreOffice 无头模式 `soffice --headless --convert-to pdf`；
3. pdf → docx：没有完美方案，一般用 pdf2docx（基于 PyMuPDF）做版面重建，
   复杂表格/图形会有偏差，界面上应提示"尽力还原"。
"""
from __future__ import annotations

from pathlib import Path

from core.registry import REGISTRY, Target

DOCUMENT_SOURCE_EXTS = {".docx", ".doc", ".pdf"}


def register() -> None:
    REGISTRY.register(Target(
        key="doc-to-pdf",
        category="文档",
        label="Word → PDF",
        ext="pdf",
        source_exts={".docx", ".doc"},
        note="保留版式导出 PDF（预留）",
        convert=None,
        available=False,
        badge="即将支持",
    ))
    REGISTRY.register(Target(
        key="pdf-to-doc",
        category="文档",
        label="PDF → Word",
        ext="docx",
        source_exts={".pdf"},
        note="版面重建，尽力还原（预留）",
        convert=None,
        available=False,
        badge="即将支持",
    ))


register()
