---
name: design-new-agent
description: End-to-end new agent design workflow - analyzes requirements, selects template, generates adapter code, registers module, creates YAML config, writes tests, and validates against the agent contract
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: agent-design-implementation
  project: parness
---

## What I do

当需要设计并实现一个新agent时，我提供从需求分析到可运行代码的完整工作流程：

1. **需求分析** — 明确agent的功能、输入输出、在管道中的位置
2. **模板选择** — 从4种Agent模板中选择最合适的
3. **代码生成** — 生成适配器、领域Agent（可选）、注册代码
4. **管道集成** — 生成YAML管道配置
5. **测试编写** — 生成单元测试和集成测试
6. **合规验证** — 对照Agent契约验证所有代码

## When to use me

当用户要求：
- "设计一个新agent..."
- "添加一个xxx模块"
- "实现一个xxx功能的agent"
- "创建一个新的分析agent"
- 任何涉及**创建新agent**的任务

## Prerequisites

设计新agent前，必须理解以下框架知识：

- See the project source code for agent catalog and development guide
- `src/orchestrator/adapters/base.py` — BaseModule / LLMAgentModule 基类
- `src/db/base.py` — BaseDatabase（SQLite连接、WAL模式、PRAGMA设置）
- `src/db/connection.py` — DatabaseManager（命名数据库连接管理）
- `src/db/schemas/` — 已有的SQLite表结构+JSON重建视图定义
- `src/db/writers/` — 已有的Writer实现（KnowledgeStoreWriter等）
- `src/db/queries/` — 已有的Query实现（从SQLite视图读取）

## 持久化约束（重要）

**所有涉及写入操作的agent，必须使用本系统的 SQLite + SqliteJson 双层持久化方案，禁止直接写JSON文件。**

### 架构说明

本系统采用双层持久化架构：

| 层 | 职责 | 技术 |
|----|------|------|
| 写入层（主） | 持久化数据到 SQLite 归一化表 | `BaseDatabase` + `Writer` |
| 读取层（桥） | 从 SQLite 视图重建 JSON 供管道消费 | `json_group_array()` 视图 |

数据流：
```
SQLite 归一化表（写入） → SQLite JSON视图（桥接） → 管道消费
```

### 实现规范

当agent需要持久化数据时：

1. **检查已有Writer** — 先查看 `src/db/writers/` 是否已有对应领域的Writer可复用
2. **复用或新建Writer** — 如需新建，继承或组合 `BaseDatabase`：
   ```python
   from src.db.base import BaseDatabase

   class XxxWriter:
       def __init__(self, db: BaseDatabase):
           self.db = db

       def save_xxx(self, data):
           self.db.execute(
               "INSERT OR REPLACE INTO xxx_table (...) VALUES (?, ?, ?)",
               (field1, field2, field3))
           self.db.commit()
   ```
3. **归一化表设计** — 列表字段拆分为子表，用 position 字段保序
4. **JSON重建视图** — 在 `src/db/schemas/` 对应 schema 文件中添加视图：
   ```sql
   CREATE VIEW IF NOT EXISTS v_xxx_full AS
   SELECT
       x.id, x.field1,
       (SELECT json_group_array(child.value)
        FROM xxx_child child WHERE child.parent_id = x.id) AS values_json
   FROM xxx x;
   ```
5. **在 adapter 中通过 config 获取 db_path，在 execute/run_agent 内创建 Writer**
6. **禁止使用** `json.dump()` / `json.dumps()` 写文件作为持久化方案

参考实现：
- 写入示例：`src/db/writers/knowledge_store_writer.py`
- 视图示例：`src/db/schemas/knowledge_store_schema.py`（62表+JSON视图）
- Adapter集成示例：`src/orchestrator/adapters/kb_save.py`

## Workflow Definition

### Phase 1: Requirements Analysis

```
任务：收集并明确agent的设计需求

向用户确认以下信息（如未提供则主动询问）：

1. 功能描述
   - agent 做什么？（一句话）
   - 属于哪个分类？（RESEARCH/IDEATION/EXPERIMENT/REVIEW/WRITING/INFRASTRUCTURE）

2. 输入输出
   - 需要什么输入？（从上游或initial_data）
   - 产出什么输出？（给下游使用）
   - 是否需要 _route 路由？
   - 是否产出 _score 自评分？

3. LLM依赖
   - 是否需要调LLM？
   - 如果需要，prompt的大致逻辑？

4. 管道位置
   - 在哪个管道中使用？
   - 上游是谁？下游是谁？
   - 是否有并行分支或迭代循环？

5. 参数配置
   - 需要哪些可配置参数？
   - 默认值是什么？

6. 持久化需求（关键）
   - agent是否需要将结果写入/保存？
   - 如果需要，对应哪个数据库领域？（knowledge_store / papers / evaluations / experiments / crawled_papers / paper_writing）
   - 是否已有Writer可复用，还是需要新建Writer+表+视图？

输出：需求文档（简版）
```yaml
agent_name: xxx_agent
display_name: Xxx Agent
description: 一句话描述
category: IDEATION
requires_llm: true

