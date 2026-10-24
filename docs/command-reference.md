# 命令参考

这份文档是 WorkBuddy Toolkit 主要命令行能力的实用索引。当前版本支持的精确参数，请以 `workbuddy help` / `wb-help` 和各命令自己的帮助输出为准。

## 命令总览

| 命令 | 用途 | 常见场景 |
|---|---|---|
| `workbuddy init` | 开启多账号工作区共享（先备份每个会话的原始归属） | 第一次安装或修复 |
| `workbuddy rollback [UID]` | 撤销共享，按备份恢复会话与自动化任务的原始归属；UID 仅用于没有备份记录的会话 | 不再需要共享或卸载前 |
| `wb-tool` | 交互式控制中心 | 免记命令引导式操作全量功能 |
| `wb-login` | 添加或刷新账号配置 | 添加新的 WorkBuddy 账号 |
| `wb-list` | 列出已保存账号 | 查看有哪些账号可用 |
| `wb-status` | 查看当前账号状态 | 确认当前身份和健康状态 |
| `wb-switch` | 切换到另一个已保存账号 | 不重新登录直接换号 |
| `wb-memory` | 跨账号记忆汇总：去重择优、追加渲染、可还原 | 多个账号共用一套长期偏好 |
| `wb-audit` | 巡检凭据健康度 | 检查过期或刷新问题 |
| `wb-checkin` | 执行每日签到 / 连续任务 | 手动或定时日常任务 |
| `wb-usage` | 查看使用量 / 积分流速 | 分析一段时间的消耗 |
| `wb-chat` | 从终端调用 WorkBuddy 模型 | 轻量命令行交互 |
| `wb-router` | 管理可选容灾路由 | 模型请求容灾 |
| `wb-models` | 查看模型清单与倍率 | 模型选择 / 成本判断 |
| `wb-doctor` | 诊断本地兼容性 | 上游更新后的首个检查命令 |
| `wb-help` | 查看已安装命令帮助 | 发现当前命令能力 |

多数 `wb-*` 命令是 Toolkit 安装后对主 `workbuddy` 命令行的便捷别名。

## 交互控制中心 (`wb-tool`)

```bash
wb-tool
# 或使用完整形式: workbuddy tool
```

启动零认知负担的引导式控制中心，集成积分查看、账号切换、每日签到、模型选择、磁盘清理与客户端重启等完整生命周期操作。支持层级面包屑回退（子菜单输入 `0` / `q` / `Esc` 返回主菜单）与原地热重载连续操作。

## 推荐的首次运行顺序

```bash
workbuddy init
workbuddy doctor
workbuddy status
wb-list
```

如果 `doctor` 已经报告运行时不兼容或只解析了一部分能力，不要一上来反复切换账号。

## 账号生命周期

### 添加账号

```bash
wb-login
```

用于添加新账号，或通过 Toolkit 登录流程刷新已有账号配置。

### 查看已保存账号

```bash
wb-list
```

如果你更关心当前活跃账号和运行时状态，用：

```bash
wb-status
```

### 切换账号

```bash
wb-switch
```

切换不是简单文件覆盖。Toolkit 会先同步当前活跃凭据，再替换目标账号配置，降低较新的 Token 被旧状态覆盖的风险。

### 跨账号记忆汇总

```bash
workbuddy memory collect                  # 汇总所有账号 MEMORY.md，去重并保留质量更优的版本
workbuddy memory compact                  # 给超长/偏好事实类条目建分片，窗口里只留一行索引
workbuddy memory compact --shard-min 200  # 只给超过 200 字的条目建分片（默认 120）
workbuddy memory apply [账号]             # 渲染进指定账号（省略则全部）
workbuddy memory apply --budget 600       # 临时收紧共享段落预算（默认 800 字）
workbuddy memory rebalance                # 把准则/画像分流到 SOUL、USER（默认只出计划）
workbuddy memory rebalance --apply --target 3200
workbuddy memory forget "关键词"          # 移出共享库并留墓碑（默认只预览）
workbuddy memory forget "关键词" --apply  # 确认后执行；账号原文不动
workbuddy memory conflicts                # 查看互相否定的规则
workbuddy memory status                   # 库规模、可发布条数、各账号自有/共享条数、字数
workbuddy memory restore <账号>           # 用快照还原，并摘掉分诊写入的 SOUL / USER 段落
workbuddy memory on / off                 # 开启 / 关闭切号时自动汇总渲染
```

