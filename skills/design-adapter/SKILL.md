---
name: design-adapter
description: Design a new adapter by analyzing upstream/downstream specs, auto-generating input/output contracts, YAML fragments, and skeleton code
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: adapter-design
  project: parness
---

## What I do

根据上下游 adapter 的 SPEC 自动推导新 adapter 的输入输出契约，生成骨架代码和 YAML 配置片段。

## When to use me

- 设计新 adapter 时
- 需要在两个已有 adapter 之间插入新 adapter 时
- 用户要求"创建一个新模块"、"设计一个 adapter"

## How to use

```bash
# 指定上下游
python scripts/design_adapter.py --name paper_reviewer --upstream paper_writer --downstream paper_editor

# 只有上游
python scripts/design_adapter.py --name paper_reviewer --upstream paper_writer

# 只有下游
python scripts/design_adapter.py --name paper_reviewer --downstream paper_editor

# 无上下游（从零开始）
python scripts/design_adapter.py --name my_new_adapter
```

## Output

JSON 格式，包含 4 个部分：

```json
{
  "spec": {
    "module": "paper_reviewer",
    "input_contract": {
      "draft": {"type": "dict", "required": false, "_source": "output.paper_writer.draft"},
    },
    "output_contract": {
      "review_comments": {"type": "list", "_consumed_by": "paper_editor.review_comments"},
    }
  },
  "yaml_fragment": {
    "id": "paper_reviewer",
    "module": "paper_reviewer",
    "depends_on": ["paper_writer"],
    "input_mapping": {"draft": "output.paper_writer.draft"},
    "output_mapping": {"review_comments": "review_comments"}
  },
  "skeleton_code": "class PaperReviewerModule(LLMAgentModule): ...",
  "needs_llm_fill": ["description", "prompt_template"]
}
```

## Auto-derivation logic

1. **上游 OUTPUT_SPEC → 新 adapter input_contract**
   - 上游输出的每个 field 变成新 adapter 的输入
   - 全部标记为 required=False（上游可能不总是提供）
   - `_source` 记录来源

2. **下游 INPUT_SPEC → 新 adapter output_contract**
   - 下游需要的每个输入变成新 adapter 的输出
   - `_consumed_by` 记录消费方
   - 类型从下游 SPEC 推断

3. **input_mapping 自动生成**
   - 格式：`key: output.{upstream_module}.{field}`

4. **needs_llm_fill 标记**
   - 无法自动推导的部分（description、prompt 模板）标记为 TODO

## Key Principles

1. **上下游独立** — 可以只指定上游或只指定下游，也可以都不指定
2. **自动推导优先** — 能从 SPEC 推导的自动生成，推不了的标记 TODO
3. **SPEC 是契约** — 新 adapter 的 INPUT_SPEC/OUTPUT_SPEC 必须与上下游兼容
4. **一种组合一个 adapter** — 不同的输入组合配不同的 adapter，不做运行时可选
5. **验证后使用** — 生成的代码和 YAML 需要用 validate_pipeline.py 验证