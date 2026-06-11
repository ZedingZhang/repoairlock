# RepoAirlock

面向任意 coding agent 的安全执行 Harness。

[English](README.md) | 简体中文

## 解决的问题

Coding agent 会自主修改代码。没有隔离、记录和策略控制时，以下问题难以回答：

- Agent 做了什么？
- 是否触及了仓库外的文件？
- 它的修改能否重放？
- 原始工作区是否完好无损？

RepoAirlock 通过隔离环境、结构化审计轨迹和可重复工件来回答这些问题。

## RepoAirlock 做什么

RepoAirlock 在隔离的 Docker 容器中使用 git worktree 隔离运行 coding agent，
记录结构化执行轨迹，强制执行安全策略，并导出可重复的工件——全程不修改用户的原始工作树。

## 能力等级

| 等级 | 名称 | 能力 |
|------|------|------|
| 0 | Process Wrapper | 容器隔离、工件记录、patch 导出、资源监控、HTML 报告 |
| 1 | Structured Events | 导入 agent 工具调用轨迹用于过程质量分析 |
| 2 | Enforcement (preview only) | 对单个工具调用（Bash/Edit/Write）进行执行前策略检查，需通过 Claude Code hook adapter |

**当前状态：** v0.1.0 alpha release candidate。Tier 0 stabilization in progress。
Claude Code Tier 2 hook adapter 模块为 preview only；v0.1 的 CLI `run` 路径
使用 command adapter。

## 5 分钟体验

```bash
# 1. 安装
git clone https://github.com/ZedingZhang/repoairlock.git && cd repoairlock
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. 环境检查
repoairlock doctor

# 3. 在沙箱中运行 agent
repoairlock run \
  --repo examples/demo-repo \
  --image alpine:latest \
  -- sh -c "echo 'print(\"Hello, RepoAirlock!\")' > /workspace/hello.py"

# 4. 查看结果
repoairlock list
repoairlock inspect <run-id>

# 5. 重放 patch（不会重新调用 agent）
repoairlock replay <run-id> --repo examples/demo-repo

# 6. 对比两次运行
repoairlock compare <run-a> <run-b>

# 7. 查看 HTML 报告
open ~/.repoairlock/runs/<run-id>/report.html
```

## 安全保证

- Agent 永远不会在用户原始工作树中运行（INV-001）
- 容器默认无网络、无特权、有 CPU/内存/PID 限制
- 环境变量通过显式 allowlist 注入——绝不传递整个主机环境
- 每次沙箱执行尝试即使失败也生成可审计工件（manifest、events、logs、patch、report）
- 每次运行前后验证原始工作区指纹
- Patch 重放前通过 SHA-256 验证完整性
- Sandbox 配置策略执行：在构造阶段拒绝危险的 Docker 参数
- 命令级策略执行仅在启用 Tier 2 Claude Code hook adapter 时生效

## 明确不作保证

RepoAirlock **不能**也**不会**保证：

- 防止容器逃逸（这是 Docker 运行时的属性）
- Tier 0 下观察 agent 所有内部行为
- 防御容器内主动恶意代码
- 绝对隔离（Docker 是进程级边界，非硬件边界）
- Tier 0 下 on/off 之外的网络出口过滤

RepoAirlock 是一个**安全 Harness**，不是安全沙箱。当你显式启用网络（`--network bridge`）时，agent 可以发起出站连接。

## 架构

```
                        ┌────────────────────────────┐
                        │        repoairlock CLI       │
                        │  run / inspect / replay /   │
                        │  compare / list / doctor    │
                        └──────────────┬─────────────┘
                                       │
                             create RunContext
                                       │
                        ┌──────────────▼─────────────┐
                        │       Run Orchestrator      │
                        │  (完整 Tier 0 流水线)       │
                        └───────┬───────────┬────────┘
                                │           │
                  ┌─────────────▼───┐   ┌──▼────────────────┐
                  │ WorkspaceManager │   │   ArtifactStore    │
                  │  git worktree    │   │  JSONL / JSON /    │
                  │  指纹验证        │   │  原子写入          │
                  └─────────────┬───┘   └──▲───┬─────────────┘
                                │          │   │
                        ┌───────▼──────────┴───┴───────┐
                        │         SandboxBackend       │
                        │   DockerSandbox (安全参数)   │
                        └───────┬──────────────────────┘
                                │
                  ┌─────────────▼──────────────┐
                  │        AgentAdapter         │
                  │  Tier 0: CommandAdapter     │
                  │  Tier 2: ClaudeCodeAdapter  │
                  └─────────────┬──────────────┘
                                │
              ┌─────────────────▼────────────────┐
              │ PolicyEngine   │ ReportGenerator │
              │ (12 条规则)    │ (JSON + HTML)   │
              │ EventRecorder  │ CompareService  │
              └─────────────────────────────────┘
```

