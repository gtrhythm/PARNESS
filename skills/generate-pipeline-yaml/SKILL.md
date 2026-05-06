---
name: generate-pipeline-yaml
description: >
  将自然语言描述的复杂工作流目标解析为可执行的 DAG pipeline YAML，
  最大化复用已有 agent，通过 adapter 桥接格式差异，仅在必要时设计新 agent
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: pipeline-generation
  project: parness
---

## What I do

用户用自然语言描述一个复杂的工作流目标（可能是一句话，也可能是多步骤的复杂指令），我将其解析、拆解、映射到已有 Agent 目录，最终生成一个可直接运行的 `config/pipelines/*.yaml` 文件。

## When to use me

- 用户说"我想建一个 pipeline..."
- 用户描述一个多步骤的自动化工作流
- 用户说"帮我生成一个 YAML 配置..."
- 用户提供了一个复杂的工作流描述
- 用户输入一段目标描述，期望系统自动编排为 DAG

## Prerequisites

执行此 skill 前，必须动态读取以下文件（不硬编码 agent 名单）：

- `src/orchestrator/modules/__init__.py` — 完整的 agent 注册表、SPEC、tags
- `src/orchestrator/adapters/base.py` — BaseModule / LLMAgentModule 基类规范
- `config/pipelines/` 目录 — 已有 pipeline 作为参考模板
- See the project source code for agent catalog and development guide

## 核心设计原则

| 原则 | 优先级 | 说明 |
|------|--------|------|
| **复用优先** | P0 | 优先从已有 agent 中选择，不造轮子 |
| **Adapter 桥接** | P1 | 数据格式不匹配时，优先用 adapter 桥接，而非新建 agent |
| **解耦** | P1 | 每个 node 只做一件事，通过 `input_mapping` / `output_mapping` 传递数据 |
| **标准合规** | P2 | 必须新建的 agent/adapter 必须符合 `LLMAgentModule` / `BaseModule` 规范 |
| **可验证** | P2 | 生成的 YAML 必须能通过 `validate_pipeline.py` |

## Workflow Definition

### Phase 1: 需求解析（Command Decomposition）

```
任务：将用户自然语言描述解析为结构化需求文档

输入：用户自然语言描述
输出：结构化需求文档

解析目标：
1. 最终产出物（paper / ideas / experiment / analysis / 其他）
2. 数据来源（arxiv / iclr / local PDF / user-provided / config注入）
3. 处理步骤（隐含在描述中的多阶段流程）
4. 质量约束（数量、评分阈值、迭代次数）
5. 资源约束（是否需要GPU、是否有timeout要求）
6. 分支/循环结构（是否有条件分支、迭代优化）

解析示例：
用户输入: "爬取arxiv上关于efficient transformer的论文50篇，
          提取创新点，结合这些创新点生成30个新想法，
          筛选top5跑实验验证，最后写一篇4页论文"

解析为:
  stages:
    - stage: crawl
      source: arxiv
      topic: "efficient transformer"
      count: 50
    - stage: extract
      input_from: crawl
      output: innovations
    - stage: ideation
      input_from: extract
      count: 30
    - stage: filter
      input_from: ideation
      top_k: 5
    - stage: experiment
      input_from: filter
    - stage: writing
      input_from: [filter, experiment]
      format: "4-page paper"
```

### Phase 2: Agent 匹配（Agent Mapping）

```
任务：对每个 stage，从已有 Agent 目录中匹配最合适的 agent

前置动作（必须完成）：
1. 读取 src/orchestrator/modules/__init__.py 中的 _ADAPTERS 和 get_all_module_specs()
2. 掌握当前所有可用 agent 的 name / description / input_schema / output_schema / tags

匹配策略：
1. 精确匹配：stage 功能与某个 agent 的 description 完全对应
2. 组合匹配：一个 stage 需要多个 agent 串联
3. 缺口标记：无任何现有 agent 能覆盖

关键决策树：

  stage 是否需要 LLM？
    ├─ 是 → 匹配继承 LLMAgentModule 的 agent
    └─ 否 → 匹配继承 BaseModule 的 agent（filter/gate/counter/persist/controller）

  stage 是否需要路由决策？
    ├─ 是 → 匹配 routing agent + routes 配置
    └─ 否 → 普通agent

  stage 是否需要迭代？
    ├─ 是 → 匹配 iteration controller + 循环 edges
    └─ 否 → 单次执行
```

### Phase 3: 缺口分析与 Adapter 决策（Gap Resolution）

```
任务：对 Phase 2 中标记的缺口，按优先级解决

Level 1: 纯 Adapter 桥接（优先）
  场景：上游输出格式与下游输入格式不完全匹配
  方案：写一个 BaseModule adapter，做字段映射/格式转换/拆分/合并
  判定标准：
    - 只需数据格式转换，不需要 LLM → BaseModule adapter
    - 只需简单的字段重命名 → 甚至不需要 adapter，用 output_mapping 即可
    - 只需简单的条件判断 → gate module

Level 2: 参数配置解决
  场景：已有 agent 功能匹配，但行为需微调
  方案：通过 YAML params 配置，不改代码
  判定标准：
    - agent 已有对应 config 参数 → 直接在 params 中配置
    - 需要的数据可以通过 external_data 注入 → 加一个 external_data node

Level 3: 新 Agent（最后手段）
  场景：确实没有任何组合能覆盖
  方案：触发 design-new-agent skill，按标准创建
  必须回答：
    - 为什么不能复用？哪个现有 agent 最接近？差在哪？
    - 新 agent 的 INPUT_SPEC / OUTPUT_SPEC 是什么？
    - 继承 LLMAgentModule 还是 BaseModule？

决策记录（每个缺口都必须记录决策理由）：
  gap: "需要将实验结果转为LaTeX表格"
  decision: adapter
  reason: "已有实验评估agent，只需BaseModule做格式转换"
  adapter_design: ExperimentLatexFormatterModule(BaseModule)
    input: {"experiment_results": "list"}
    output: {"latex_tables": "str"}
```

