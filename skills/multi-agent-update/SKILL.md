---
name: multi-agent-update
description: Parallel multi-agent modification workflow - discovers all agents, spawns coding agents for parallel updates, monitors status, and marks completion
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: multi-agent-coordination
  project: parness
---

## What I do

当需要对多个agent进行修改时，我定义了一套完整的并行处理工作流程：

1. **发现阶段** - 列出所有待修改的agent，构建修改清单
2. **评估阶段** - 评估每个agent的修改工程量
3. **分配阶段** - 根据工程量和可用资源，决定并行度
4. **执行阶段** - 启动多个coding agent并行修改不同的agent
5. **监控阶段** - 主agent持续监控各coding agent的状态
6. **完成阶段** - 根据返回状态更新清单标记

## When to use me

当用户要求：
- "修改所有agent..."
- "对多个agent进行..."
- "批量更新agent..."
- 任何涉及同时修改多个agent的任务

## Workflow Definition

### Phase 1: Discover Agents

```
任务：发现所有需要修改的agent

1. 使用glob/grep工具搜索agent定义文件
2. 构建agent列表，格式：
   ```
   | Agent Name | File Path | Status |
   |------------|-----------|--------|
   | agent1     | path/to/1 | pending |
   | agent2     | path/to/2 | pending |
   ```
3. 展示列表给用户确认修改范围
```

### Phase 2: Assess Workload

```
任务：评估修改工程量

对每个pending状态的agent：
1. 读取agent源代码
2. 评估修改复杂度（简单/中等/复杂）
3. 估算所需时间

根据总工程量决定并行度：
- ≤3个agent: 串行执行
- 4-10个agent: 2-3个并行
- >10个agent: 4-6个并行
```

### Phase 3: Spawn Coding Agents

```
任务：为每个agent分配一个coding agent

对每个pending agent，启动一个coding agent子任务：
- 任务描述：修改指定agent的指定内容
- 上下文：包含原始需求和具体修改指令
- 期望输出：完成状态报告

使用Task tool启动子agent，格式：
task({
  description: "修改 {agent_name}",
  prompt: "请修改 {file_path} 中的agent，需求是：{modification_request}",
  subagent_type: "coding"
})
```

### Phase 4: Monitor Status

```
任务：持续监控所有coding agent的状态

监控机制：
1. 定期检查各子agent的task_id
2. 收集返回状态
3. 更新清单中的status字段：
   - pending → in_progress → completed/failed
4. 如有失败，评估是否需要重试或手动介入
```

### Phase 5: Complete & Report

```
任务：汇总最终结果

生成报告：
```
## 修改完成报告

| Agent Name | File Path | Status | Notes |
|------------|-----------|--------|-------|
| agent1     | path/to/1 | ✅ 完成 | - |
| agent2     | path/to/2 | ❌ 失败 | 原因：xxx |

成功: 1/2
失败: 1/2
```

如需重试，使用相同工作流重新处理失败的agent
```

## Key Principles

1. **先列清单后执行** - 始终先展示完整agent列表
2. **动态并行度** - 根据工程量自动调整并行数量
3. **状态透明** - 实时更新清单状态
4. **容错处理** - 失败不阻塞其他agent
5. **主agent监控** - 主agent保持对全局状态的掌控

## Subagent Result Format

每个coding agent返回时应包含：
```json
{
  "agent_name": "xxx",
  "status": "completed|failed",
  "files_modified": ["file1", "file2"],
  "summary": "修改摘要",
  "error": "错误信息（如有）"
}
```

## Usage Example

当用户说 "修改所有agent的错误处理逻辑" 时：

1. 主agent加载此skill
2. 发现5个agent，创建清单
3. 评估工程量，决定3个并行
4. 启动3个coding agent
5. 监控状态，收集结果
6. 更新清单，生成最终报告
