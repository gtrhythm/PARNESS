---
name: parse-pdf
description: Parse PDF files using PDF-Extract-Kit full pipeline (layout detection, formula detection/recognition, OCR, table parsing) and return structured results
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: pdf-parsing
  project: parness
---

## What I do

解析 PDF 文件（或图片），通过完整管道输出结构化结果：

1. **Layout Detection** — 检测文档布局元素（标题、正文、图片、表格、公式等）
2. **Formula Detection** — 检测行内和行间公式位置
3. **Formula Recognition** — 将公式图片识别为 LaTeX
4. **OCR** — 提取文本内容（含位置和置信度）
5. **Table Parsing** — 将表格图片转换为 HTML

输出：结构化 JSON + Markdown + 提取的图片

## When to use me

当需要：
- "解析这个 PDF"
- "提取 PDF 内容"
- "把论文转成文本/Markdown"
- "读取 PDF 中的公式/表格/图片"
- "分析这篇论文的结构"
- 任何涉及 **读取或解析 PDF 内容** 的任务

**不要使用我的场景：**
- 只需要知道 PDF 有多少页 → 用 `python3 -c "import fitz; print(len(fitz.open('file.pdf')))"`
- 只需要下载 PDF → 用 crawler 的 pdf_agents

## Prerequisites

- 项目路径：`src/PDF-Extract-Kit/`
- 环境：系统 Python 3.10+，所有依赖已预装
- 模型权重：已存在于 `src/PDF-Extract-Kit/models/`（共 2.6 GB）
- GPU：需要 NVIDIA GPU（≥8 GB 显存），自动检测，多 GPU 时选空闲显存最多的

### 运行环境

NVIDIA GPU with CUDA support (≥8 GB VRAM recommended)

### 核心依赖

| 包 | 版本 | 用途 |
|----|------|------|
| `torch` | 2.3.1+cu121 | 推理后端 |
| `paddlepaddle` | 3.3.1 | OCR 后端 |
| `ultralytics` | 8.4.30 | YOLO 框架 |
| `doclayout-yolo` | 0.0.4 | 布局检测 |
| `unimernet` | 0.2.1 | 公式识别 |
| `paddleocr` | 2.7.3 | OCR |
| `struct-eqtable` | 0.3.3 | 表格解析 |
| `PyMuPDF` | 1.27.2 | PDF 渲染 |

### 硬件要求

| 组件 | 最低 | 推荐 |
|------|------|------|
| GPU | 1× NVIDIA ≥8 GB | ≥16 GB |
| 磁盘 | 3 GB (模型) | 5 GB |
| 内存 | 16 GB | 32 GB |

> 无 GPU 时会自动降级 CPU，但 StructEqTable（表格解析）会慢 20-50 倍，强烈不推荐。

## Quick Reference

### CLI 命令（最常用）

```bash
cd src/PDF-Extract-Kit

# 基础用法：解析 PDF
python3 scripts/parse_pdf.py <PDF路径或图片路径>

# 指定输出目录
python3 scripts/parse_pdf.py paper.pdf --output-dir ./results

# 指定 GPU（多卡环境）
python3 scripts/parse_pdf.py paper.pdf --device cuda:1

# 输出完整 JSON 到 stdout（方便管道处理）
python3 scripts/parse_pdf.py paper.pdf --verbose

# 不生成 Markdown（只要 JSON）
python3 scripts/parse_pdf.py paper.pdf --no-markdown

# 生成可视化标注图
python3 scripts/parse_pdf.py paper.pdf --visualize
```

### Python API（在 agent 中调用）

```python
import sys, os
sys.path.insert(0, 'src/PDF-Extract-Kit')
sys.path.insert(0, 'src/PDF-Extract-Kit/project/pdf2markdown/scripts')

from pdf_extract_kit.utils.device import auto_select_device, reset_device_cache
from pdf_extract_kit.utils.config_loader import load_config, initialize_tasks_and_models
from pdf2markdown import PDF2MARKDOWN
import pdf_extract_kit.tasks

# 可选：指定设备
os.environ['PEK_DEVICE'] = 'cuda:0'

# 加载配置（CWD 必须是 src/PDF-Extract-Kit）
os.chdir('src/PDF-Extract-Kit')
config = load_config('project/pdf2markdown/configs/pdf2markdown.yaml')
task_instances = initialize_tasks_and_models(config)

# 构建 pipeline
pipeline = PDF2MARKDOWN(
    layout_model=task_instances['layout_detection'].model,
    mfd_model=task_instances['formula_detection'].model,
    mfr_model=task_instances['formula_recognition'].model,
    ocr_model=task_instances['ocr'].model,
    table_model=task_instances['table_parsing'].model,
)

# 解析 PDF
results = pipeline.process(
    'path/to/paper.pdf',
    save_dir='outputs/result',
    visualize=False,
    merge2markdown=True,
    extract_images=True,
)
# results 结构：List[List[dict]]
#   外层 list：每个文件一个元素（process 支持目录输入）
#   内层 list：每页一个 dict
#   每个 dict 包含：layout_dets（检测元素列表）和 page_info（页码、尺寸）

# 访问单页结果
page_0 = results[0][0]
for det in page_0['layout_dets']:
    print(f"  {det['category_type']}: score={det['score']}")
    if 'text' in det:
        print(f"    text: {det['text']}")
    if 'latex' in det:
        print(f"    latex: {det['latex']}")
    if 'html' in det:
        print(f"    html: {det['html']}")
```

