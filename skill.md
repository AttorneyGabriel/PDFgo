# PDFgo — 本地卷宗解析 Skill

PDFgo 是一个面向律师阅卷的本地文件解析 skill。它把 PDF、扫描件、图片、Word、Excel、音频和视频材料转换为可追溯的 Markdown，方便律师复核，也方便后续智能体继续做证据目录、时间线、质证意见和阅卷摘要。

PDFgo 的输出天然适配 Obsidian、Notion、Logseq 等笔记软件和知识库工具。解析后的卷宗 Markdown 可以直接放入资料库，按案件、证据、人物、时间线建立链接，方便全文检索、双链整理、标签管理和后续智能体阅读。

PDFgo 的默认设计是**本地部署、本地解析、本地保存**。案件材料不上传到云端，不发送给第三方模型服务，不消耗云端 token。只要你使用本地 GLM-OCR 服务和本地转写工具，卷宗材料就始终留在自己的电脑里，这对律师保密义务和案件材料安全非常重要。

核心原则：

```text
本地处理
不上传卷宗
不调用云端 OCR
Markdown 知识库友好
逐页留痕
失败可重试
结论可复核
不把 OCR 当事实判断
```

---

## 保密与本地部署

律师使用 PDFgo 时，默认安全边界如下：

```text
1. 原始卷宗只从本机输入目录读取
2. OCR 请求只发送到 127.0.0.1 本地服务
3. Markdown、缓存、失败页记录只写入本机输出目录
4. 不主动连接云端 OCR、云端 LLM 或第三方 API
5. 不上传 PDF、图片、音频、视频或解析后的 Markdown
```

因此，在本地 GLM-OCR 服务正常运行的前提下，PDFgo 适合处理需要保密的律师阅卷材料。

注意：

```text
如果用户自行把 OCR 服务地址 LOCAL_OCR_URL 改成公网或第三方 API，
则不再属于 PDFgo 的默认本地保密模式。
处理真实案件材料前，应确认 LOCAL_OCR_URL 指向 127.0.0.1 或内网可信地址。
```

快速确认：

```bash
echo $LOCAL_OCR_URL
curl http://127.0.0.1:11500/health
```

`LOCAL_OCR_URL` 为空时，PDFgo 默认使用：

```text
http://127.0.0.1:11500
```

---

## 触发条件

当用户提出以下需求时，优先使用 PDFgo：

- “用 PDFgo 解析”
- “OCR”
- “PDF 转文字”
- “扫描件识别”
- “卷宗解析”
- “解析 PDF / 图片”
- “批量 OCR”
- “把卷宗转成 Markdown”
- “用本地 OCR 处理案件材料”

如果用户只是让你分析已经存在的 Markdown，不需要重新 OCR，则不要重复调用 PDFgo。

---

## 一句话调用

```bash
python3 ~/.claude/skills/PDFgo/case_parser.py "<输入目录>" "<输出目录>" [--config YAML] [--types 类型] [--force]
```

常用示例：

```bash
python3 ~/.claude/skills/PDFgo/case_parser.py "./input" "./output"
python3 ~/.claude/skills/PDFgo/case_parser.py "./input" "./output" --types pdf,image
python3 ~/.claude/skills/PDFgo/case_parser.py "./input" "./output" --force
```

---

## 适用场景

PDFgo 适合：

- 刑事卷宗扫描 PDF
- 侦查卷、文书卷、证据卷
- 讯问笔录、询问笔录、辨认笔录、搜查/扣押材料
- 起诉意见书、起诉书、判决书、鉴定意见
- 微信聊天截图、转账截图、现场照片中的文字
- 庭审录音、讯问录音、同步录音录像中的音频转写
- 后续要交给智能体阅读的案件材料 Markdown 化
- 导入 Obsidian、Notion、Logseq 等笔记/知识库工具进行案件管理

PDFgo 不负责：

- 判断证据是否合法
- 直接生成最终辩护意见
- 替代律师核对原件
- 保证 OCR 结果零错误
- 处理未转换的旧版 `.doc` / `.xls`

---

## 本机架构

```text
案件材料目录
  ↓
case_parser.py 扫描文件
  ↓
按文件类型分流
  ↓
PDF / 图片 → 本地 GLM-OCR 服务
Word / Excel → 本地结构化提取
音频 / 视频 → faster-whisper 转写
  ↓
postprocess.py 清洗与标注
  ↓
Markdown 输出 + 页级缓存 + 失败页记录
```

本机默认 OCR 服务：

```text
http://127.0.0.1:11500
```

接口：

```text
POST /api/v3/chat/completions
```

OCR 服务应兼容 OpenAI/Volcengine 风格的多模态请求：`image_url + text`。

---

## 运行环境

