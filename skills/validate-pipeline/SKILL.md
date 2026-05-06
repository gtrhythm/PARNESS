---
name: validate-pipeline
description: Validate pipeline YAML files by checking adapter input/output connections, type compatibility, and dependency integrity before running
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: pipeline-validation
  project: parness
---

## What I do

验证 pipeline YAML 文件中所有 adapter 之间的输入输出对接是否正确，在运行 pipeline 之前发现接口不匹配问题。

## When to use me

- 在运行 pipeline 之前
- 修改了 adapter 的输入输出后
- 新建或修改 pipeline YAML 后
- 用户要求"检查 pipeline"、"验证配置"

## Validation Checks

脚本 `scripts/validate_pipeline.py` 执行以下 5 项检查：

1. **STRUCTURE** — `config.X` key 是否存在于 pipeline config 中；`output.X.Y` 引用的节点是否存在
2. **FIELD_EXISTS** — `output.X.Y` 中的 Y 是否存在于上游 adapter 的 OUTPUT_SPEC 中
3. **TYPE_MATCH** — 上游输出类型与下游输入类型是否匹配（字符串级别）
4. **REQUIRED_COVERAGE** — 下游 INPUT_SPEC 中标记为 required=True 的输入是否都被 input_mapping 覆盖
5. **DANGLING_REF** — input_mapping 引用了不在 depends_on 中的节点（WARN）

## How to use

```bash
# 验证单个 pipeline
python scripts/validate_pipeline.py config/pipelines/simple_idea_test.yaml

# 验证目录下所有 pipeline
python scripts/validate_pipeline.py config/pipelines/

# JSON 输出
python scripts/validate_pipeline.py config/pipelines/simple_idea_test.yaml --json
```

## Output format

```
[PASS] STRUCTURE: config.ideas → idea_evaluation.ideas
[PASS] TYPE_MATCH: experiment_plan.experiment_plan(str) → experiment_report.experiment_plan(str)
[FAIL] TYPE_MATCH: experiment_report.report(str) → paper_writing.experiment_results(dict): type mismatch
[WARN] DANGLING_REF: 'paper_writing' referenced but not in depends_on
```

- `[PASS]` — 检查通过
- `[WARN]` — 潜在问题，不阻塞运行
- `[FAIL]` — 严重问题，运行时会出错

## How INPUT_SPEC / OUTPUT_SPEC work

每个 adapter 类声明了 INPUT_SPEC 和 OUTPUT_SPEC：

```python
class PaperReviewerModule(LLMAgentModule):
    module_name = "paper_reviewer"

    INPUT_SPEC = {
        "paper_content": {"type": "dict", "required": True},
        "paper_id": {"type": "str", "required": False, "default": ""},
    }

    OUTPUT_SPEC = {
        "overall_score": {"type": "float"},
        "summary": {"type": "str"},
        "critiques": {"type": "list"},
    }
```

验证脚本读取这些 SPEC，对照 YAML 的 input_mapping / output_mapping 做静态检查。

## Key Principles

1. **先验证再运行** — 任何 pipeline 修改后先跑验证脚本
2. **SPEC 是契约** — adapter 的输入输出声明是机器可读的接口契约
3. **类型必须匹配** — 上游输出 str，下游期望 dict，就是 FAIL
4. **depends_on 必须覆盖** — input_mapping 引用的节点必须在 depends_on 里