inputs:
  - name: data
    type: List[Dict]
    required: true
    source: output.upstream.results

outputs:
  - name: results
    type: List[Dict]
    destination: downstream
  - name: count
    type: int

config_params:
  - name: target_count
    type: int
    default: 20

persistence:
  needs_write: true
  db_domain: knowledge_store
  reuse_writer: KnowledgeStoreWriter
  # 或 needs_write: false（纯计算/路由agent）

pipeline_position:
  pipeline: iclr_multi_agent_pipeline
  depends_on: [upstream_node]
  downstream: [downstream_node]
```
```

### Phase 2: Template Selection

```
任务：从4种Agent模板中选择最合适的

根据需求匹配模板：

| 模板 | 适用场景 | 标志 |
|------|---------|------|
| 普通Agent | 数据变换，调LLM做计算 | 无 _route，单进单出 |
| 路由Agent | 条件分支，质量门控 | 需要 _route + YAML routes |
| 迭代控制器 | 控制循环次数 | 需要 _route: continue/exit |
| 聚合Agent | 合并多上游输出 | depends_on 多个节点 |

基类选择：
- 需要 LLM + 监控 → 继承 LLMAgentModule（推荐）
  - 只需实现 run_agent() 和可选的 emit_output()
  - 自动管理 reporter 生命周期和错误处理
- 不需要 LLM → 继承 BaseModule
  - 需手动管理 reporter（如有）
- 简单逻辑 → 适配器包含全部逻辑（无需领域Agent文件）
- 复杂逻辑 → 拆分为适配器 + 领域Agent

输出：模板选择决策
```yaml
template: 普通Agent
base_class: LLMAgentModule
needs_domain_agent: true
needs_routes: false
```
```

### Phase 2.5: SPEC Definition

```
任务：定义 adapter 的 INPUT_SPEC 和 OUTPUT_SPEC

在写代码之前，先定义接口契约：

1. 如果有已知上游/下游，运行 design_adapter.py 自动推导：
   python scripts/design_adapter.py --name {agent_name} --upstream {upstream} --downstream {downstream}

2. 根据推导结果 + 需求分析，确定最终的 INPUT_SPEC 和 OUTPUT_SPEC

3. SPEC 格式：
   INPUT_SPEC = {
       "key_name": {"type": "str|dict|list|float|int|bool", "required": True|False, "default": ...},
   }
   OUTPUT_SPEC = {
       "key_name": {"type": "str|dict|list|float|int|bool"},
   }

4. 验证 SPEC 与上下游兼容：
   python scripts/validate_pipeline.py config/pipelines/{pipeline}.yaml

输出：确认的 INPUT_SPEC 和 OUTPUT_SPEC
```

### Phase 3: Code Generation