## CLI 参数说明

| 参数 | 短选项 | 默认值 | 说明 |
|------|--------|--------|------|
| `input` | — | 必填 | PDF文件、图片文件或目录路径 |
| `--output-dir` | `-o` | `outputs/parse_<timestamp>` | 输出目录 |
| `--config` | `-c` | 内置 pdf2markdown.yaml | 自定义 YAML 配置 |
| `--device` | — | 自动选择 | 计算设备（`cuda:0`/`cuda:1`/`cpu`） |
| `--no-markdown` | — | False | 跳过 Markdown 生成 |
| `--visualize` | — | False | 生成可视化标注图 |
| `--verbose` | `-v` | False | 打印完整 JSON 到 stdout |

## 输出结构

```
<output-dir>/
├── <basename>.json          # 结构化 JSON（每页所有检测元素）
├── <basename>.md            # Markdown 文本
└── figures/
    ├── <basename>_page0_fig0.png   # 提取的图片
    ├── <basename>_page1_fig0.png
    └── ...
```

### JSON 结构

```json
[
  {
    "layout_dets": [
      {
        "category_type": "title",
        "poly": [x0, y0, x1, y0, x1, y1, x0, y1],
        "score": 0.95
      },
      {
        "category_type": "text",
        "poly": [...],
        "score": 0.97,
        "text": "识别的文本内容"
      },
      {
        "category_type": "inline",
        "poly": [...],
        "score": 0.89,
        "latex": "x^2 + y^2 = r^2"
      },
      {
        "category_type": "table",
        "poly": [...],
        "score": 0.91,
        "html": "<table>...</table>"
      },
      {
        "category_type": "figure",
        "poly": [...],
        "score": 0.92,
        "img_path": "figures/paper_page0_fig0.png"
      }
    ],
    "page_info": {
      "page_no": 0,
      "height": 2339,
      "width": 1654
    }
  }
]
```

### category_type 分类

| 类别 | 说明 |
|------|------|
| `title` | 标题 |
| `plain text` | 正文段落区域 |
| `text` | OCR 识别出的具体文本 |
| `figure` | 图片 |
| `figure_caption` | 图片标题 |
| `table` | 表格 |
| `table_caption` | 表格标题 |
| `table_footnote` | 表格脚注 |
| `isolate_formula` | 行间公式（独立公式） |
| `formula_caption` | 公式编号 |
| `inline` | 行内公式 |
| `isolated` | 行间公式（检测阶段） |
| `abandon` | 废弃区域（页眉页脚等） |

## GPU 设备选择

系统自动管理 GPU 选择，通过 `pdf_extract_kit/utils/device.py`：

1. **默认**：自动选空闲显存最多的 GPU
2. **环境变量覆盖**：`PEK_DEVICE=cuda:1` 或 `PEK_DEVICE=cpu`
3. **CLI 参数覆盖**：`--device cuda:1`
4. **无 GPU 降级**：自动使用 CPU（table_parsing 会变慢）

所有 5 个模型（layout、formula_det、formula_rec、ocr、table）共享同一设备选择。

## 性能参考

基于 DDPM.pdf（25页学术论文，含大量公式）：

| 阶段 | 耗时 |
|------|------|
| 模型加载 | ~21s |
| 公式识别（241个公式） | ~65s |
| OCR | ~25s |
| 总计（含 layout + formula_det + table） | ~90s |

单张图片（论文截图）：~8s

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| `FileNotFoundError: models/...` | 确保 CWD 是 `src/PDF-Extract-Kit/` |
| `CUDA out of memory` | 用 `--device cpu` 或清理 GPU |
| `No module named 'xxx'` | 确认在系统 Python 环境中运行 |
| JSON 输出中文乱码 | JSON 文件是 UTF-8 编码，用 `ensure_ascii=False` 读取 |
| 图片提取失败 | 检查 figures/ 目录权限 |

## Workflow

### 场景 A：Agent 需要解析 PDF 获取内容

```
1. 确认 PDF 文件路径存在
2. 运行 CLI 命令：
   cd src/PDF-Extract-Kit && python3 scripts/parse_pdf.py <path> --output-dir <outdir>
3. 读取 <outdir>/<basename>.json 获取结构化结果
4. 读取 <outdir>/<basename>.md 获取 Markdown 文本
5. 将结果传递给下游 agent
```

### 场景 B：Agent 需要在 Python 中直接调用

```
1. import 并初始化 pipeline（见上方 Python API）
2. 调用 pipeline.process(pdf_path, save_dir=...)
3. 直接使用返回的 results 列表
4. 或读取 save_dir 中的 .json / .md 文件
```

### 场景 C：批量解析多个 PDF

```
1. 将 PDF 放入同一目录
2. 运行 CLI：python3 scripts/parse_pdf.py <目录路径>
3. 每个 PDF 生成独立的 .json + .md + figures/
```

## Key Principles

1. **CWD 必须是 src/PDF-Extract-Kit** — 模型路径相对于此目录
2. **首次加载慢** — 模型加载约 21s，后续推理快
3. **不要重复加载** — 如果连续解析多个 PDF，保持 pipeline 实例复用
4. **GPU 自动管理** — 无需手动设置 CUDA_VISIBLE_DEVICES
5. **JSON 是主输出** — Markdown 是便捷格式，JSON 包含完整信息（坐标、分数、所有类别）
