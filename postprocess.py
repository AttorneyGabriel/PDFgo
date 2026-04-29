"""后处理管线：去水印、页码标注、日期校验、行格式保护、Unicode 清理。"""
import re
from typing import List, Tuple

# ── Unicode 隐藏字符清理 ──────────────────────────────────────────
_HIDDEN_CHARS = str.maketrans({
    "​": "",  # ZWSP
    "‌": "",  # ZWNJ
    "‍": "",  # ZWJ
    "‎": "",  # LRM
    "‏": "",  # RLM
    "﻿": "",  # BOM
    "­": "",  # SOFT HYPHEN
    "‪": "", "‫": "", "‬": "", "‭": "", "‮": "",
    "⁠": "",  # WORD JOINER
    "⁦": "", "⁧": "", "⁨": "", "⁩": "",
})


def clean_unicode(text: str) -> str:
    return text.translate(_HIDDEN_CHARS)


# ── 去水印 ─────────────────────────────────────────────────────────
def remove_watermark_lines(text: str, keywords: List[str]) -> str:
    """整行包含任一水印关键词时删除该行。"""
    if not keywords:
        return text
    pats = [re.compile(re.escape(kw)) for kw in keywords]
    lines = text.split("\n")
    out = []
    for ln in lines:
        stripped = ln.strip()
        if stripped and any(p.search(stripped) for p in pats):
            continue
        out.append(ln)
    return "\n".join(out)


# ── 重复行清理（保护性行格式保护）──────────────────────────────────
def collapse_identical_repeats(text: str, threshold: int = 3) -> str:
    """连续 ≥ threshold 行完全相同 → 只保留 1 行。"""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        j = i + 1
        while j < len(lines) and lines[j] == lines[i]:
            j += 1
        if j - i >= threshold:
            out.append(lines[i])
        else:
            out.extend(lines[i:j])
        i = j
    return "\n".join(out)


# ── LaTeX 清理 ─────────────────────────────────────────────────────
_LATEX_CMDS = (
    "underline|text|mathbf|mathrm|emph|textbf|textit|textnormal|"
    "mathit|mathsf|mathtt|operatorname|overline"
)


def strip_latex(s: str) -> str:
    if not s:
        return s
    s = s.replace("\\(", "").replace("\\)", "")
    s = s.replace("\\[", "").replace("\\]", "")
    s = re.sub(r"\${1,2}([^$]*)\${1,2}", r"\1", s)
    pat = re.compile(r"\\(?:" + _LATEX_CMDS + r")\{([^{}]*)\}")
    while True:
        new = pat.sub(r"\1", s)
        if new == s:
            break
        s = new
    pat2 = re.compile(r"\\[a-zA-Z]+\{([^{}]*)\}")
    while True:
        new = pat2.sub(r"\1", s)
        if new == s:
            break
        s = new
    s = re.sub(r"\\[a-zA-Z]+\b", "", s)
    return s


# ── 空行整理 ───────────────────────────────────────────────────────
def normalize_blank_lines(text: str, max_consecutive: int = 2) -> str:
    """连续空行 > max_consecutive → 压缩到 max_consecutive。"""
    lines = text.split("\n")
    out = []
    blank_count = 0
    for ln in lines:
        if ln.strip() == "":
            blank_count += 1
            if blank_count <= max_consecutive:
                out.append(ln)
        else:
            blank_count = 0
            out.append(ln)
    return "\n".join(out)


# ── 名称/术语纠错 ──────────────────────────────────────────────────
def apply_fixes(text: str, fixes: dict) -> str:
    """按 fixes 字典做文本替换。"""
    for wrong, right in fixes.items():
        text = text.replace(wrong, right)
    return text


# ── OCR 幻觉过滤 ──────────────────────────────────────────────────
_OCR_ARTIFACTS = re.compile(
    r"文字需清晰|确保所有信息完整|检查是否有遗漏|确认所有信息符合要求"
    r"|避免模糊或变形|逐行还原|人名.*机构名.*零错误"
    r"|不要添加.*删除.*改动|印章内容用|保持原文行结构"
)


def remove_ocr_artifacts(text: str) -> str:
    """删除 OCR 模型幻觉（指令文本混入输出）。"""
    lines = text.split("\n")
    out = []
    for ln in lines:
        if _OCR_ARTIFACTS.search(ln):
            continue
        out.append(ln)
    return "\n".join(out)


# ── 日期校验 ───────────────────────────────────────────────────────
# 匹配 "XXXX年XX月XX日" 但后面没有 "XX时"
_DATE_NO_TIME = re.compile(
    r"(\d{4}年\d{1,2}月\d{1,2}日)"
    r"(?!\s*\d{1,2}[:：]?\d{0,2}\s*时)"
)


def validate_dates(text: str) -> str:
    """对执法行为日期缺时分的标注 [!缺时分]。排除出生日期、判决日期等。"""
    trigger_words = ["审讯", "笔录", "讯问", "询问", "拘留", "逮捕",
                     "传唤", "到案", "供述", "辩解", "询问时间", "讯问时间",
                     "送至", "向我宣布", "送至我所", "执行拘留", "执行逮捕"]
    exclude_words = ["出生", "判处", "出生日期", "生于"]
    lines = text.split("\n")
    out = []
    for ln in lines:
        has_trigger = any(w in ln for w in trigger_words)
        has_exclude = any(w in ln for w in exclude_words)
        if has_trigger and not has_exclude:
            new_ln = _DATE_NO_TIME.sub(r"\1 [!缺时分]", ln)
            out.append(new_ln)
        else:
            out.append(ln)
    return "\n".join(out)


# ── 页码标注 ───────────────────────────────────────────────────────
def annotate_page_number(
    pages: List[Tuple[int, int, str]],
    source_name: str = "",
) -> str:
    """pages: [(卷宗页码, PDF页码, 页内容), ...] → 合并并标注页码。"""
    parts = []
    for vol_page, pdf_page, content in pages:
        header = f"<!-- 卷宗第{vol_page}页 / PDF第{pdf_page}页 -->"
        parts.append(f"{header}\n{content}")
    return "\n\n".join(parts)


# ── 完整后处理管线 ─────────────────────────────────────────────────
def postprocess(
    text: str,
    watermark_keywords: List[str] | None = None,
    name_fixes: dict | None = None,
    term_fixes: dict | None = None,
) -> str:
    """按顺序执行全部后处理步骤。"""
    text = clean_unicode(text)
    text = strip_latex(text)
    text = remove_watermark_lines(text, watermark_keywords or [])
    text = remove_ocr_artifacts(text)
    text = collapse_identical_repeats(text, threshold=3)
    if name_fixes:
        text = apply_fixes(text, name_fixes)
    if term_fixes:
        text = apply_fixes(text, term_fixes)
    text = validate_dates(text)
    text = normalize_blank_lines(text, max_consecutive=2)
    return text
