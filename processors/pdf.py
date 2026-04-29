"""PDF → Markdown：用本地 GLM-OCR 服务逐页 OCR，支持断点续传。"""
import base64, hashlib, io, json, os, sys, tempfile, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from tqdm import tqdm

import fitz
import requests
from PIL import Image

try:
    from ..postprocess import postprocess
except ImportError:
    import importlib, sys, os
    _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from postprocess import postprocess, apply_fixes

OCR_SERVICE = os.environ.get("LOCAL_OCR_URL", "http://127.0.0.1:11500")
OCR_API = f"{OCR_SERVICE}/api/v3/chat/completions"
OCR_TIMEOUT = int(os.environ.get("CASE_PARSER_OCR_TIMEOUT", "180"))
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_BYTES = 9 * 1024 * 1024
MAX_RETRIES = 3


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ── 进度缓存 ───────────────────────────────────────────────────────
def _cache_dir(pdf_path: str, output_path: str) -> Path:
    return Path(output_path).parent / f"{Path(pdf_path).stem}_ocr_cache"


def load_progress(pdf_path: str, output_path: str) -> Optional[Dict]:
    p = _cache_dir(pdf_path, output_path) / "progress.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text("utf-8"))
        if data.get("pdf_hash") != _hash_file(pdf_path):
            return None
        return data
    except (json.JSONDecodeError, KeyError):
        return None


def save_progress(pdf_path: str, output_path: str, data: Dict):
    d = _cache_dir(pdf_path, output_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "progress.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def load_page(pdf_path: str, output_path: str, page_no: int) -> Optional[str]:
    f = _cache_dir(pdf_path, output_path) / f"page_{page_no:04d}.txt"
    return f.read_text("utf-8") if f.exists() else None


def save_page(pdf_path: str, output_path: str, page_no: int, text: str):
    d = _cache_dir(pdf_path, output_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"page_{page_no:04d}.txt").write_text(text, "utf-8")


# ── 图片处理 ───────────────────────────────────────────────────────
def _extract_page_image(pdf_path: str, page_no: int, dpi: int = 200) -> Tuple[Image.Image, Optional[Tuple[float, float]]]:
    """提取单页图像。优先取嵌入扫描图（避水印），否则渲染整页。"""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_no - 1]
        page_size = (page.rect.width, page.rect.height)
        embedded = page.get_images(full=True)
        if embedded:
            best = max(embedded, key=lambda x: x[2] * x[3])
            pix = fitz.Pixmap(doc, best[0])
            if pix.alpha or pix.colorspace.name not in ("DeviceRGB", "DeviceGray"):
                pix = fitz.Pixmap(fitz.csRGB, pix)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).copy()
            return img, page_size
        else:
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).copy()
            return img, page_size
    finally:
        doc.close()


def _auto_rotate(img: Image.Image, pdf_size: Optional[Tuple[float, float]]) -> Image.Image:
    w, h = img.size
    if w <= h * 1.2:
        return img
    if pdf_size and pdf_size[0] > pdf_size[1]:
        return img
    return img.rotate(90, expand=True, fillcolor="white")


def _optimize(img: Image.Image) -> Image.Image:
    """只做 RGB 转换和像素上限压缩，不做灰度。服务端有 resize。"""
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if w * h > MAX_IMAGE_PIXELS:
        scale = (MAX_IMAGE_PIXELS / (w * h)) ** 0.5
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def _to_b64(img: Image.Image) -> str:
    for q in (80, 65, 50):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True)
        if buf.tell() <= MAX_IMAGE_BYTES:
            buf.seek(0)
            return base64.b64encode(buf.read()).decode()
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=40, optimize=True)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


OCR_PROMPT = (
    "请精确提取图片中的全部文字，逐行还原。\n"
    "要求：1.人名、地名、机构名必须零错误\n"
    "2.日期时间精确保留到时分\n"
    "3.案号、文号、法条编号精确还原\n"
    "4.不要添加、删除或改动任何文字\n"
    "5.印章内容用【印章：XXX】标注\n"
    "6.保持原文行结构，一行对一行"
)


