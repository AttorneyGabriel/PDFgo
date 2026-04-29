# PDFgo — 本地卷宗解析工具

## 触发条件

当用户说以下内容时触发本 skill：
- "PDFgo"、"用 PDFgo 解析"
- "OCR"、"PDF 转文字"、"扫描件识别"、"卷宗解析"、"解析 PDF"、"解析图片"
- "把 PDF 转成 Markdown"、"批量 OCR"
- "用本地 OCR 处理"、"离线 OCR"

## 一句话调用

```bash
python3 ~/.claude/skills/PDFgo/case_parser.py <输入目录> <输出目录> [--config YAML] [--types 类型] [--force]
```

---

## 一、运行环境（本机实际部署）

| 项目 | 值 |
|---|---|
| 系统 | macOS，Apple Silicon (M 系列芯片) |
| Python | 3.11.0 (`~/.pyenv/shims/python3`) |
| OCR 模型 | **GLM-OCR**（智谱 zai-org 出品），MIT 开源许可 |
| OCR 推理框架 | **mlx-vlm 0.4.5**（Apple Silicon 原生 GPU 加速） |
| 模型权重 | `~/.cache/huggingface/hub/GLM-OCR/`（2.5GB safetensors） |
| 模型来源 | HuggingFace: `zai-org/GLM-OCR` |
| OCR 服务 | `http://127.0.0.1:11500`（FastAPI + uvicorn） |
| 服务代码 | `~/.local/local-ocr/server.py` |
| 服务 Python | `~/.local/glm-ocr/.venv/bin/python3.12` |
| 进程管理 | launchd: `~/Library/LaunchAgents/com.pdfgo.local-ocr.plist`（开机自启、崩溃自动重启） |
| API 协议 | Volcengine 兼容: `POST /api/v3/chat/completions`（多模态 image_url + text） |
| ffmpeg | `imageio_ffmpeg` 内置二进制（自动调用，无需单独安装） |

### 前置条件

1. OCR 服务必须运行：`curl http://127.0.0.1:11500` 应返回 `{"service":"local-ocr","model":"GLM-OCR",...}`
2. 系统Python依赖已装（见下方清单）

---

## 二、依赖清单

### PDFgo 依赖（系统 Python 3.11，已装）

```
PyMuPDF>=1.24.0       # PDF 嵌入图提取（fitz）
Pillow>=10.0.0        # 图片处理
requests>=2.28.0      # HTTP 调用 OCR 服务
python-docx>=0.8.11   # DOCX 解析
openpyxl>=3.1.0       # XLSX 解析
faster-whisper>=1.0.0 # 音频转写（CPU, int8 量化）
imageio-ffmpeg>=0.4.0 # 视频→音轨提取（自带 ffmpeg 二进制）
PyYAML>=6.0           # 配置文件
tqdm>=4.60.0          # 进度条
```

### OCR 服务依赖（venv Python 3.12，已装）

```
mlx-vlm==0.4.5        # Apple Silicon VLM 推理框架
mlx==0.31.2           # Apple ML 框架
transformers==5.6.2   # HuggingFace 模型加载
fastapi==0.136.1      # HTTP 服务框架
uvicorn==0.46.0       # ASGI 服务器
pillow==12.2.0        # 图片处理
torch==2.11.0         # PyTorch（transformers 依赖）
```

---

## 三、支持文件类型

| 类型 | 扩展名 | 引擎 | 说明 |
|---|---|---|---|
| PDF | `.pdf` | PyMuPDF + GLM-OCR (mlx-vlm) | 提取每页最大嵌入图（避水印层），逐页 OCR |
| 图片 | `.jpg .jpeg .png .bmp .tiff .tif .webp` | GLM-OCR (mlx-vlm) | 整图送 OCR |
| Word | `.docx`（`.doc` 需先转换） | python-docx | 提取段落+表格，保留标题层级 |
| Excel | `.xlsx`（`.xls` 需先转换） | openpyxl | 每个 Sheet 提取为管道符表格 |
| 音频 | `.mp3 .wav .m4a .amr .aac .flac .ogg .wma` | faster-whisper (base, CPU) | 中文转写带时间戳 |
| 视频 | `.mp4 .avi .mov .mkv .wmv .flv .3gp` | ffmpeg 提音 + faster-whisper | 先提取音轨再转写 |

---

## 四、处理流程（PDF 为例）

