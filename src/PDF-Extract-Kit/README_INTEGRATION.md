# PDF-Extract-Kit Integration

> **This module is based on the open-source project [PDF-Extract-Kit](https://github.com/opendatalab/PDF-Extract-Kit) by OpenDataLab.**
>
> - Project: https://github.com/opendatalab/PDF-Extract-Kit
> - Models: https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0
> - License: AGPL-3.0

本目录包含 PDF-Extract-Kit 作为 git submodule，并在其基础上做了集成和增强：
- 新增图片裁剪保存、表格图片 + LaTeX 源码持久化
- 表格解析模型 (StructEqTable) 集成到解析流水线
- GPU 设备自动检测，不硬编码
- 封装为统一函数接口

---

## 运行环境

| 项目 | 版本 |
|------|------|
| Python | 3.10 |
| PyTorch | 2.3.1+cu121 |
| CUDA | 12.1 |
| GPU | 2x Tesla V100 (32GB) |
| PaddleOCR | 2.7.3 |
| PaddlePaddle | 3.3.1 |
| UniMERNet | 0.2.1 |
| DocLayout-YOLO | 0.0.4 |
| Ultralytics (YOLO) | 8.4.30 |
| StructEqTable | 0.3.3 |
| PyMuPDF | 1.27.2.2 |

### 依赖安装

```bash
pip install -r requirements.txt
```

`requirements.txt` 内容：

```
omegaconf
matplotlib
PyMuPDF
ultralytics>=8.2.85
doclayout-yolo==0.0.2
unimernet==0.2.1
paddlepaddle-gpu
paddleocr==2.7.3
struct-eqtable
lmdeploy
```

### 模型下载

模型权重从 HuggingFace 下载，存放在 `models/` 目录：

```bash
# 下载所有模型
huggingface-cli download opendatalab/PDF-Extract-Kit-1.0 \
  --include "models/Layout/YOLO/*" \
  --include "models/MFD/YOLO/*" \
  --include "models/MFR/unimernet_tiny/*" \
  --include "models/OCR/PaddleOCR/det/ch_PP-OCRv4_det/*" \
  --include "models/OCR/PaddleOCR/rec/ch_PP-OCRv4_rec/*" \
  --include "models/OCR/paddleocr/whl/cls/ch_ppocr_mobile_v2.0_cls_infer/*" \
  --include "models/TabRec/StructEqTable/*" \
  --local-dir .
```

模型列表：

| 模型 | 路径 | 用途 |
|------|------|------|
| DocLayout-YOLO | `models/Layout/YOLO/doclayout_yolo_ft.pt` | 版面检测 |
| YOLOv8 | `models/MFD/YOLO/yolo_v8_ft.pt` | 公式检测 |
| UniMERNet (tiny) | `models/MFR/unimernet_tiny/` | 公式识别 |
| PaddleOCR v4 det | `models/OCR/PaddleOCR/det/ch_PP-OCRv4_det/` | 文字检测 |
| PaddleOCR v4 rec | `models/OCR/PaddleOCR/rec/ch_PP-OCRv4_rec/` | 文字识别 |
| PaddleOCR cls | `models/OCR/paddleocr/whl/cls/ch_ppocr_mobile_v2.0_cls_infer/` | 方向分类 |
| StructEqTable | `models/TabRec/StructEqTable/` | 表格结构识别 |

---

## 接口

### `parse_pdf(pdf_path, output_dir, device=None)`

统一入口函数，完成模型加载、PDF 解析、结果持久化的全部流程。

```python
from src.pdf_parser.pdf_parse import parse_pdf

result = parse_pdf("paper.pdf", "./output")
```

**参数：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pdf_path` | `str` | (必填) | PDF 文件路径 |
| `output_dir` | `str` | (必填) | 输出目录，不存在则自动创建 |
| `device` | `str` | `None` (自动检测) | 推理设备，如 `"cuda"`, `"cuda:0"`, `"cpu"` |

**返回值：** `Dict[str, Any]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `pdf_path` | `str` | PDF 绝对路径 |
| `output_dir` | `str` | 输出目录绝对路径 |
| `markdown_path` | `str` | Markdown 文件路径 |
| `json_path` | `str` | 原始解析结果 JSON 路径 (每页 layout 检测) |
| `images_dir` | `str` | 提取图片目录 |
| `tables_dir` | `str` | 提取表格目录 |
| `image_files` | `List[str]` | 图片文件相对路径列表 |
| `table_files` | `List[str]` | 表格文件相对路径列表 (含 .png + .tex) |
| `metadata` | `dict` | 文档元数据 (title, authors 等) |
| `page_count` | `int` | PDF 页数 |
| `parse_time_ms` | `int` | 解析耗时 (毫秒) |
| `engine` | `str` | 引擎名称 (`"pdf_extract_kit"`) |
| `device` | `str` | 实际使用的设备 |

**输出目录结构：**

```
output_dir/
├── {basename}.md            # Markdown (含图片/表格路径引用)
├── {basename}.json          # 每页 layout 检测原始结果
├── images/
│   ├── page_001_fig_001.png
│   ├── page_002_fig_002.png
│   └── ...
├── tables/
│   ├── page_001_tab_001.png
│   ├── page_001_tab_001.tex
│   ├── page_005_tab_002.png
│   ├── page_005_tab_002.tex
│   └── ...
└── parse_result.json        # 结构化摘要
```

**Markdown 中的引用格式：**

```markdown
![figure_1](images/page_001_fig_001.png)

![table_1](tables/page_005_tab_001.png)

```latex
\begin{table}
...
\end{table}
```
```

---

### `PDFExtractKitEngine`

底层引擎类，支持更灵活的调用方式。

```python
from src.pdf_parser.engines.pdf_extract_kit_engine import PDFExtractKitEngine

engine = PDFExtractKitEngine(device="cuda")

# 解析并保存到目录 (含图片/表格持久化)
result = engine.parse_to_output_dir("paper.pdf", "./output")

# 解析为 ParseResult 对象 (兼容原有接口)
parse_result = engine.parse("paper.pdf")
print(parse_result.full_text)
```

---

## 解析流水线

一次 `parse_pdf` 调用依次执行以下步骤：

1. **版面检测** (DocLayout-YOLO) — 检测 title / text / figure / table / formula 等区域
2. **公式检测** (YOLOv8) — 检测行内/行间公式位置
3. **公式识别** (UniMERNet) — 将公式图片转为 LaTeX
4. **OCR** (PaddleOCR) — 文字区域识别
5. **图片裁剪** — 按检测框从 PDF 页面裁剪 figure 区域，保存为 PNG
6. **表格解析** (StructEqTable) — 按检测框裁剪 table 区域，识别为 LaTeX
7. **Markdown 组装** — 按阅读顺序合并文本/公式/图片引用/表格引用

---

## GPU 设备策略

- 默认自动检测：有 CUDA 则用 GPU，否则用 CPU
- 不硬编码 `.cuda()`，所有模型通过 `torch.device` 统一管理
- 可通过 `device` 参数手动指定，如 `"cuda:0"`, `"cuda:1"`, `"cpu"`
- 表格模型 (StructEqTable) 从配置中读取设备，与其他模型保持一致