## 报告示例

运行 `repoairlock run` 后生成的 HTML 报告包含 8 个章节：

1. **Run Summary** — 状态、wall time、退出码、HEAD SHA
2. **Safety Posture** — 网络模式、特权状态、环境变量 allowlist、INV-001
3. **Repository Change Summary** — 文件/行数变更、敏感路径检测
4. **Verification Result** — verifier 退出码（如已配置）
5. **Resource Usage** — 峰值内存、平均 CPU、峰值 PIDs、网络 I/O
6. **Quality & Policy Findings** — 能力层级声明、安全发现
7. **Artifact Integrity** — SHA-256 哈希
8. **Replay Instructions** — 精确的重放命令

每份报告都显式标注当前 capability tier 以及该层级**无法得出**的结论。

## 支持的 Adapter

| Adapter | Tier | 说明 |
|---------|------|------|
| `command` | 0 | 任意 CLI agent——原样包装命令在沙箱中执行 |
| `claude_code` | 2 (preview only) | Claude Code hook adapter 模块——PreToolUse 策略执行 + PostToolUse 记录；v0.1 暂未暴露 CLI wiring |

## 开发路线

| 阶段 | 状态 | 交付内容 |
|------|------|----------|
| 0 | 完成 | 仓库脚手架与约束文档 |
| 1 | 完成 | Artifact Store 与事件日志 |
| 2 | 完成 | WorkspaceManager 与原始仓库保护 |
| 3 | 完成 | DockerSandbox 与 doctor |
| 4 | 完成 | CommandAdapter 与首个完整 run |
| 5 | 完成 | Inspect、Replay、Compare |
| 6 | 完成 | 指标与 HTML 报告 |
| 7 | 完成 | Policy Engine（12 条默认规则） |
| 8 | 完成 | Claude Code Tier 2 hook adapter 模块 |
| 9 | 进行中 | 稳定化与公开发布 |

详见 [docs/progress.md](docs/progress.md)。

## 局限

- **平台：** Linux 优先。macOS 通过 Docker Desktop 支持，但资源限制、文件系统语义和性能有差异。CI 以 Linux 为准。
- **Windows：** v0.1 无 Windows 原生支持。
- **Tier 0 可见性：** 无法观察 agent 内部工具调用、LLM token 使用或单步推理。HTML 报告显式声明了这一点。
- **网络过滤：** 仅开/关（`none`/`bridge`），无域名级 allowlist。
- **Docker 依赖：** 需要 Docker daemon。暂不支持 Podman/buildah。
- **PostToolUse 测试：** Claude Code Tier 2 adapter 的 PostToolUse 记录需要真实 Claude Code 二进制文件进行完整端到端测试。

## 运行测试

```bash
pip install -e ".[dev]"
ruff check .
mypy src
pytest -q                    # 单元 + 集成测试（无 Docker daemon 时跳过 Docker 测试）
pytest -q tests/e2e          # 端到端测试（需要 Docker）
```

## 设计原则

1. **范围克制：** MVP 只做单机 CLI，不做 Web UI、远程服务、多租户。
2. **默认安全失败：** 隔离不可用时显式失败，不静默降级。
3. **原始工作区不可变：** 绝不在原始 working tree 中执行 agent。
4. **工件优先：** 终端输出只是视图，工件才是事实来源。
5. **能力分层：** 公开接入能力等级，不夸大能力。

## 出处

RepoAirlock 是面向 coding agent 的安全执行 Harness。它**不**执行代码生成、LLM 推理或自主修复。它**不**保证"完全安全"或"绝对隔离"。它提供的是一个结构化、可审计、可复现的执行环境，使得 agent 的行为可以被审查、重放和对比。
