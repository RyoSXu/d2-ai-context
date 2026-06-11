# d2-ai-context

本地只读的 Destiny 2 AI 上下文框架。

`d2-ai-context` 读取 Bungie 官方 Manifest 和用户授权的 Profile 数据，将版本数据、库存、武器、护甲、异域装备、perk、socket、craftable 等信息整理成 AI 易读取的本地上下文。目标是让 AI 基于用户真实数据和当前版本数据，和用户讨论 build、武器 roll、异域搭配、缺失装备与刷取优先级。

本项目保持只读：不会移动、装备、购买、分解、聚焦或修改任何账号物品。

## 项目定位

`d2-ai-context` 只负责给 AI 提供可靠上下文：

- 当前 Bungie Manifest 版本数据。
- 用户只读 Profile / 库存数据。
- 可搜索的武器、护甲、异域、perk、socket 和 craftable 索引。
- 给 AI 直接读取的紧凑 context pack。
- 后续可扩展的 MCP、Skill、HTTP API 或自定义 AI 接入层。

推荐把它理解为：

```text
Bungie API + 本地解析 + 索引导出 + AI 上下文
```

## 当前状态

当前项目处于可用 MVP 阶段，重点是 CLI、本地数据同步、索引导出和 AI 上下文生成。

已经完成：

- Manifest 下载、更新和本地 SQLite 缓存。
- Bungie OAuth 登录、token refresh 和只读 Profile 拉取。
- 武器、护甲、异域、perk、socket、stat 和 craftable 数据解析。
- 可读 JSON、CSV profile 数据和 Manifest CSV 索引导出。
- 给 AI 读取的 `data/context/ai_context_pack.md` 生成。
- Manifest/Profile 搜索命令。
- 单物品 `inspect-item` 查询，可查看 Manifest 定义、用户拥有实例、socket、perk 和 stat。
- 武器 `perk-pool` 查询，可按 socket/列查看 Manifest 中的完整 perk 池。
- `setup`、`sync`、`doctor` 一键初始化、同步和健康检查命令。

尚未完成：

- MCP server：把本地查询能力暴露给支持工具调用的 AI 客户端。
- Codex Skill：让 Codex 按固定流程读取本项目数据。
- HTTP API：给 Web UI、bot 或其他客户端使用。
- 权威强度排名、自动 build 推荐或社区 meta 判断。

当前推荐使用方式是：用 CLI 同步和查询数据，再把生成的 context pack、CSV 和索引交给 AI 工具读取。

## 安装

```powershell
pip install -r requirements.txt
copy .env.example .env
```

然后编辑 `.env`，填写 Bungie API 信息。

## 创建 Bungie API Application

1. 打开 Bungie.net 的开发者应用页面并创建 Application。
2. 填写 `BUNGIE_API_KEY`、`BUNGIE_CLIENT_ID`、`BUNGIE_CLIENT_SECRET`。
3. Redirect URL 填：`https://localhost:8765/callback`。
4. 本工具只使用读取数据所需的 OAuth 登录，不会调用账号写接口。

为什么需要自己创建 Bungie API Application：

- Bungie OAuth 登录必须绑定一个已注册的 API Application，包括 API key、client id、client secret 和 redirect URL。
- DIM 之类的工具也使用 Bungie OAuth，只是 DIM 团队已经注册并运营了自己的官方应用，所以用户只看到“点击登录”。
- `d2-ai-context` 当前是纯本地、开源、无托管后端的 CLI 工具，没有公共服务器替用户完成 OAuth 应用身份和回调流程。
- `client secret` 不能安全地写进公开 GitHub 仓库；如果项目内置公共 secret，就等于泄露这个 Bungie 应用的凭据。
- 因此当前版本采用“用户自己创建 Bungie Application，本机通过 `localhost` 回调登录”的方式，换来更简单的本地部署和更清楚的账号边界。

后续如果项目提供官方 Bungie Application、公共登录入口或安全的公开客户端 OAuth 流程，可以把体验改成更接近 DIM：用户只点击登录，不再手动填写 API 信息。

`.env` 示例：

```dotenv
BUNGIE_API_KEY=
BUNGIE_CLIENT_ID=
BUNGIE_CLIENT_SECRET=
BUNGIE_REDIRECT_URI=https://localhost:8765/callback
BUNGIE_LOCALE=zh-chs
```

## 快速开始

推荐一键初始化、同步和检查：

```powershell
python main.py setup
python main.py sync
python main.py doctor
```

`sync` 会依次执行 Manifest 更新、OAuth/Profile 拉取、装备解析、Manifest 导出和 AI context pack 生成。

首次登录会打开浏览器进入 Bungie 官方 OAuth 页面。不要在终端里输入 Bungie 密码。
本地 OAuth 回调用自签名 HTTPS 证书，浏览器提示证书风险时可以继续访问 `localhost`。

## 现在能做什么

同步完成后，用户可以：

