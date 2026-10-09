# aoci-codebase-index · 让 Agent 一次读懂你的整个代码库

一个 Agent Skill：用 [AOCI-CODE](https://github.com/aoci-spec/aoci-code)
把大型代码库压成一张**持久化、Git 版本化的认知索引**。
装进你的 coding agent（WorkBuddy / Claude Code / Codex / Cursor / opencode）之后，
它每个任务开局读一次索引就知道系统在干什么，而不是反复搜索、反复重读仓库。

> 这不是工具本体的分发，只是**我把这套流程真跑通之后整理出来的操作方法与踩坑清单**。
> 工具本体请到上游仓库获取。

---

## 为什么需要它

大模型的上下文窗口装不下整个仓库。于是每个任务都要重新 grep、重新读文件，
读到的还是碎片，改完也不知道碰了谁。

AOCI 的答案是：每个文件一行条目，四个字段把「职责 / 关联 / 对外契约 / 不能踩的约束」
压成高密度的纯文本，跟代码放在一起，由 Git 版本化。

规模参考（上游官方口径）：

- 20 万行代码，首建约 1 小时
- 生产中有 70 万行的商业系统，用约 30 万 token 的索引在维护

## 装到你的 agent

```bash
git clone https://github.com/TaurenRen/aoci-codebase-index.git ~/.workbuddy/skills/aoci-codebase-index
```

再按 `SKILL.md` 里的安装段装好 AOCI 本体（release 包 + `aoci init --locale zh-CN` + MCP）。

## 怎么用

```bash
aoci init --locale zh-CN      # 生成 .aoci/ 与 aoci.txt 三件套
aoci scan                     # 建立基线指纹（每个文件的源码 SHA-256）
aoci index agent guide --agent cursor --json   # 问机器：下一步干什么

# 循环直到 remaining = 0：
aoci maintain                       # MCP: tools/call aoci_maintain，无参数
#   读这一批每个文件 → 写条目 → 整批 aoci_update_entry

aoci verify && aoci check           # 收尾
```

条目长这样（一条一行）：

```
watermarked-image/index.js[CU6M]: F:给图片叠品牌水印的公共组件，按 mode 决定烧进图片或作为浮层，支持按容器宽高自适应定位 | R:code:miniprogram/config/index.js | A:src,mode,text | S:mode=burn 时水印被写进导出图，无法撤销
```

四个字段：

| 字段 | 写什么 |
|---|---|
| **F** | 它负责什么，不写怎么实现 |
| **R** | 必须一起读的文件，只写 `code:路径` |
| **A** | 对外契约：函数名 / 组件名 / properties / 事件名 |
| **S** | **不能从代码推断、改的人不知道就踩坑**的事实 |

## 这个 skill 相对上游 README 多了什么

上游 README 讲产品是什么，这个 skill 讲**你照着做一遍会遇到什么**：

1. **首建的真实工作量口径**：`scan` 后 `guide` 会直接告诉你「1297 个文件待写、每批 50 条、约 52 轮」——
   动手前就能估出这是个半小时还是一整天的事。
2. **踩坑清单（16 条，全部实测）** —— 包括两个会让人直接卡死的地方：
   - 改 `.aoci/config.json` 的 `exclude_dirs` 收窄范围 → 策略身份漂移，后续 maintain 全部 `repair_required`
   - 用 `scope rule add --action exclude` 大批量排除 → 超过 25% 阈值，要求**真人在终端手敲确认串**，
     脚本/管道里过不去
   - 正解是从 Git 源头排除（`.gitignore` + `git rm -r --cached`），因为认知对象就是 git 跟踪集合
3. **标签格式的坑**：官方样例是 4 位紧凑形式（如 `EG7T`），但照「A+B+C+[D]+E」字面写会插一个 `-`，
   结果被 `object_tag_dictionary_violation` 拒收；模块位还不能用 `F`。
4. **免 MCP 集成的调用脚本** `scripts/mcp_call.py`：宿主还没加载新 MCP server 时，
   直接起 stdio 子进程发 JSON-RPC 也能调（关键是 `initialize` 之后必须补发 `notifications/initialized`）。
5. **自动修复循环** `scripts/submit_batch.py`：提交 → 读机器 findings → 按 `max_runes` / `max_items` / `max_tokens` 裁剪 → 重交。
   实测三轮收敛：14 → 10 → 0 处不符。

## 目录

```
SKILL.md                     主文件：判断表、首建流程、提交契约、红线
references/
  fras-writing.md            FRAS 四字段规范、标签字典、配额上限
  pitfalls.md                16 条实测踩坑
scripts/
  mcp_call.py                免 MCP 集成的 stdio JSON-RPC 客户端
  submit_batch.py            批量提交 + 自动修复循环
```

## 许可

本 skill 的文本与方法整理：**MIT**，版权归 TaurenRen。

**上游工具 AOCI-CODE 是 FSL-1.1-MIT（Functional Source License 1.1），不是 MIT 也不是 Apache**：

- 允许个人/企业内部使用、修改、部署
- **禁止**把它的二进制或代码做成竞争性产品／对外托管服务提供给第三方
- 该限制在发布满两年后解除，届时转 MIT

商用前请自行确认这一条，别把它当成普通 MIT 依赖用。