```
1. PyMuPDF 打开 PDF，获取总页数，计算文件 SHA256
2. 检查进度缓存（断点续传）
3. 逐页处理：
   a. fitz 提取该页最大嵌入图（自动跳过水印文字层）
   b. 无嵌入图时降级为整页渲染
   c. 自动旋转校正（对比 PDF 元数据和图片宽高比）
   d. RGB 转换 + 像素上限压缩（20M 像素）
   e. JPEG 编码，quality 自适应（80→65→50→40），上限 9MB
   f. base64 编码 → POST 到本地 GLM-OCR 服务（带法律专用 Prompt）
   g. OCR 失败检测：若返回 `[OCR 失败: ...]` 则抛异常，该页记入 failed_pages，不标记为已完成
   h. 后处理管线（8 步，见下方）
   i. 结果写入输出目录下 `_ocr_cache/page_XXXX.txt`，仅成功页更新 progress.json 的 completed_pages
4. 合并所有页，每页标注 "--- 第X页 ---"
5. 在文件开头写入 YAML frontmatter（文件名、总页数、解析日期）
6. 输出为 .md 文件（CRLF 换行，UTF-8）
```

---

## 五、OCR Prompt（PDF/图片共用）

```
请精确提取图片中的全部文字，逐行还原。
要求：1.人名、地名、机构名必须零错误
2.日期时间精确保留到时分
3.案号、文号、法条编号精确还原
4.不要添加、删除或改动任何文字
5.印章内容用【印章：XXX】标注
6.保持原文行结构，一行对一行
```

- `max_tokens`: 16384（单页/单图最大输出 token 数，密集表格页不会截断）

---

## 六、后处理管线（postprocess.py，按顺序执行）

| 步骤 | 函数 | 作用 |
|---|---|---|
| 1 | `clean_unicode` | 清除 ZWSP/BOM/LRM 等 Unicode 隐藏字符 |
| 2 | `strip_latex` | 清除 LaTeX 公式标记（`\textbf{}`等） |
| 3 | `remove_watermark_lines` | 整行匹配水印关键词则删除该行 |
| 4 | `remove_ocr_artifacts` | 过滤 OCR 模型幻觉（模型把指令文本输出到结果里） |
| 5 | `collapse_identical_repeats` | 连续 ≥3 行完全相同只保留 1 行 |
| 6 | `apply_fixes` | 名称/术语纠错（按配置，可选） |
| 7 | `validate_dates` | 执法行为日期缺时分标 `[!缺时分]`，排除出生/判决日期 |
| 8 | `normalize_blank_lines` | 连续空行 >2 压缩为 2 行 |

### 日期校验细节

- **标注 `[!缺时分]`**：行含执法关键词（拘留/逮捕/讯问/询问/笔录/传唤/到案/送至/执行拘留/执行逮捕/送至我所/向我宣布）且日期 `XXXX年XX月XX日` 后无 `XX时` 或 `XX:XX时`
- **不标注**：行含"出生""判处""生于"时跳过

---

## 七、输出格式

- 文件名：`原名.pdf` → `原名.md`
- YAML frontmatter（文件开头）：
  ```yaml
  ---
  文件名: 原名（不含扩展名）
  总页数: 23
  解析日期: 2026-04-30
  ---
  ```
- 换行：CRLF（`\r\n`，macOS 文本编辑器兼容）
- 编码：UTF-8
- 页码标记：`--- 第X页 ---`（每页开头）
- 目录结构：保持与输入目录一致的相对路径

---

## 八、断点续传与失败重试

- 已有 `.md` 文件 > 100 字节 → 自动跳过（除非 `--force`）
- PDF 进度缓存：**输出目录**下 `{文件名}_ocr_cache/progress.json`（含文件 SHA256 校验）+ `page_XXXX.txt`（每页结果）
- **OCR 超时**：默认 180 秒（可通过环境变量 `CASE_PARSER_OCR_TIMEOUT` 调整）
- **OCR 失败页**：记入 `progress.json` 的 `failed_pages`，不加入 `completed_pages`，下次续传时自动重试
- **首页失败兜底**：第一页就失败时自动初始化 progress 再记录，不会丢失失败信息
- **图片 OCR 失败**：图片处理器失败时抛异常，由主程序统计为 `fail`，不再静默返回 `status: "ok"`
- **Whisper 模型缓存**：音频转写模型只加载一次，多文件复用
- `--force`：强制重跑，忽略已有产物和缓存

---

## 九、配置文件