# ── OCR 调用 ───────────────────────────────────────────────────────
def _ocr_image(img: Image.Image) -> str:
    img = _optimize(img)
    b64 = _to_b64(img)
    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": OCR_PROMPT},
            ]
        }],
        "max_tokens": 16384,
    }
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(OCR_API, json=payload, timeout=OCR_TIMEOUT)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                return f"[OCR 失败: {e}]"


# ── 主入口 ─────────────────────────────────────────────────────────
def process_pdf(
    pdf_path: str,
    output_path: str,
    config: dict | None = None,
    force: bool = False,
) -> dict:
    """处理单个 PDF → Markdown。返回统计信息。"""
    config = config or {}
    wm_keywords = config.get("watermark_keywords", [])
    name_fixes = config.get("name_fixes", {})
    term_fixes = config.get("term_fixes", {})

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    progress = None if force else load_progress(pdf_path, output_path)
    completed: Set[int] = set()
    if progress:
        completed = set(progress.get("completed_pages", []))

    pages_text: Dict[int, str] = {}

    # 加载已完成页（始终用最新配置重新应用纠错）
    for pn in completed:
        t = load_page(pdf_path, output_path, pn)
        if t:
            if name_fixes or term_fixes:
                t = apply_fixes(t, {**(name_fixes or {}), **(term_fixes or {})})
            pages_text[pn] = t

    # OCR 未完成页
    pending = [p for p in range(1, total_pages + 1) if p not in completed]
    stats = {"total": total_pages, "skipped": len(completed), "ocr": 0, "failed": 0}

    stem = Path(pdf_path).stem
    pbar = tqdm(pending, desc=f"  {stem}", unit="页",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")

    for pn in pbar:
        try:
            img, pdf_size = _extract_page_image(pdf_path, pn)
            img = _auto_rotate(img, pdf_size)
            raw = _ocr_image(img)
            if raw.startswith("[OCR 失败"):
                raise RuntimeError(raw)
            clean = postprocess(raw, wm_keywords, name_fixes, term_fixes)
            pages_text[pn] = clean
            save_page(pdf_path, output_path, pn, clean)
            stats["ocr"] += 1

            # 更新进度
            completed.add(pn)
            if progress is None:
                progress = {
                    "pdf_hash": _hash_file(pdf_path),
                    "total_pages": total_pages,
                    "completed_pages": sorted(completed),
                    "failed_pages": {},
                    "status": "in_progress",
                }
            else:
                progress["completed_pages"] = sorted(completed)
            save_progress(pdf_path, output_path, progress)
        except Exception as e:
            stats["failed"] += 1
            pages_text[pn] = f"[第{pn}页处理失败: {e}]"
            pbar.write(f"  第{pn}页失败: {e}")
            # 记入 failed_pages，不加入 completed，断点续传时会重试
            if progress is None:
                progress = {
                    "pdf_hash": _hash_file(pdf_path),
                    "total_pages": total_pages,
                    "completed_pages": [],
                    "failed_pages": {},
                    "status": "in_progress",
                }
            fp = progress.get("failed_pages", {})
            fp[str(pn)] = str(e)
            progress["failed_pages"] = fp
            save_progress(pdf_path, output_path, progress)

    pbar.close()

    # 按页码排序合并，带页码标注
    parts = []
    for pn in range(1, total_pages + 1):
        text = pages_text.get(pn, f"[第{pn}页内容缺失]")
        parts.append(f"--- 第{pn}页 ---\n{text}")

    # YAML frontmatter
    from datetime import date
    frontmatter = (
        "---\n"
        f"文件名: {Path(pdf_path).stem}\n"
        f"总页数: {total_pages}\n"
        f"解析日期: {date.today().isoformat()}\n"
        "---\n\n"
    )

    Path(output_path).write_text(frontmatter + "\n\n".join(parts), "utf-8", newline="\r\n")

    # 标记完成
    if progress:
        progress["status"] = "completed"
        save_progress(pdf_path, output_path, progress)

    return stats