### Phase 4: YAML 组装（DAG Composition）

```
任务：将匹配的 agent 组装为 DAG YAML

遵循以下规则：

#### 4.1 节点命名
- id 使用语义化名称：{stage}_{role}，如 crawl_arxiv, ideation_generate
- 同类型多个实例用编号：evaluator_1, evaluator_2

#### 4.2 数据流连接
- 每条数据流必须有 input_mapping（禁止隐式传递）
- output_mapping 仅在字段名冲突时使用
- config.X 引用 graph config 中的参数

#### 4.3 依赖声明
- depends_on 必须包含所有数据依赖的上游节点
- 无数据依赖的节点可以并行（框架自动处理）

#### 4.4 路由配置
- routing agent 必须配 routes 表
- iteration controller 必须配 routes: {continue: loop_back, exit: next}

#### 4.5 迭代循环
- 需要 iteration controller node
- 需要 edge: {from: controller, to: worker, feedback_key: ...}
- 设置 max_rounds 限制

#### 4.6 YAML 模板结构

name: {pipeline_name}
config:
  topic: ...
  db_path: ...
  # 其他全局参数

nodes:
  - id: external_config
    module: external_data
    params: {初始数据注入}

  - id: {stage_1_node}
    module: {matched_agent}
    depends_on: [external_config]
    input_mapping: {...}
    output_mapping: {...}

  - id: {stage_2_node}
    module: {matched_agent}
    depends_on: [{stage_1_node}]
    input_mapping: {...}

  # ... 中间节点

  - id: {final_output}
    module: result_exporter / idea_saver / paper_formatter
    depends_on: [{last_stage_node}]

edges: []  # 大多数情况不需要显式 edges
```

### Phase 5: 一致性校验（Validation）

```
任务：对生成的 YAML 执行多层校验

#### 5.1 结构校验
- 所有 input_mapping 中的 output.X.Y，X 是否是已声明的 node id？
- Y 是否存在于该 node 对应 agent 的 OUTPUT_SPEC？
- 所有 depends_on 中的 node id 是否存在？

#### 5.2 类型校验
- 上游 OUTPUT_SPEC 的类型是否与下游 INPUT_SPEC 匹配？
- 特别注意：str vs dict, list vs list[dict]

#### 5.3 路由校验
- routing agent 的 routes 表是否覆盖了所有可能的 _route 值？
- iteration controller 是否有 continue 和 exit 两个路由目标？

#### 5.4 完整性校验
- 是否有孤立节点（不连接任何上下游且非 external_data）？
- 是否有断链（上游输出无人消费）？

#### 5.5 自动运行验证
python scripts/validate_pipeline.py {generated_yaml_path}
```

### Phase 6: 输出与交付（Delivery）

```
任务：交付最终产出物

输出包含：
1. YAML 文件 → config/pipelines/{pipeline_name}.yaml
2. 缺口决策报告 → 哪些用了已有 agent，哪些用了 adapter，哪些需要新建
3. 如果有新 agent/adapter 需要创建：
   - 输出 agent 规格说明（触发 design-new-agent skill）
   - 输出 adapter 规格说明（触发 design-adapter skill）
4. 验证结果 → validate_pipeline.py 的输出

如果存在未创建的新 agent/adapter：
  输出下一步操作指引：
  "以下 agent/adapter 需要先创建才能运行此 pipeline：
   1. xxx_adapter (adapter) — 格式转换
   2. xxx_agent (new agent) — 需要设计
   请先使用 design-new-agent skill 创建这些模块。"
```

## Key Principles

1. **运行时动态发现** — agent 列表从 `modules/__init__.py` 动态读取，不硬编码名单或数量
2. **复用 > Adapter > 新建** — 三级优先级严格递减，每个缺口必须记录为什么不能复用
3. **SPEC 是契约** — 组装 YAML 时必须对照 INPUT_SPEC / OUTPUT_SPEC，保证类型匹配
4. **先验证再交付** — 交付前必须通过 validate_pipeline.py 校验
5. **解耦** — 每个 node 职责单一，数据流通过 input_mapping / output_mapping 显式声明
6. **迭代与路由明确** — 迭代循环必须有 controller，分支必须有 routes 表，不留隐式逻辑

## Usage Example

用户输入: "帮我建一个 pipeline，从Semantic Scholar搜索论文，解析PDF提取方法，
         生成改进想法，评估后取top3，写一篇survey"

1. Phase 1 解析为: search → parse → ideation → evaluate → filter → write
2. Phase 2 匹配: search_crawler → pdf_kit_parse → idea_generator → idea_evaluator → topk_filter → paper_writer
3. Phase 3 检查缺口: 无缺口，所有 stage 均有对应 agent
4. Phase 4 组装 YAML，配置 input_mapping 连接数据流
5. Phase 5 运行 validate_pipeline.py 校验
6. Phase 6 交付 config/pipelines/survey_generator.yaml
