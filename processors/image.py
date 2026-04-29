"""图片 → Markdown：调本地 GLM-OCR 服务。"""
import base64, io, os, sys, time
from pathlib import Path

import requests
from PIL import Image

try:
    from ..postprocess import postprocess
except ImportError:
    import sys, os
    _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from postprocess import postprocess

OCR_SERVICE = os.environ.get("LOCAL_OCR_URL", "http://127.0.0.1:11500")
OCR_API = f"{OCR_SERVICE}/api/v3/chat/completions"
MAX_RETRIES = 3


def process_image(
    image_path: str,
    output_path: str,
    config: dict | None = None,
) -> dict:
    config = config or {}
    wm = config.get("watermark_keywords", [])
    nf = config.get("name_fixes", {})
    tf = config.get("term_fixes", {})

    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()

    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": "请精确提取图片中的全部文字，逐行还原。\n要求：1.人名、地名、机构名必须零错误\n2.日期时间精确保留到时分\n3.案号、文号、法条编号精确还原\n4.不要添加、删除或改动任何文字\n5.印章内容用【印章：XXX】标注\n6.保持原文行结构，一行对一行"},
            ]
        }],
        "max_tokens": 16384,
    }

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(OCR_API, json=payload, timeout=120)
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"]
            break
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                raise RuntimeError(f"[OCR 失败: {e}]")

    text = postprocess(raw, wm, nf, tf)
    Path(output_path).write_text(text, "utf-8", newline="\r\n")
    return {"status": "ok", "chars": len(text)}