- 搜索当前 Manifest 里的物品、perk 和收藏品。
- 搜索自己 Profile 中拥有的武器、护甲和异域。
- 检查单个物品的官方定义和当前拥有实例。
- 查询武器完整 perk 池，并按随机 socket/列分组查看中文 perk 名和描述。
- 导出当前 Manifest 的全量 JSONL 压缩数据和常用 CSV 索引。
- 生成紧凑 AI context pack，让 AI 基于当前版本和真实库存讨论 build、roll、缺失装备和刷取优先级。

这个项目提供事实上下文，不内置权威 meta 结论。涉及强度排行、god roll、赛季环境或活动推荐时，应额外结合当前补丁说明和可靠社区资料。

## 常用命令

```powershell
python main.py manifest
python main.py login
python main.py profile
python main.py parse
python main.py export-data
python main.py context-pack
python main.py all
```

搜索当前 Manifest 和用户数据：

```powershell
python main.py search "星界夜鹰"
python main.py search "边缘交通" --scope profile
python main.py search "诱导推销" --scope manifest
```

检查单个物品的 Manifest 定义和当前拥有实例：

```powershell
python main.py inspect-item "牵引器火炮"
python main.py inspect-item 3580904581 --owned-limit 1
python main.py inspect-item "鬼神胸甲" --json
```

查询武器 perk 池：

```powershell
python main.py perk-pool "边缘交通"
python main.py perk-pool 2228325504 --json
python main.py perk-pool "边缘交通" --include-reusable
```

## 输出

- `data/manifest/`：当前版本 SQLite Manifest。
- `data/manifest/manifest_meta.json`：Manifest 版本、语言和本地路径元数据。
- `data/profile/raw_profile.json`：原始 Profile 响应。
- `data/profile/items_readable.json`：可读装备 JSON。
- `data/profile/weapons.csv`：武器 CSV。
- `data/profile/armor.csv`：护甲 CSV。
- `data/profile/exotics.csv`：异域护甲 CSV。
- `data/profile/craftables.json`：craftables 原始片段。
- `data/exports/`：当前 Manifest 的全量 JSONL 压缩导出和 CSV 索引。
- `data/context/ai_context_pack.md`：给 AI 读取的紧凑上下文包。

## AI 工具用法

这个项目可以作为任何 AI 工具的本地上下文来源。最低门槛流程：

```powershell
python main.py setup
python main.py sync
python main.py doctor
```

之后让 AI 优先读取：

- `docs/AI_USAGE.md`
- `data/context/ai_context_pack.md`
- `data/profile/weapons.csv`
- `data/profile/armor.csv`
- `data/profile/exotics.csv`
- `data/exports/*/indexes/inventory_items_index.csv`
- `data/exports/*/indexes/sandbox_perks_index.csv`

回答 build 问题时，应明确区分：

- Bungie/API 事实：Manifest、物品定义、perk 描述、用户拥有的装备和 roll。
- 用户 Profile 事实：当前库存、角色、装备实例、socket、stat、craftable。
- 外部判断：强度评价、god roll、配装推荐、活动适配性、社区共识。

## 集成方向

项目主体应保持为通用 CLI / Python 数据框架，AI 适配层可以按需扩展：

- CLI：适合脚本、手动同步、本地查询。
- Context pack：适合复制到任意 AI Chat 工具或让 Agent 直接读取文件。
- MCP server：适合支持工具调用的 AI 环境。
- Codex Skill：适合告诉 Codex 如何使用本项目的数据、命令和边界。
- HTTP API：适合自建 Web UI、bot、OpenAI API 工作流或其他客户端。

Skill、MCP、HTTP API 都应调用同一套本地数据层，不应把 token、Profile 原始数据或 Manifest 数据打包进 Skill。

## 隐私和安全

以下文件包含敏感或私人信息，不要上传、粘贴到公开位置或提交到仓库：

- `.env`
- `data/token.json`
- `data/profile/raw_profile.json`
- profile 派生 CSV/JSON，如果用户不打算公开分享

项目必须保持 Bungie 账号只读。不要添加或调用以下接口能力：

- transfer item
- equip item
- socket item
- dismantle item
- purchase item
- focus item

## 常见错误

- API key 缺失：检查 `.env` 里的 `BUNGIE_API_KEY`。
- OAuth redirect 不匹配：Bungie Application 的 Redirect URL 必须和 `.env` 完全一致。
- token 过期：工具会自动 refresh；refresh 失败会重新打开网页登录。
- Manifest 下载失败：检查网络、Bungie 服务状态和 `BUNGIE_LOCALE`，工具会从 `zh-chs` fallback 到 `en`。
- profile components 返回缺失：账号隐私设置或权限可能不允许读取某些 component，错误会列出请求的 component。
- membershipType 识别失败：确认当前 Bungie 账号已绑定 Destiny 2 平台账号。

## 当前限制

当前版本重点是数据同步、解析、索引导出和 AI 上下文生成。它不内置权威强度排名，也不替用户执行任何账号操作。