```
任务：生成agent的完整代码

#### 3.1 适配器文件

文件：src/orchestrator/adapters/{agent_name}.py

根据选择的基类生成代码：

--- 模板A：继承 LLMAgentModule（推荐，用于LLM agent）---

class XxxAgentModule(LLMAgentModule):
    module_name = "{agent_name}"

    INPUT_SPEC = {
        "data": {"type": "list", "required": True},
    }
    OUTPUT_SPEC = {
        "results": {"type": "list"},
        "count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        from src.domain.xxx import XxxDomainAgent

        # 1. 提取输入
        data = inputs.get("data")
        if not data:
            raise ValueError("'data' input is required")

        # 2. 获取LLM客户端（已包含缺失检查）
        llm_client = self._get_llm_client()

        # 3. 读取配置参数
        param_a = self.config.get("param_a", "default")

        # 4. 执行业务逻辑
        agent = XxxDomainAgent(llm_client=llm_client)
        result = await agent.run(data, param_a=param_a)

        # 5. 返回输出
        return {
            "results": result,
            "count": len(result),
        }

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        # 可选：实现监控输出
        return AgentOutput(
            display_type="metrics",
            title="Xxx Agent Results",
            data={"count": result.get("count", 0)},
        )

--- 模板B：继承 BaseModule（用于非LLM agent）---

class XxxModule(BaseModule):
    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        data = inputs.get("data")
        if not data:
            raise ValueError("'data' input is required")

        result = self._process(data)
        return {"results": result, "count": len(result)}

    def _process(self, data):
        ...

--- 模板C：路由Agent ---

class QualityGateModule(LLMAgentModule):
    module_name = "quality_gate"

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        ideas = inputs.get("ideas", [])
        threshold = self.config.get("pass_threshold", 7.0)

        if not ideas:
            return {"_route": "fail", "reason": "no ideas"}

        # 评估逻辑...
        if avg_score >= threshold:
            return {"_route": "pass", "ideas": ideas, "_score": avg_score}
        return {"_route": "fail", "ideas": ideas, "_score": avg_score}

--- 模板D：迭代控制器 ---

class MyControllerModule(BaseModule):
    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        score = inputs.get("_score", 0.0)
        attempt = inputs.get("_iteration_attempt", 0) + 1
        max_attempts = self.config.get("max_attempts", 5)
        target = self.config.get("target_score", 7.0)

        if score >= target or attempt >= max_attempts:
            return {
                "_route": "exit",
                "final_outputs": inputs,
                "_score": score,
            }
        return {
            "_route": "continue",
            "refined_inputs": inputs,
            "_score": score,
        }

--- 模板E：聚合Agent ---

class MyAggregatorModule(BaseModule):
    def __init__(self, config: dict = None):
        self.config = config or {}

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        branch_a = inputs.get("branch_a_results", [])
        branch_b = inputs.get("branch_b_results", [])
        combined = branch_a + branch_b
        return {"combined": combined, "total": len(combined)}

#### 3.2 领域Agent文件（如需要）

文件：src/idea_agents/{agent_name}.py 或 src/{package_name}/{name}.py

class XxxDomainAgent:
    def __init__(self, llm_client, **kwargs):
        self.llm_client = llm_client
        ...

    async def run(self, data, **kwargs):
        prompt = self._build_prompt(data)
        response = await self.llm_client.chat([
            {"role": "system", "content": "..."},
            {"role": "user", "content": prompt},
        ])
        return self._parse_response(response)

    def _build_prompt(self, data):
        ...

    def _parse_response(self, response):
        ...

#### 3.3 持久化代码（如 agent 需要写入）

如果 Phase 1 确认 `needs_write: true`，必须生成以下内容：

**情况A：复用已有Writer**
```python
async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
    from src.db.base import BaseDatabase
    from src.db.writers.knowledge_store_writer import KnowledgeStoreWriter

    db_path = self.config.get("db_path")
    db = BaseDatabase(db_path)
    writer = KnowledgeStoreWriter(db)
    writer.save_xxx(processed_data)
    db.close()
```

**情况B：新建Writer**
```python
from src.db.base import BaseDatabase

class XxxWriter:
    def __init__(self, db: BaseDatabase):
        self.db = db

    def save_xxx(self, data_list):
        for item in data_list:
            self.db.execute(
                "INSERT OR REPLACE INTO xxx_table (id, field1, field2) VALUES (?, ?, ?)",
                (item["id"], item["field1"], item["field2"]))
        self.db.commit()
```

同时在 `src/db/schemas/` 对应文件中添加表和JSON视图定义。

**禁止：** 直接使用 `json.dump()` 写文件作为持久化方案。

#### 3.4 注册代码

需要修改的文件：src/orchestrator/modules/__init__.py

两个修改点：

1. _ADAPTERS dict 添加一行：
   "{agent_name}": ("src.orchestrator.adapters.{agent_name}", "XxxAgentModule"),

2. get_all_module_specs() 添加一个 specs.append：
   specs.append(ModuleSpec(
       name="{agent_name}",
       display_name="Xxx Agent",
       description="一句话描述",
       input_schema={"data": "List[Dict]"},
       output_schema={"results": "List[Dict]", "count": "int"},
       tags={"agent", "llm_required"},
       factory=_make_factory(*_ADAPTERS["{agent_name}"]),
   ))
```

### Phase 4: Pipeline Integration

