#!/usr/bin/env python3
"""PDFgo — 本地卷宗解析工具。

将案件目录下的 PDF、图片、DOCX、XLSX、音频、视频统一转为 Markdown。
支持断点续传、去水印、行格式保护、页码标注。

用法:
    python3 case_parser.py <输入目录> <输出目录> [选项]

选项:
    --config YAML    案件配置文件
    --types TYPE     只处理指定类型 (pdf,image,docx,xlsx,audio,video)
    --force          强制重跑，忽略已有产物
"""
import argparse, os, sys, time
from pathlib import Path

import yaml

# 让导入工作（CLI 运行时需要）
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from processors.pdf import process_pdf
from processors.image import process_image
from processors.docx import process_docx
from processors.xlsx import process_xlsx
from processors.audio import process_audio
from processors.video import process_video

# 文件扩展名 → 类型映射
EXT_MAP = {
    ".pdf": "pdf",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".bmp": "image",
    ".tiff": "image", ".tif": "image", ".webp": "image",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".amr": "audio",
    ".aac": "audio", ".flac": "audio", ".ogg": "audio", ".wma": "audio",
    ".mp4": "video", ".avi": "video", ".mov": "video", ".mkv": "video",
    ".wmv": "video", ".flv": "video", ".3gp": "video",
}

PROCESSORS = {
    "pdf": process_pdf,
    "image": process_image,
    "docx": process_docx,
    "xlsx": process_xlsx,
    "audio": process_audio,
    "video": process_video,
}


def load_config(config_path: str | None) -> dict:
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    # 尝试自动加载输入目录下的 case-config.yaml
    return {}


def scan_files(input_dir: str, exclude_dirs: list[str] | None = None) -> list[tuple[str, str]]:
    """扫描目录，返回 [(相对路径, 类型), ...]。"""
    exclude = set(exclude_dirs or [])
    results = []
    for root, dirs, files in os.walk(input_dir):
        # 排除目录
        dirs[:] = [d for d in dirs if d not in exclude]
        # 排除 _ocr_cache 目录
        dirs[:] = [d for d in dirs if not d.endswith("_ocr_cache")]

        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            ftype = EXT_MAP.get(ext)
            if ftype:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, input_dir)
                results.append((rel, ftype))
    return results


def main():
    ap = argparse.ArgumentParser(description="全案文件解析工具")
    ap.add_argument("input_dir", help="输入目录")
    ap.add_argument("output_dir", help="输出目录")
    ap.add_argument("--config", help="案件配置 YAML")
    ap.add_argument("--types", help="只处理指定类型，逗号分隔 (pdf,image,docx,xlsx,audio,video)")
    ap.add_argument("--force", action="store_true", help="强制重跑")
    args = ap.parse_args()

    input_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)

    if not os.path.isdir(input_dir):
        print(f"错误: 输入目录不存在: {input_dir}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # 加载配置
    config = load_config(args.config)
    if not config:
        auto_cfg = os.path.join(input_dir, "case-config.yaml")
        config = load_config(auto_cfg)

    exclude_dirs = config.get("exclude_dirs", [])
    filter_types = set(args.types.split(",")) if args.types else None

    # 扫描文件
    files = scan_files(input_dir, exclude_dirs)
    if not files:
        print("未找到可处理的文件。")
        return

    # 按类型分组统计
    type_counts: dict[str, int] = {}
    for _, ftype in files:
        type_counts[ftype] = type_counts.get(ftype, 0) + 1

    print(f"扫描完成: {len(files)} 个文件")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")

    # 处理
    t0 = time.time()
    stats = {"ok": 0, "skip": 0, "fail": 0}

    for rel, ftype in files:
        if filter_types and ftype not in filter_types:
            continue

        src = os.path.join(input_dir, rel)
        dst = os.path.join(output_dir, rel)
        dst_md = os.path.splitext(dst)[0] + ".md"

        # 断点续传：已有 MD > 100B 跳过
        if not args.force and os.path.exists(dst_md):
            sz = os.path.getsize(dst_md)
            if sz > 100:
                stats["skip"] += 1
                continue

        os.makedirs(os.path.dirname(dst_md), exist_ok=True)

        print(f"\n[{ftype}] {rel}")
        try:
            kwargs = {"config": config}
            if ftype == "pdf":
                kwargs["force"] = args.force
            result = PROCESSORS[ftype](src, dst_md, **kwargs)
            stats["ok"] += 1
            if isinstance(result, dict):
                print(f"  → {result}")
        except Exception as e:
            stats["fail"] += 1
            print(f"  ✗ 失败: {e}", file=sys.stderr)

    elapsed = time.time() - t0
    print(f"\n{'='*50}")
    print(f"完成: {stats['ok']} 成功, {stats['skip']} 跳过, {stats['fail']} 失败")
    print(f"耗时: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
