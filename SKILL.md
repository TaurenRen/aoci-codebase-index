---
name: aoci-codebase-index
description: "给大型代码库建一张持久化、Git 版本化的认知索引（AOCI），让 coding agent 开局读一次就懂系统，不再每任务重读仓库；支持首建、增量漂移检测与自动维护；本地优先、不上传代码。当任务涉及「让 AI 读懂大仓库」「跨会话保持项目理解」「接手陌生项目」「索引过期/漂移」「上下文不够用」时使用。"
---

# 代码库认知索引（AOCI）

## 它解决什么

大模型上下文窗口装不下整个仓库，于是每个任务都要重新搜索、重新读代码，读到的还是碎片。
AOCI 的做法是：把每个文件压缩成**一行高密度条目**，存成仓库里的纯文本文件，跟代码一起被 Git 版本化。
agent 开局读一次索引，就知道每个文件负责什么、依赖谁、对外契约是什么、哪些地方不能乱改。

规模参考（官方文档口径）：20 万行代码约需 1 小时完成首建；生产中有 70 万行商业系统用约 30 万 token 的索引在维护。

## 先判断任务

| 他说的 | 做什么 |
|---|---|
| 「让 AI 读懂这个仓库」「建索引」 | 走首建流程（下面第二节） |
| 「我改了代码」「索引过期了吗」 | `maintain` 查漂移 → 只更新被影响的条目 |
| 「索引质量怎么样」 | `index score`（九维度评分） |
| 「agent 每次都重读仓库」 | 这就是 AOCI 要解决的问题，按本文接入 |

## 一、前置：仓库必须是 Git 仓库（硬门槛）

AOCI 的认知范围 = **Git 跟踪的文件集合**。不是 git 仓库的项目，先 `git init`。

```
git init
# 关键：先写 .gitignore，把依赖、构建产物、上传目录、AI 工具资产排除掉
git add -A && git commit -m "initial commit"
```

**这一步最容易翻车**：没有 .gitignore 就 `git add`，node_modules、日志、上传文件全会进索引，
把认知预算瞬间打爆（实测：不规范时预估 61.8 万 token，规范后 14.8 万，差 4 倍）。

## 二、首建流程

```bash
# 1）初始化（会生成 .aoci/ 骨架、aoci.txt 三件套、config.json、AGENTS.md 区块）
aoci init --locale zh-CN          # 想自动接入宿主：加 --agent claude|codex|cursor|opencode|all

# 2）建立基线指纹
aoci scan

# 3）看当前该干什么（永远以 Guide 返回的 next_action 为准）
aoci index agent guide --agent cursor --json

# 4）取一批候选（每批 ≤50 条，响应预算 24 KiB）
aoci maintain                     # 通过 MCP：tools/call aoci_maintain，无参数

# 5）读完这批每个文件 → 写条目 → 整批提交（见第四节契约）

# 6）重复 4–5，直到 remaining = 0；再依次跑 verify → check → guide
```

### 关键顺序（踩过坑）

1. **`init` 之后不要直接改 `.aoci/config.json` 的 `exclude_dirs` 来收窄范围**——会让策略身份漂移，
   Guide 卡在 `scope_change_required` 且 `aligned=false`。
2. **也不要用 `scope rule add --action exclude` 大批量排除**——超过阈值
   （`entry_removal_percent=25`）会被判定为高风险变更，要求**真人在终端手敲确认串**；
   脚本/管道里过不去（`human_tty_digest_confirmation_required`）。
3. **正道是从 Git 源头解决**：把无关目录写进 `.gitignore` 并 `git rm -r --cached <dir>`（磁盘文件保留），
   再删掉 `.aoci` 与 `aoci*.txt` 重新 `init`。因为认知对象就是 git 跟踪集合，源头干净就不需要事后删条目。

## 三、FRAS 四个字段

```
文件名[标签]: F:职责 | R:必须一起读的关联 | A:对外契约 | S:不可推断但改错会出事的约束
```