- **不覆盖原文**：首次接入时存一份快照（只给 `restore` 用），日常渲染的基线是文件**当前**的自有内容，只做“原文 + 追加段落”；
- **不复活**：你在文件里删掉的行，下次 `apply` 不会写回来；只有 `restore` 回到快照；
- **不丢版本**：疑似重复时保留质量更高的一条，落选版本进 `superseded` 留档；
- **可还原**：`restore` 按快照写回，同时摘掉 SOUL / USER 里 `<!-- memory-rebalance:begin -->` 的受管段落，所以是“回到分诊前”；备份在 `cache/shared_memory/backups/`；
- **相似判定保守**：只合并 ≥0.90 的近重复，且数字不同一律不合并（`30s` ≠ `60s`）；
- 客户端只读前 4000 字，预算优先给账号自有内容，共享条目放不下会标注条数；原文自己就顶满 4000 时不再补换行，共享段落永远落在窗口内；
- **只发布规则**：`publish_level` 把条目分成 P0 红线 / P1 显式指令 / P2 项目约定 / P3 习惯 / P4 事实推断，默认只发布 P0–P2；含本机路径、邮箱、URL、UUID 的条目，以及以 `>` / `*` / `_` / `|` 开头的引用块、斜体、表格行（文档碎片）一律不跨账号；
- **`--budget`**：共享段落自身预算，默认 800 字，每条按“正文 + 3”计、最多 20 条，按级别与质量先到先得；它限制的是追加段落，不是文件总长；
- **`forget`**：把匹配条目移出共享库并留墓碑，下次 `collect` 不会复活，账号原文不改动；墓碑目前没有解除命令；
- **`conflicts`**：只差否定的两条规则只注入优先级更高的一条，另一条留档不注入，确认后可用 `forget` 永久移除；
- **`compact`**：条目正文超过 `--shard-min`（默认 120 字）或本身是偏好/事实类时，原文落到 `cache/shared_memory/shards/<id>.md`，`apply` 在剩余预算里最多补 8 行索引；分片正文不会被注入，重复执行不会多出分片；
- `rebalance` 解决容量：客户端其实有四个常驻通道（`MEMORY.md` 4000、`SOUL.md`/`USER.md`/`IDENTITY.md` 各 10000），
  把“准则”分流到 SOUL、“画像”分流到 USER，同样一份记忆可以完整保留而不被截断。文档有 ≥2 个 `##` 标题时**整节迁移**（标题、列表、缩进子项一起走），CLI 逐节打印留下/搬走；默认只打印计划，`--apply` 才写，写前备份。

`collect` / `compact` / `apply` / `rebalance` / `restore` / `forget` 全程持有一把跨进程锁（`cache/shared_memory/.hub.lock`，等待上限 5 秒），
所以切号触发的自动同步与手动命令撞车时，后到的那个会提示“被另一个进程占用”，而不是互相覆盖。

完整的发布分级、失效场景与回滚步骤见 [跨账号记忆共享](memory-sharing.md)。

## 健康检查与诊断

### 凭据巡检

```bash
wb-audit
```

用于检查账号健康状态，尤其适合长期没有切换过的副号。

### 兼容性诊断

```bash
wb-doctor
```

这些情况建议先运行 `doctor`：

- 升级 WorkBuddy 后；
- 换机器后；
- 突然出现异常退出登录；
- 出现沙盒或 IPC 相关故障；
- 重装 Toolkit 后。

README 不再硬编码所有可能的诊断状态。真实运行时输出比静态兼容承诺更有价值。

### exit 137 / 命令卡死排查

当前 Toolkit 提供专门取证入口：

```bash
wb-doctor --inspect-137
```

当命令被杀，或故障特征指向沙盒 / 资源耗尽时使用。建议配合 [`docs/incidents/`](incidents/README.md) 下的事故复盘一起判断。

## 自动化

### 每日签到

```bash
wb-checkin
```

建议第一次先手动运行。确认命令本身成功后，再依赖后台定时任务。

Toolkit 安装器可以接入平台原生调度。具体方式取决于操作系统，见 [入门指南](getting-started.md)。

## 使用量查看

```bash
wb-usage
```

用于查看 Toolkit 能提供的使用量 / 积分流速信息。如果要把输出交给其他程序处理，优先使用当前版本支持的机器可读输出。

## 终端模型调用

```bash
wb-chat
```

这是可选能力。基础账号管理不要求使用终端模型调用。

## 容灾路由

```bash
wb-router
```

容灾路由是高级能力，用于把模型层故障与账号健康状态分开处理。基础安装并不要求启用。

## 模型清单

```bash
wb-models
```

用于查看 Toolkit 能观察到的模型清单和相关元数据，辅助模型选择和使用量判断。

## 机器可读状态

部分状态和诊断命令支持 JSON 输出。旧 README 曾记录 `--json` 用于状态 / 诊断场景。真正接入自动化前，请先检查当前安装版本的命令帮助，确认参数和字段名。

示例：

```bash
wb-status --json
```

自动化应依赖已文档化字段，并允许未来增加新字段。

## 安全操作顺序

WorkBuddy 上游发生变化时，建议按这个顺序：

```text
1. wb-doctor
2. wb-status
3. wb-list
4. 确认无异常后，再执行写入 / 切换 / 自动化操作
```

这样可以把兼容性检查放在状态修改之前。

## 相关文档

- [入门指南](getting-started.md)
- [架构说明](architecture.md)
- [工程笔记](engineering-notes.md)
- [事故复盘](incidents/README.md)