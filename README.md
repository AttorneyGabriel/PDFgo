# PDFgo

PDFgo is a local case-file parsing tool for lawyers. It converts PDFs, scanned images, Word/Excel files, audio, and video into Markdown that can be read by humans and AI agents.

The project is designed around criminal case review workflows: page-level OCR, resumable processing, failure tracking, source-preserving Markdown, and fully local OCR through GLM-OCR on Apple Silicon.

PDFgo outputs clean Markdown, making it especially suitable for Obsidian, Notion, Logseq, and other note-taking or knowledge-base tools. Parsed case files can be dropped into a vault/database, linked with tags, searched, reviewed, and reused by AI agents without format conversion.

## Privacy First

PDFgo is designed for local deployment. By default, case materials are read from your computer, sent only to a local OCR service at `127.0.0.1`, and written back to your local output directory.

PDFgo does not upload PDFs, images, audio, video, or generated Markdown to a cloud OCR service, cloud LLM, or third-party API unless you explicitly change the OCR endpoint yourself.

This matters for lawyers: confidential case files should not leave the machine during OCR parsing.

## Highlights

- Local OCR service based on GLM-OCR and `mlx-vlm`
- Batch PDF and image OCR to Markdown
- Page-level progress cache and retry support
- Failed pages recorded in `failed_pages`
- YAML frontmatter and page markers in output Markdown
- Obsidian/Notion friendly Markdown output
- Audio/video transcription through `faster-whisper`
- Local-first: no case materials are uploaded by PDFgo itself
- No PaddleOCR/Baidu dependency in the core workflow

## Quick Start

```bash
git clone https://github.com/<your-name>/PDFgo.git
cd PDFgo
python3 --version  # requires Python 3.11+
pip install -r requirements.txt

python3 case_parser.py "<input_dir>" "<output_dir>" --types pdf
```

PDF/image OCR requires a local OCR service compatible with:

```text
POST http://127.0.0.1:11500/api/v3/chat/completions
```

See [skill.md](skill.md) for the full deployment notes.

## Supported Inputs

| Type | Extensions | Engine |
|---|---|---|
| PDF | `.pdf` | PyMuPDF + local GLM-OCR service |
| Images | `.jpg .jpeg .png .bmp .tiff .tif .webp` | local GLM-OCR service |
| Word | `.docx` | python-docx |
| Excel | `.xlsx` | openpyxl |
| Audio | `.mp3 .wav .m4a .amr .aac .flac .ogg .wma` | faster-whisper |
| Video | `.mp4 .avi .mov .mkv .wmv .flv .3gp` | imageio-ffmpeg + faster-whisper |

Legacy `.doc` and `.xls` files should be converted to `.docx` and `.xlsx` first.

## Basic Usage

```bash
python3 --version  # requires Python 3.11+
python3 case_parser.py "<case_materials>" "<markdown_output>"
python3 case_parser.py "<case_materials>" "<markdown_output>" --types pdf,image
python3 case_parser.py "<case_materials>" "<markdown_output>" --force
```

For a case-specific config, add `case-config.yaml` to the input directory:

```yaml
watermark_keywords:
  - "example watermark"

name_fixes: {}
term_fixes: {}
date_year: "2026"
exclude_dirs:
  - "videos"
whisper_model: "base"
```

## Output

PDF output includes YAML frontmatter and page markers:

```markdown
---
文件名: example
总页数: 23
解析日期: 2026-04-30
---

--- 第1页 ---
...
```

For PDFs, progress is cached under the output directory in:

```text
<file_name>_ocr_cache/
  progress.json
  page_0001.txt
```

Failed OCR pages are recorded in `progress.json` and are retried on the next run.

## Privacy

PDFgo is intended for local processing. Do not commit case materials, generated OCR output, client documents, or configuration containing private names. The `.gitignore` file excludes common case material formats by default.

## License

MIT