默认配置 `~/.claude/skills/PDFgo/config.yaml`：

```yaml
watermark_keywords:    # 整行包含这些关键词的行会被删除
  - "示例水印文字"

name_fixes: {}         # 可选，复核后发现系统性 OCR 错误再填
term_fixes: {}         # 可选，复核后发现系统性 OCR 错误再填

date_year: "2026"      # 默认年份
exclude_dirs:          # 跳过的子目录名
  - "案件视频"

whisper_model: "base"  # faster-whisper 模型: tiny / base / small / medium
```

案件专属配置：放在输入目录下命名为 `case-config.yaml`，或用 `--config` 指定路径。

---

## 十、CLI 用法

```bash
# 基本用法
python3 ~/.claude/skills/PDFgo/case_parser.py "<案件输入目录>" "<输出目录>"

# 带案件配置
python3 ~/.claude/skills/PDFgo/case_parser.py "<输入>" "<输出>" --config case-config.yaml

# 只处理 PDF
python3 ~/.claude/skills/PDFgo/case_parser.py "<输入>" "<输出>" --types pdf

# 强制重跑
python3 ~/.claude/skills/PDFgo/case_parser.py "<输入>" "<输出>" --force
```

---

## 十一、工具文件清单

```
~/.claude/skills/PDFgo/          ← 本工具
├── case_parser.py                     ← CLI 主入口
├── postprocess.py                     ← 后处理管线（8 步）
├── config.yaml                        ← 默认配置
├── requirements.txt                   ← pip 依赖
├── skill.md                           ← 本文件
└── processors/
    ├── __init__.py
    ├── pdf.py                         ← PDF → MD（PyMuPDF 提图 + GLM-OCR 识别）
    ├── image.py                       ← 图片 → MD（GLM-OCR）
    ├── docx.py                        ← DOCX → MD（python-docx）
    ├── xlsx.py                        ← XLSX → MD（openpyxl）
    ├── audio.py                       ← 音频 → MD（faster-whisper）
    └── video.py                       ← 视频 → MD（ffmpeg 提音 + faster-whisper）

~/.local/local-ocr/                    ← OCR 服务代码
├── server.py                          ← FastAPI 服务（加载 GLM-OCR，暴露 Volcengine 兼容 API）

~/.local/glm-ocr/         ← OCR 服务运行环境
└── .venv/                             ← Python 3.12 venv（mlx-vlm, transformers, fastapi）

~/.cache/huggingface/hub/GLM-OCR/  ← GLM-OCR 模型权重（2.5GB）
├── model.safetensors
├── config.json
├── tokenizer.json
└── ...

~/Library/LaunchAgents/com.pdfgo.local-ocr.plist  ← launchd 服务配置（开机自启）
```

---

## 十二、部署说明（如需在另一台 Mac 上复现）

### 1. 下载 GLM-OCR 模型

```bash
# 方法一：huggingface-cli
pip install huggingface-hub
huggingface-cli download zai-org/GLM-OCR --local-dir ~/.cache/huggingface/hub/GLM-OCR

# 方法二：直接从 https://huggingface.co/zai-org/GLM-OCR 下载
```

模型信息：智谱 zai-org 出品，MIT 许可，0.9B 参数，支持中英法西俄德日韩多语言。

### 2. 创建 OCR 服务 venv

```bash
python3.12 -m venv ~/.local/glm-ocr/.venv
~/.local/glm-ocr/.venv/bin/pip install mlx-vlm transformers fastapi uvicorn pillow torch
```

### 3. 部署 server.py

将 `~/.local/local-ocr/server.py` 复制到目标机器相同路径。

### 4. 配置 launchd 自启

```bash
cat > ~/Library/LaunchAgents/com.pdfgo.local-ocr.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.pdfgo.local-ocr</string>
    <key>ProgramArguments</key>
    <array>
        <string>~/.local/glm-ocr/.venv/bin/python</string>
        <string>~/.local/local-ocr/server.py</string>
        <string>--host</string><string>127.0.0.1</string>
        <string>--port</string><string>11500</string>
    </array>
    <key>WorkingDirectory</key>
    <string>~/.local/local-ocr</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>LOCAL_OCR_MODEL_PATH</key>
        <string>~/.cache/huggingface/hub/GLM-OCR</string>
    </dict>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.pdfgo.local-ocr.plist
```

### 5. 安装 PDFgo 依赖

