# PDF-Extract-Kit 集成技术报告

## 1. 系统概览

本模块基于开源项目 [PDF-Extract-Kit](https://github.com/opendatalab/PDF-Extract-Kit) 构建，集成了 5 个深度学习模型，组成完整的 PDF 解析流水线：

```
PDF 文件
  │
  ▼
PyMuPDF 渲染 (144 DPI)
  │
  ▼
┌─────────────────────────────────────────────────┐
│  Phase 1: 检测 (逐页)                           │
│  ┌──────────────────┐  ┌──────────────────────┐ │
│  │ DocLayout-YOLO   │  │ YOLOv8 (MFD)         │ │
│  │ 版面检测          │  │ 公式检测              │ │
│  │ 10 类元素         │  │ inline + isolated     │ │
│  └──────────────────┘  └──────────────────────┘ │
├─────────────────────────────────────────────────┤
│  Phase 2: 公式识别 (全文档批量)                   │
│  ┌──────────────────────────────────────────┐   │
│  │ UniMERNet (tiny)                          │   │
│  │ 公式图片 → LaTeX (batch=128)              │   │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│  Phase 3: OCR (逐区域, 公式遮罩)                 │
│  ┌──────────────────────────────────────────┐   │
│  │ PaddleOCR v4                              │   │
│  │ 文本区域 → 文字内容 (跳过公式区域)         │   │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│  Phase 4: 表格解析 (逐表格)                      │
│  ┌──────────────────────────────────────────┐   │
│  │ StructEqTable (InternVL2-1B)              │   │
│  │ 表格图片 → LaTeX / HTML / Markdown        │   │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│  Phase 5: 组装输出                               │
│  ├─ span→block 合并, 阅读顺序排序               │
│  ├─ 图片裁剪保存 (images/)                      │
│  ├─ 表格裁剪+LaTeX保存 (tables/)                │
│  └─ Markdown 生成 (含路径引用)                   │
└─────────────────────────────────────────────────┘
  │
  ▼
输出: .json / .md / images/ / tables/ / parse_result.json
```

---

## 2. 模型详解

### 2.1 版面检测 — DocLayout-YOLO

| 项目 | 值 |
|------|-----|
| 来源 | [DocLayout-YOLO](https://github.com/opendatalab/DocLayout-YOLO) |
| 基础架构 | YOLOv10 |
| 权重路径 | `models/Layout/YOLO/doclayout_yolo_ft.pt` |
| 输入尺寸 | 1024×1024 |
| 置信度阈值 | 0.25 |
| NMS IoU 阈值 | 0.45 |

**检测类别 (10类):**

| ID | 类别名 | 说明 |
|----|--------|------|
| 0 | `title` | 标题 |
| 1 | `plain text` | 正文文本区域 |
| 2 | `abandon` | 页眉页脚等可忽略区域 |
| 3 | `figure` | 图片 |
| 4 | `figure_caption` | 图片标题 |
| 5 | `table` | 表格 |
| 6 | `table_caption` | 表格标题 |
| 7 | `table_footnote` | 表格脚注 |
| 8 | `isolate_formula` | 独立公式 (行间) |
| 9 | `formula_caption` | 公式编号/标题 |

**工作机制:**
1. 将 PDF 页面渲染为图片 (144 DPI)
2. 输入 DocLayout-YOLO 模型，推理得到所有检测框
3. 后处理通过 torchvision NMS 去除重叠框
4. 每个检测结果输出为 `{category_type, poly, score}`

**输出格式:**
```json
{
  "category_type": "plain text",
  "poly": [xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax],
  "score": 0.98
}
```
其中 `poly` 为 8 元素数组，表示四边形的 4 个顶点坐标 (顺时针)。

---

### 2.2 公式检测 — YOLOv8 (MFD)

| 项目 | 值 |
|------|-----|
| 来源 | [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) 微调 |
| 基础架构 | YOLOv8 |
| 权重路径 | `models/MFD/YOLO/yolo_v8_ft.pt` |
| 输入尺寸 | 1280×1280 |
| 置信度阈值 | 0.25 |
| NMS IoU 阈值 | 0.45 |

**检测类别 (2类):**

| ID | 类别名 | 说明 |
|----|--------|------|
| 0 | `inline` | 行内公式 — 嵌在文本中的短公式，如 `$\alpha$` |
| 1 | `isolated` | 行间公式 — 独立成行的展示公式，如 `$$E=mc^2$$` |

**工作机制:**
1. 与版面检测并行，对同一页面图片独立推理
2. 检测结果中的公式区域会作为**遮罩**传给 OCR 模型，避免 OCR 误识别公式文字
3. 检测出的公式区域裁剪后送入公式识别模型

**输出格式:**
```json
{
  "category_type": "inline",
  "poly": [493, 962, 520, 962, 520, 982, 493, 982],
  "score": 0.77,
  "latex": ""
}
```
注意: 检测阶段 `latex` 字段为空占位，由 Phase 2 填充。

---

### 2.3 公式识别 — UniMERNet (tiny)

| 项目 | 值 |
|------|-----|
| 来源 | [UniMERNet](https://github.com/opendatalab/UniMERNet) |
| 基础架构 | Vision-to-Text Transformer (编码器-解码器) |
| 权重路径 | `models/MFR/unimernet_tiny/pytorch_model.pth` |
| 最大序列长度 | 1536 tokens |
| 视觉输入尺寸 | 192×672 (高×宽) |
| 解码策略 | 贪心解码 (temperature=0.0) |
| 批处理大小 | 128 |

**工作机制:**
1. **收集:** 从所有页面收集公式裁剪图片，统一放入 `MathDataset`
2. **预处理:** `vis_processor` 将图片 resize 到 192×672，归一化
3. **批量推理:** DataLoader 按 batch=128 喂入模型，调用 `model.generate()`
4. **后处理:** `latex_rm_whitespace()` 清理 LaTeX 中多余的空格，但保留 `\operatorname{}`、`\mathrm{}`、`\text{}`、`\mathbf{}` 等命令内部的空格
5. **回填:** 将识别结果写回对应检测框的 `latex` 字段

**输出格式:**
```json
{
  "category_type": "isolated",
  "poly": [641, 930, 1093, 930, 1093, 998, 641, 998],
  "score": 0.93,
  "latex": "H V S Q=\\frac{1}{N}\\sum_{i=1}^{N}..."
}
```

---

### 2.4 OCR — PaddleOCR v4

| 项目 | 值 |
|------|-----|
| 来源 | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) |
| 架构 | 三阶段: 文字检测 → 方向分类 → 文字识别 |
| 检测模型 | `models/OCR/PaddleOCR/det/ch_PP-OCRv4_det/` |
| 识别模型 | `models/OCR/PaddleOCR/rec/ch_PP-OCRv4_rec/` |
| 方向分类模型 | `models/OCR/paddleocr/whl/cls/ch_ppocr_mobile_v2.0_cls_infer/` |
| 语言 | `ch` (中文+英文) |
| 检测框阈值 | 0.3 |

**工作机制:**

1. **区域裁剪:** 对版面检测出的文本类区域 (`title`, `plain text`, `figure_caption`, `table_caption`, `table_footnote`)，从页面图片中裁剪出来，四周加 25px padding
2. **公式遮罩:** 公式检测结果传入 OCR，`update_det_boxes()` 计算文本框与公式框的 X 轴重叠，将文本框在公式位置处分割，确保 OCR 不处理公式区域
3. **文字检测:** PaddleOCR 检测裁剪图中的文字行
4. **框合并:** `merge_det_boxes()` 将相邻重叠的检测框合并为更大的文字区域
5. **文字识别:** 对每个检测框进行文字识别
6. **坐标还原:** 将裁剪图内的坐标转换回页面原始坐标
7. **过滤:** 低于 `drop_score` 的结果被丢弃

**输出格式:**
```json
{
  "category_type": "text",
  "poly": [126.0, 566.0, 588.0, 566.0, 588.0, 591.0, 126.0, 591.0],
  "score": 0.96,
  "text": "This paper proposes a method for..."
}
```

---

### 2.5 表格解析 — StructEqTable (InternVL2-1B)

| 项目 | 值 |
|------|-----|
| 来源 | [StructEqTable](https://github.com/UniModal4Reasoning/StructEqTable-Deploy) |
| 基础架构 | InternVL2-1B 视觉语言模型 |
| 权重路径 | `models/TabRec/StructEqTable/` (safetensors 格式) |
| 最大生成 tokens | 1024 |
| 最大生成时间 | 30 秒/表格 |
| 输出格式 | LaTeX (默认) / HTML / Markdown |

**工作机制:**
1. **裁剪:** 按版面检测的 `table` 区域从页面中裁剪表格图片
2. **保存:** 表格图片保存为 PNG
3. **推理:** 调用 `build_model()` 加载 InternVL2-1B，输入表格图片，自回归生成结构化文本
4. **输出:** 生成 LaTeX 表格代码，包含 `\begin{table}` `\begin{tabular}` 等完整结构

**输出格式 (LaTeX 示例):**
```latex
\begin{table}
\begin{center}
\begin{tabular}{lccc}
\hline
Model & IS & FID & NLL \\
\hline
EBM & 8.30 & 37.9 & \\
BigGAN & 9.22 & 14.73 & \\
Ours & 9.46 & 3.17 & $\leq$ 3.75 \\
\hline
\end{tabular}
\end{center}
\end{table}
```

---

## 3. Span-Block 合并机制

检测和 OCR 完成后，页面上的元素分为两类:

- **Block (块级元素):** 由版面/公式检测产生的区域 — `title`, `plain text`, `figure`, `table`, `isolate_formula` 等
- **Span (行内元素):** 由 OCR 和公式识别产生的文本/公式片段 — `text`, `inline`, `isolated`

### 合并流程

```
所有 spans + blocks
  │
  ▼
fill_spans_in_blocks(blocks, spans, overlap_ratio=0.6)
  │  计算 span 与 block 的面积重叠比
  │  重叠 > 60% 的 span 归入该 block
  │  已分配的 span 从池中移除
  ▼
fix_block_spans()
  │  ├─ 文本类 block: fix_text_block()
  │  │   isolated span 降级为 inline
  │  │   merge_spans_to_line() 按 Y 轴重叠分行 (阈值 80%)
  │  │   line_sort_spans_by_left_to_right() 行内按 X 排序
  │  │
  │  └─ 公式 block: fix_interline_block()
  │      保留 isolated 类型
  ▼
merge_para_with_text()
  │  遍历每个 block 的所有行和 span
  │  ├─ text span: 原文 + Markdown 特殊字符转义
  │  ├─ inline span: 包裹为 $...$
  │  ├─ isolated span: 包裹为 $$...$$
  │  │
  │  语言检测: 中文字符间不加空格, 英文加空格
  ▼
段落文本
```

---

## 4. 图片和表格持久化

此部分为集成层新增功能，不在原始 PDF-Extract-Kit 中。

### 图片提取

```
版面检测输出 figure 类别
  │
  ▼
按 poly 坐标从页面图片裁剪 (PIL.Image.crop)
  │
  ▼
保存为 images/page_{页码:03d}_fig_{序号:03d}.png
  │
  ▼
在 Markdown 中插入: ![figure_N](images/page_001_fig_001.png)
```

### 表格提取

```
版面检测输出 table 类别
  │
  ▼
裁剪表格图片 → tables/page_{页码:03d}_tab_{序号:03d}.png
  │
  ▼
StructEqTable 推理 → tables/page_{页码:03d}_tab_{序号:03d}.tex
  │
  ▼
Markdown 中插入:
  ![table_N](tables/page_005_tab_001.png)
  ```latex
  \begin{table}...
  ```
```

---

## 5. 输出格式

### 5.1 原始检测 JSON — `{basename}.json`

每页一个对象的列表:

```json
[
  {
    "page_info": {
      "page_no": 0,
      "height": 1584,
      "width": 1224
    },
    "layout_dets": [
      {
        "category_type": "title",
        "poly": [127, 137, 1096, 137, 1096, 280, 127, 280],
        "score": 0.96
      },
      {
        "category_type": "plain text",
        "poly": [107, 566, 592, 566, 592, 923, 107, 923],
        "score": 0.98
      },
      {
        "category_type": "text",
        "poly": [126.0, 566.0, 588.0, 566.0, 588.0, 591.0, 126.0, 591.0],
        "score": 0.96,
        "text": "recognized OCR text"
      },
      {
        "category_type": "inline",
        "poly": [493, 962, 520, 962, 520, 982, 493, 982],
        "score": 0.77,
        "latex": "\\alpha"
      },
      {
        "category_type": "isolated",
        "poly": [641, 930, 1093, 930, 1093, 998, 641, 998],
        "score": 0.93,
        "latex": "E=mc^2"
      },
      {
        "category_type": "figure",
        "poly": [635, 141, 1116, 141, 1116, 505, 635, 505],
        "score": 0.97
      },
      {
        "category_type": "table",
        "poly": [644, 534, 1112, 534, 1112, 651, 644, 651],
        "score": 0.98
      }
    ]
  }
]
```

### 5.2 Markdown — `{basename}.md`

```markdown
# DenoisingDiffusionProbabilisticModels

 JonathanHo ...

# Abstract

 We present high quality image synthesis...

# Introduction

 Deep generative models of all kinds...

![figure_1](images/page_001_fig_001.png)

 Figure 1: Generated samples on CelebA-HQ $256\times256$

$$
p_\theta(\mathbf{x}_{0:T}) := ...
$$

![table_1](tables/page_005_tab_001.png)

```latex
\begin{table}
\begin{center}
\begin{tabular}{lccc}
\hline
Model & IS & FID \\
\hline
...
\end{tabular}
\end{center}
\end{table}
```
```

### 5.3 解析结果摘要 — `parse_result.json`

```json
{
  "pdf_path": "/abs/path/to/paper.pdf",
  "output_dir": "/abs/path/to/output",
  "markdown_path": "/abs/path/to/output/paper.md",
  "json_path": "/abs/path/to/output/paper.json",
  "images_dir": "/abs/path/to/output/images",
  "tables_dir": "/abs/path/to/output/tables",
  "image_files": ["images/page_001_fig_001.png", ...],
  "table_files": ["tables/page_005_tab_001.png", "tables/page_005_tab_001.tex", ...],
  "metadata": {
    "title": "...",
    "authors": ["..."],
    "page_count": 25
  },
  "page_count": 25,
  "parse_time_ms": 186971,
  "engine": "pdf_extract_kit",
  "device": "cuda"
}
```

### 5.4 文件系统输出

```
output_dir/
├── paper.md                 # Markdown (含图片/表格路径引用)
├── paper.json               # 每页 layout 检测原始结果
├── parse_result.json        # 结构化摘要
├── images/
│   ├── page_001_fig_001.png
│   ├── page_002_fig_002.png
│   └── ...
└── tables/
    ├── page_005_tab_001.png
    ├── page_005_tab_001.tex
    ├── page_013_tab_002.png
    ├── page_013_tab_002.tex
    └── ...
```

---

## 6. GPU 设备管理

**策略: 不硬编码，统一管理**

```python
# 自动检测
device = "cuda" if torch.cuda.is_available() else "cpu"

# 所有模型通过 torch.device 统一分配
self.device = torch.device(device_str)
model.to(self.device)

# 支持手动指定
engine = PDFExtractKitEngine(device="cuda:0")   # 第一块卡
engine = PDFExtractKitEngine(device="cuda:1")   # 第二块卡
engine = PDFExtractKitEngine(device="cpu")      # 强制 CPU
```

涉及的修改点:
- `struct_eqtable.py`: `.cuda()` → `.to(self.device)`，device 从配置读取
- `PDFExtractKitEngine`: 所有模型通过 `_apply_device_override()` 统一设置
- `parse_pdf()`: `device` 参数透传到引擎

---

## 7. 性能参考

测试环境: 2× Tesla V100-PCIE-32GB, CUDA 12.1

| PDF | 页数 | 图片 | 表格 | 耗时 |
|-----|------|------|------|------|
| DDPM.pdf | 25 页 | 19 张 | 3 个 (含 LaTeX) | ~187s |
| 典型论文 (10-15页) | ~15 页 | ~16 张 | ~1-3 个 | ~105s |

耗时分布:
- 版面检测 + 公式检测: 每页 ~1-2s
- 公式识别 (批量): 全文档 ~45s (取决于公式数量)
- OCR: 每页 ~3-5s (取决于文字密度)
- 表格解析: 每个表格 ~5-10s

---

## 8. 项目归属

| 组件 | 项目 | 地址 | 许可证 |
|------|------|------|--------|
| PDF-Extract-Kit 框架 | OpenDataLab | https://github.com/opendatalab/PDF-Extract-Kit | AGPL-3.0 |
| DocLayout-YOLO | OpenDataLab | https://github.com/opendatalab/DocLayout-YOLO | AGPL-3.0 |
| UniMERNet | OpenDataLab | https://github.com/opendatalab/UniMERNet | MIT |
| StructEqTable | UniModal4Reasoning | https://github.com/UniModal4Reasoning/StructEqTable-Deploy | Apache-2.0 |
| PaddleOCR | PaddlePaddle | https://github.com/PaddlePaddle/PaddleOCR | Apache-2.0 |
| YOLO (Ultralytics) | Ultralytics | https://github.com/ultralytics/ultralytics | AGPL-3.0 |
| 模型权重 | HuggingFace | https://huggingface.co/opendatalab/PDF-Extract-Kit-1.0 | — |