| 项目 | 默认值 |
|---|---|
| 系统 | macOS，Apple Silicon |
| 客户端 Python | Python 3.11+ |
| OCR 模型 | GLM-OCR |
| OCR 推理 | mlx-vlm |
| OCR 服务地址 | `http://127.0.0.1:11500` |
| 音频转写 | faster-whisper |
| 视频抽音 | imageio-ffmpeg |

基础依赖：

```text
PyMuPDF
Pillow
requests
python-docx
openpyxl
faster-whisper
imageio-ffmpeg
PyYAML
tqdm
```

安装：

```bash
pip install -r ~/.claude/skills/PDFgo/requirements.txt
```

---

## 支持文件类型

| 类型 | 扩展名 | 引擎 | 说明 |
|---|---|---|---|
| PDF | `.pdf` | PyMuPDF + GLM-OCR | 逐页 OCR，带断点续传 |
| 图片 | `.jpg .jpeg .png .bmp .tiff .tif .webp` | GLM-OCR | 整图 OCR |
| Word | `.docx` | python-docx | 提取段落和表格 |
| Excel | `.xlsx` | openpyxl | 按 Sheet 输出表格文本 |
| 音频 | `.mp3 .wav .m4a .amr .aac .flac .ogg .wma` | faster-whisper | 中文转写，带时间戳 |
| 视频 | `.mp4 .avi .mov .mkv .wmv .flv .3gp` | imageio-ffmpeg + faster-whisper | 先抽音轨，再转写 |

旧版 `.doc`、`.xls` 请先转换为 `.docx`、`.xlsx`。

---

## PDF 处理流程

PDFgo 对每个 PDF 逐页处理：

```text
1. 打开 PDF，读取页数，计算文件 SHA256
2. 检查输出目录中的 _ocr_cache/progress.json
3. 对未完成页逐页处理
4. 优先提取页面最大嵌入图，尽量避开水印文字层
5. 无嵌入图时渲染整页
6. 自动旋转校正
7. RGB 转换与图片压缩
8. 调用本地 GLM-OCR 服务
9. 检测 OCR 失败
10. 后处理清洗
11. 写入 page_XXXX.txt
12. 更新 completed_pages / failed_pages
13. 合并为 Markdown
```

PDF 输出页码标记：

```markdown
--- 第1页 ---
本页 OCR 内容

--- 第2页 ---
本页 OCR 内容
```

---

## OCR Prompt

PDF 和图片共用同一套法律 OCR prompt：

```text
请精确提取图片中的全部文字，逐行还原。
要求：1.人名、地名、机构名必须零错误
2.日期时间精确保留到时分
3.案号、文号、法条编号精确还原
4.不要添加、删除或改动任何文字
5.印章内容用【印章：XXX】标注
6.保持原文行结构，一行对一行
```

默认：

```text
max_tokens = 16384
OCR timeout = 180s
```

可通过环境变量调整超时时间：

```bash
export CASE_PARSER_OCR_TIMEOUT=300
```

---

## 后处理管线

`postprocess.py` 按顺序执行：

| 步骤 | 函数 | 用途 |
|---|---|---|
| 1 | `clean_unicode` | 清除隐藏字符 |
| 2 | `strip_latex` | 清除模型偶发 LaTeX 标记 |
| 3 | `remove_watermark_lines` | 删除配置指定的水印行 |
| 4 | `remove_ocr_artifacts` | 删除混入结果的提示词幻觉 |
| 5 | `collapse_identical_repeats` | 合并连续重复行 |
| 6 | `apply_fixes` | 应用案件级名称/术语纠错 |
| 7 | `validate_dates` | 标注执法行为日期缺时分 |
| 8 | `normalize_blank_lines` | 整理空行 |

日期缺时分标注：

```text
讯问、询问、拘留、逮捕、传唤、到案、送至、执行拘留、执行逮捕等执法行为行中，
若出现 “YYYY年M月D日” 但缺少具体时分，则标注 [!缺时分]。
```

排除：

```text
出生
生于
出生日期
判处
```

---

## 输出结构

输入：

```text
input/
  侦查卷.pdf
  图片证据/
    微信截图.png
```

输出：

```text
output/
  侦查卷.md
  侦查卷_ocr_cache/
    progress.json
    page_0001.txt
    page_0002.txt
  图片证据/
    微信截图.md
```

PDF Markdown 文件开头包含 YAML frontmatter：

```yaml
---
文件名: 侦查卷
总页数: 23
解析日期: 2026-04-30
---
```

---

## 笔记软件适配

PDFgo 输出的是普通 Markdown 文件，不绑定专有数据库，适合直接放入：

```text
Obsidian vault
Notion 页面或数据库
Logseq graph
本地文件夹知识库
RAG / Agent 文档库
```

适配优势：