```bash
pip install -r ~/.claude/skills/PDFgo/requirements.txt
```

### 6. 验证

```bash
curl http://127.0.0.1:11500          # 应返回 {"service":"local-ocr","model":"GLM-OCR",...}
python3 ~/.claude/skills/PDFgo/case_parser.py --help
```

---

## 十三、Windows 部署（NVIDIA GPU，如 RTX 4060 Ti 8GB）

GLM-OCR 仅 0.9B 参数，8GB 显存绰绰有余。macOS 版用 mlx-vlm，Windows 改用 PyTorch + CUDA。

### 1. 安装 Python 3.12 + CUDA PyTorch

```powershell
# 安装 Python 3.12（从 python.org 下载）
# 安装 PyTorch（CUDA 12.x）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

### 2. 安装依赖

```powershell
pip install transformers accelerate fastapi uvicorn pillow
```

### 3. 下载 GLM-OCR 模型

```powershell
pip install huggingface-hub
huggingface-cli download zai-org/GLM-OCR --local-dir %USERPROFILE%\.cache\huggingface\hub\GLM-OCR
```

### 4. 创建 OCR 服务（Windows 版 server.py）

```python
# server_win.py — Windows 版 GLM-OCR 服务（PyTorch + CUDA）
import io, base64, time
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from PIL import Image
from transformers import AutoModel, AutoTokenizer

MODEL_PATH = Path.home() / ".cache/huggingface/hub/GLM-OCR"

print(f"加载模型 {MODEL_PATH} ...")
tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH), trust_remote_code=True)
model = AutoModel.from_pretrained(str(MODEL_PATH), trust_remote_code=True, device_map="cuda")
model.eval()
print("模型加载完成")

app = FastAPI()

OCR_PROMPT = (
    "请精确提取图片中的全部文字，逐行还原。\n"
    "要求：1.人名、地名、机构名必须零错误\n"
    "2.日期时间精确保留到时分\n"
    "3.案号、文号、法条编号精确还原\n"
    "4.不要添加、删除或改动任何文字\n"
    "5.印章内容用【印章：XXX】标注\n"
    "6.保持原文行结构，一行对一行"
)

@app.get("/")
def info():
    return {"service": "local-ocr", "model": "GLM-OCR", "device": "cuda"}

@app.post("/api/v3/chat/completions")
async def ocr(req: dict):
    content = req["messages"][0]["content"]
    image_b64 = None
    text_prompt = ""
    for item in content:
        if item.get("type") == "image_url":
            url = item["image_url"]["url"]
            image_b64 = url.split(",", 1)[1]
        elif item.get("type") == "text":
            text_prompt = item["text"]

    img_bytes = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    result, _ = model.chat(tokenizer, query=text_prompt, image=img, history=[], max_new_tokens=16384)

    return {
        "choices": [{"message": {"content": result}}],
        "usage": {"total_tokens": 0}
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=11500)
```

### 5. 启动服务

```powershell
python server_win.py
# 应输出：模型加载完成
# 服务运行在 http://127.0.0.1:11500
```

### 6. 安装 PDFgo 并验证

```powershell
pip install PyMuPDF Pillow requests python-docx openpyxl PyYAML
# 将 PDFgo skill 目录复制到 Windows 对应位置
python case_parser.py --help
curl http://127.0.0.1:11500
```

### 注意

- Windows 版 API 端口和协议与 macOS 版完全一致，PDFgo 客户端无需任何修改
- 如遇显存不足，在 `device_map` 后加 `torch_dtype="float16"`
- 开机自启可用 Task Scheduler 或 NSSM 注册为 Windows 服务

---

## 十四、注意事项

1. **OCR 服务必须运行**：`curl http://127.0.0.1:11500` 无响应则 PDF/图片处理失败
2. **外部卷需 Full Disk Access**：访问 `/Volumes/your-drive/` 需在系统设置 > 隐私与安全中给终端授权
3. **不要改动 OCR 服务环境**：`~/.local/local-ocr/server.py`、`~/.local/glm-ocr/.venv/`、模型权重目录
4. **不要用 `page.get_pixmap(dpi=200)` 单独渲染整页**：PDF 处理器已内置嵌入图提取优先策略
5. **所有 OCR 产物写输出目录**：不写 `/tmp/`、不写桌面
6. **macOS 原生（mlx-vlm）**：Windows/Linux 需用 PyTorch + CUDA 或 vLLM 部署 GLM-OCR，详见部署章节