```
任务：生成YAML管道配置

根据Phase 1确定的位置，在目标YAML文件中添加节点：

```yaml
- id: {node_id}
  module: {agent_name}
  depends_on: [{upstream_node_ids}]
  params:
    param_a: "value"
    param_b: 20
  input_mapping:
    data: output.{upstream_node}.{output_key}
    existing_items: output.kb_load.{key}
  output_mapping:
    results: {mapped_key}
  # routes:                    # 仅路由Agent需要
  #   pass: next_stage
  #   fail: retry_loop
  # timeout: 60                # 可选：超时秒数
  # retry:                     # 可选：重试策略
  #   max_attempts: 3
  #   backoff: exponential
```

同时需要更新下游节点的 input_mapping 以引用本节点输出。

如果有 edges 段，添加：
- {from: upstream_node, to: {node_id}}
- {from: {node_id}, to: downstream_node}

验证：
- input_mapping 中的引用使用映射后的key（考虑上游output_mapping）
- depends_on 包含所有数据依赖的上游节点
- 无循环依赖（除非是迭代控制器）
```

### Phase 5: Test Writing

```
任务：生成单元测试和集成测试

#### 5.1 单元测试

文件：tests/test_{agent_name}.py

```python
import pytest
from src.orchestrator.adapters.{agent_name} import XxxAgentModule

@pytest.mark.asyncio
async def test_{agent_name}_happy_path():
    from src.llm_provider.factory import LLMFactory
    mock = LLMFactory.create("mock", delay=0.0)
    module = XxxAgentModule(config={"llm_client": mock, "param_a": "test"})
    result = await module.execute({"data": [{"id": 1, "text": "hello"}]})
    assert "results" in result
    assert result["count"] >= 0

@pytest.mark.asyncio
async def test_{agent_name}_missing_input():
    module = XxxAgentModule(config={})
    with pytest.raises(ValueError, match="data"):
        await module.execute({})

@pytest.mark.asyncio
async def test_{agent_name}_no_llm():
    module = XxxAgentModule(config={})
    with pytest.raises(RuntimeError, match="llm_client"):
        await module.execute({"data": [{"id": 1}]})

@pytest.mark.asyncio
async def test_{agent_name}_empty_input():
    mock = LLMFactory.create("mock", delay=0.0)
    module = XxxAgentModule(config={"llm_client": mock})
    result = await module.execute({"data": []})
    # 根据agent逻辑：空输入应该返回空结果或raise
```

#### 5.2 集成测试（如需要）

```python
@pytest.mark.asyncio
async def test_{agent_name}_in_pipeline():
    from src.orchestrator.modules import register_all_modules
    from src.orchestrator.registry import ModuleRegistry
    from src.orchestrator.iteration.graph import IterationGraph, IterationNode
    from src.orchestrator.iteration.graph_runner import GraphRunner
    from src.llm_provider.factory import LLMFactory

    registry = ModuleRegistry()
    register_all_modules(registry)

    mock_client = LLMFactory.create("mock", delay=0.0)
    shared_config = {"llm_client": mock_client}

    graph = IterationGraph(name="test_{agent_name}", nodes=[
        IterationNode(id="source", module_name="placeholder",
                       input_mapping={}, output_mapping={}),
        IterationNode(id="target", module_name="{agent_name}",
                       depends_on=["source"],
                       input_mapping={"data": "output.source.results"}),
    ])

    runner = GraphRunner(registry, shared_config=shared_config, max_workers=0)
    result = await runner.run(graph, initial_data={"results": [...]})
    assert result.success
```

注意：
- 测试必须用 max_workers=0（MockLLMClient不可pickle）
- MockLLMClient 通过关键词匹配prompt返回预设响应（44条规则）
```

### Phase 6: Compliance Validation