```text
1. 每份材料一个 Markdown 文件，方便按案件归档
2. PDF 每页都有页码标记，便于引用和复核
3. YAML frontmatter 便于 Notion/Obsidian 属性管理
4. 输出目录保留原始相对路径，方便对应原卷宗结构
5. Markdown 可被大多数智能体、检索工具和知识库直接读取
```

推荐在 Obsidian 中按以下结构存放：

```text
案件名/
  00_案件总览.md
  01_证据目录.md
  02_时间线.md
  materials/
    侦查卷.md
    证据卷一.md
  assets/
  ocr_cache/
```

PDFgo 负责把原始材料转成 Markdown；证据目录、时间线、人物关系等二次整理，可以由律师或后续智能体继续完成。

---

## 断点续传与失败重试

PDFgo 的断点续传规则：

- 已存在 `.md` 且大于 100 字节时，默认跳过
- `--force` 会忽略已有结果和缓存，强制重跑
- PDF 页级缓存保存在输出目录下的 `{文件名}_ocr_cache/`
- 仅成功页进入 `completed_pages`
- OCR 失败页进入 `failed_pages`
- 下一次运行会自动重试失败页
- 如果第一页就失败，也会初始化 `progress.json`，不会丢失失败记录

`progress.json` 示例：

```json
{
  "pdf_hash": "abc123",
  "total_pages": 10,
  "completed_pages": [1, 2, 4],
  "failed_pages": {
    "3": "[OCR 失败: timeout]"
  },
  "status": "completed"
}
```

说明：

```text
status = completed 表示本次流程已经跑完。
是否存在失败页，以 failed_pages 和运行 stats["failed"] 为准。
```

---

## 配置文件

默认配置：

```text
~/.claude/skills/PDFgo/config.yaml
```

案件专属配置：

```text
<输入目录>/case-config.yaml
```

示例：

```yaml
watermark_keywords:
  - "示例水印文字"

name_fixes: {}
term_fixes: {}

date_year: "2026"

exclude_dirs:
  - "案件视频"

whisper_model: "base"
```

`name_fixes` 和 `term_fixes` 只用于复核后确认的系统性 OCR 错误，不要凭猜测批量替换。

---

## 使用规范

使用 PDFgo 处理案件材料时，应遵守：

```text
1. 不删除原始材料
2. 不把 OCR 结果当成最终事实
3. 不用模型猜测看不清的文字
4. 不把失败页当成成功页
5. 不提交案件材料、客户信息、OCR 结果到公开仓库
6. 对人名、日期、案号、金额、地点、印章内容进行人工复核
```

---

## 推荐工作流

第一轮只做解析：

```bash
python3 ~/.claude/skills/PDFgo/case_parser.py "./input" "./output"
```

第二轮检查失败页：

```text
查看 output/*_ocr_cache/progress.json
检查 failed_pages
必要时重跑或手动复核原图
```

第三轮再交给智能体：

```text
读取 output/*.md
生成证据目录
生成时间线
生成人物关系
生成程序违法线索表
生成低置信度复核清单
```

---

## 局限

PDFgo 当前不解决：

- 手写内容高精度识别
- 严重模糊、遮挡、歪斜材料的自动修复
- 复杂跨页表格还原
- 证据合法性判断
- 法律论证生成
- 老式 `.doc` / `.xls` 的直接解析

这些内容应由律师复核，或在后续工作流中另行处理。

---

## 部署提示

### macOS

macOS 推荐使用 GLM-OCR + `mlx-vlm` 本地服务。服务默认监听：

```text
127.0.0.1:11500
```

健康检查：

```bash
curl http://127.0.0.1:11500/health
```

应返回：

```json
{"status": "ok"}
```

### Windows / Linux

Windows 或 Linux 可以使用 PyTorch + CUDA、vLLM 或 SGLang 部署 GLM-OCR，只要对外提供同样的接口：

```text
POST /api/v3/chat/completions
```

PDFgo 客户端不关心 OCR 服务底层实现。

---

## 快速自检

运行：

```bash
python3 ~/.claude/skills/PDFgo/case_parser.py --help
curl http://127.0.0.1:11500/health
```

检查：

```text
1. 命令能显示帮助
2. OCR 服务返回 ok
3. 输入目录有可处理文件
4. 输出目录可写
```

---

## 给智能体的执行要求

当你作为智能体使用 PDFgo 时：

```text
1. 先确认 OCR 服务是否在线
2. 明确输入目录和输出目录
3. 大批量处理前，优先用 --types pdf 或少量样本试跑
4. 不要覆盖用户原始材料
5. 处理完成后报告成功、跳过、失败数量
6. 如存在 failed_pages，提醒用户复核
7. 不要声称 OCR 结果 100% 准确
```

PDFgo 的目标不是替律师判断事实，而是把案件材料转成更容易复核、检索和交给智能体阅读的 Markdown。