- **F 职责**：它是干什么的，不写怎么实现
- **R 关系**：只允许 `code:相对路径`，逗号分隔无空格，没有写 `-`
- **A 契约**：对外暴露的标识符（函数名、组件名、properties、事件名），没有写 `-`
- **S 约束**：**只写"从代码读不出来、但改的人不知道就踩坑"的事实**。没有合格约束就写 `-`

完整规范、标签字典与配额上限见 `references/fras-writing.md`。

## 四、提交契约（机器会逐条校验，错了整批拒收）

```
aoci_update_entry:
  code_batch_id : 必须 = maintain 返回的 code_plan.batch_id（也等于每个 candidate.batch_id）
                  绝不能用 authoring_batch.batch_identity
  entries[]    : path + source_sha256 + candidate_id + new_entry
                 三者都来自 maintain 返回，不许自己造
```

**整批提交，不要分批**：批次大小已按单次调用标定。
**批次不是用户决策**：一批写完立刻再调 `maintain` 拿下一批，中间不要问用户。

## 五、常见驳回与修法（实测）

| rule_code | 含义 | 修法 |
|---|---|---|
| `object_tag_dictionary_violation` | 标签某一位不在字典里 | 标签用 **4 位紧凑形式**；模块位（第 2 位）**不能用 `F`**，配置类用 `C` |
| `fras_s_too_long` | S 超 rune 上限 | 砍到 ≤50（或机器给的 max_runes） |
| `fras_a_too_many_items` | A 项数超限 | 只留前 N 项（常为 6） |
| `entry_field_budget_exceeded` | 字段 token 超预算 | token = UTF-8 字节/3，一个中日韩字符算 1 |

**建议写个自动修复循环**：提交 → 读 findings → 按机器给的 max_* 裁 → 再提交。实测三轮就能从 14 处不符收敛到 0。

## 六、增量维护（这才是它值钱的地方）

- 代码改完、进入最终稳定状态后，**只调一次 `maintain`**（不要在中间状态逐文件维护）
- 它会返回 `stale` / `missing` / `orphan` 三类：stale = 条目过期需更新，missing = 新文件待写，orphan = 文件已删
- 实测：只在文件末尾加一行注释，`maintain` 立刻精确标出 `stale 1 → miniprogram/components/course-card/index.js`

**漂移是怎么算出来的**：基线里存了每个文件的源码 SHA-256，改动后哈希对不上就是漂移——不依赖时间戳，也不依赖 AI 判断。

## 七、不能做的事（红线）

- **条目必须由模型写**。路径、文件名、AST、符号列表、依赖扫描、正则、模板、规则引擎只能用来定位/传递/校验/审计/写入，**不能**用来生成、预填、拼接或改写 F/R/A/S 和策展裁决
- 标签新写一律用 compact 形态；点分形态只保留读取兼容
- 分类或字典缺口**不要**写进 S；证据不足不等于可以编

## 八、本机环境（Windows，2026-10-09 实测）

- 二进制：`D:\tools\aoci\bin\aoci.exe`（v0.1.0-rc19）
- MCP 配置：`~/.workbuddy/mcp.json` 里加

```json
"aoci": {
  "command": "D:\\tools\\aoci\\bin\\aoci.exe",
  "args": ["mcp", "--repo", "D:\\Workspace\\dylan\\FeifeiAI"]
}
```

- **宿主没加载 MCP 时怎么调**：起 `aoci mcp --repo <根>` 子进程，用 stdio 发 JSON-RPC——
  先 `initialize` → 再发 `notifications/initialized` → 才能 `tools/call`。少发通知会被拒。参考 `scripts/mcp_call.py`。
- 装完 MCP 要**重启宿主并在连接器里点「信任」**才会生效。
- 许可：上游工具是 **FSL-1.1-MIT**（Functional Source License，两年后转 MIT），
  **限制竞争性使用**（不能拿它做成托管/转售的同类产品）；本 skill 只是使用方法的整理，不涉及再分发其代码。

## 九、回流

每次用它干完活：新模块补条目、踩到的新驳回写进 `references/pitfalls.md`、更新 `CHANGELOG.md`。