```
任务：对照Agent契约验证所有生成的代码

验证清单：

[ ] 1. SPEC 合规
    - INPUT_SPEC 和 OUTPUT_SPEC 已声明
    - INPUT_SPEC 中 required=True 的字段与代码中 raise ValueError 一致
    - OUTPUT_SPEC 中的字段与 return dict 的 key 一致
    - 运行 validate_pipeline.py 无 FAIL

[ ] 2. 签名合规
    - __init__(self, config: dict = None)
    - async execute/async run_agent
    - 返回 Dict[str, Any]

[ ] 3. 错误处理合规（§4）
    - 必要输入缺失 → raise ValueError
    - LLM未配置 → raise RuntimeError（或使用 _get_llm_client()）
    - 业务逻辑异常 → 不try/except，让异常自然传播
    - 唯一允许吞异常：可降级功能（ImportError等）

[ ] 4. 进程池约束（§3）
    - config/inputs 中只有基本类型
    - 无数据库连接、文件句柄等不可序列化对象
    - 重操作延迟到 execute() 内

[ ] 5. 输出规范（§2.4）
    - 返回 dict，不返回 None
    - 保留字段（_route等）以 _ 开头
    - 普通字段不含 _ 前缀

[ ] 6. 注册完整（§7）
    - _ADAPTERS 添加一行
    - get_all_module_specs() 添加一个 spec
    - input_schema / output_schema 与实际代码一致

[ ] 7. YAML配置正确（§7.4）
    - input_mapping 引用映射后的key
    - depends_on 包含所有数据依赖
    - params 参数名与 self.config.get() 一致

[ ] 8. 无重复
    - 在项目源代码中确认无同名/同功能模块

[ ] 8. 持久化合规
    - 如 agent 需要写入数据，确认使用 SQLite + SqliteJson 方案
    - 通过 BaseDatabase + Writer 写入归一化表
    - 如有列表字段，已创建子表和 JSON 重建视图
    - 无 json.dump()/json.dumps() 直接写文件持久化
    - db_path 通过 config 传入，在 execute/run_agent 内延迟创建连接

验证命令：
```bash
# 1. 导入测试
python -c "from src.orchestrator.adapters.{agent_name} import XxxAgentModule; print('OK')"

# 2. 注册测试
python -c "from src.orchestrator.modules import register_all_modules; from src.orchestrator.registry import ModuleRegistry; r = ModuleRegistry(); register_all_modules(r); print(r.get('{agent_name}'))"

# 3. 单元测试
pytest tests/test_{agent_name}.py -v

# 4. 契约扫描
grep -n 'except.*Exception' src/orchestrator/adapters/{agent_name}.py
grep -n 'return.*{.*"error"' src/orchestrator/adapters/{agent_name}.py
```
```

## Key Principles

1. **LLMAgentModule优先** — 需要LLM的agent一律继承 LLMAgentModule，自动获得 reporter 管理和错误处理
2. **raise不吞** — 所有业务异常 raise，让框架统一处理
3. **延迟导入** — 领域Agent在 run_agent()/execute() 内 import，不在模块顶层
4. **schema一致** — ModuleSpec 的 input/output schema 必须与代码实际使用的字段一致
5. **先查后建** — 先确认无重复模块，再开始创建
6. **SQLite+SqliteJson持久化** — 所有写入操作必须使用 BaseDatabase + Writer 写入SQLite归一化表，通过JSON视图桥接读取，禁止直接写JSON文件持久化

## File Modification Checklist

| 步骤 | 文件 | 操作 |
|------|------|------|
| 1 | `src/orchestrator/adapters/{agent_name}.py` | 新建适配器 |
| 2 | `src/idea_agents/{agent_name}.py`（可选） | 新建领域Agent |
| 2b | `src/db/writers/{domain}_writer.py`（如需写入） | 新建或复用Writer |
| 2c | `src/db/schemas/{domain}_schema.py`（如需新表） | 新建表+JSON视图 |
| 3 | `src/orchestrator/modules/__init__.py` | _ADAPTERS 添加 + ModuleSpec 添加 |
| 4 | `config/pipelines/{pipeline}.yaml`（可选） | 添加节点配置 |
| 5 | `tests/test_{agent_name}.py` | 新建测试 |
| 6 | Update project documentation（可选） | 更新目录 |

## Usage Example

当用户说 "设计一个论文引用格式化agent" 时：

1. 需求分析：输入论文列表+格式风格 → 输出格式化的引用文本，不需要LLM（纯计算）
2. 模板选择：普通Agent，继承 BaseModule，无领域Agent
3. 代码生成：适配器包含全部逻辑，无LLM依赖
4. 管道集成：可选，视用户需求
5. 测试编写：测试各种引用格式（APA/MLA/Chicago）
6. 合规验证：运行验证清单，确认无问题

当用户说 "设计一个实验结果分析agent" 时：

1. 需求分析：输入实验结果 → 输出分析报告+改进建议，需要LLM
2. 模板选择：普通Agent，继承 LLMAgentModule，需要领域Agent
3. 代码生成：适配器 + 领域Agent（prompt构建 + 响应解析）
4. 管道集成：在实验管道中，experiment_evaluator 之后
5. 测试编写：MockLLMClient 单元测试 + 管道集成测试
6. 合规验证：全清单通过
