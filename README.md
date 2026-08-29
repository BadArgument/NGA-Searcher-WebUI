# NGA 版面搜索器

全版面本地全文搜索工具，提供 Web UI。离线索引后按关键词、作者、日期范围秒搜 NGA 帖子。

## 功能

- **全文搜索** — 离线 SQLite 索引 + 模糊匹配，支持多关键词 AND/OR、排除词、日期范围、作者筛选
- **在线搜索** — 直连 NGA API 搜索，无需预索引
- **版面发现** — 自动获取 NGA 全部版面列表
- **增量更新** — 后台定时刷新已索引版面，检测新帖/回复
- **收藏管理** — 收藏帖子，支持导出
- **导出** — 帖子导出为 HTML 或 UBB 格式
- **多平台** — macOS / Windows / Linux 单文件可执行

## 快速开始

### 1. 获取 Cookie

浏览器登录 [bbs.nga.cn](https://bbs.nga.cn) → F12 → Network → 任意请求 → 复制 `Cookie` 请求头整段，粘贴到可执行文件同级目录的 `AUTH` 文件中。

```
┌──────────────────────────────────────┐
│  nga-search                          │
│  AUTH         ← Cookie 放这里        │
│  search.db    ← 自动生成             │
└──────────────────────────────────────┘
```

### 2. 启动

**直接运行可执行文件：**

```bash
# macOS / Linux
./nga-search

# Windows
nga-search.exe
```

**或从源码启动：**

```bash
uv run nga
```

浏览器会自动打开 `http://127.0.0.1:8765`。

### 3. 使用

1. 点击「版面」→「发现版面」拉取版面列表
2. 进入目标版面 →「索引全部」抓取帖子元数据
3. 回到首页搜索，关键词空格分隔为 AND

## 启动参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--port` | `8765` | HTTP 服务端口 |
| `--host` | `127.0.0.1` | 监听地址 |
| `--no-open` | — | 不自动打开浏览器 |

## 从源码构建

### 环境要求

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)

### 安装依赖

```bash
uv sync --extra dev
```

### 开发模式运行

```bash
uv run nga
```

### 打包为单文件

```bash
uv run python build.py
# 输出: dist/nga-search
```

## 技术栈

| 层 | 技术 |
|----|------|
| Web 框架 | FastAPI + Uvicorn |
| 模板引擎 | Jinja2 |
| 数据库 | SQLite（本地 `search.db`） |
| 搜索 | rapidfuzz（模糊匹配）+ 自定义 query parser |
| HTTP | httpx |
| 打包 | PyInstaller（单文件多平台） |
| CI/CD | GitHub Actions 自动构建 + Release |

## 项目结构

```
nga-forum-search/
├── src/nga_search/
│   ├── app.py              # FastAPI 应用工厂
│   ├── cli.py              # CLI 入口
│   ├── web.py              # 兼容包装（委托到 app.py）
│   ├── auth.py             # Cookie 认证
│   ├── crawler.py          # NGA API 爬虫
│   ├── parser.py           # NGA 响应解析
│   ├── store.py            # SQLite 存储层
│   ├── indexer.py          # 索引协调器
│   ├── query.py            # 搜索查询引擎
│   ├── export.py           # UBB→HTML 转换 + 导出
│   ├── sanitizer.py        # HTML 白名单清洗（防 XSS）
│   ├── schemas.py          # Pydantic 请求/响应模型
│   ├── ratelimit.py        # 请求频率控制
│   ├── emotes.py           # 表情映射
│   ├── models.py           # 数据类
│   └── routers/            # FastAPI 路由
│       ├── pages.py        # SSR 页面
│       ├── search.py       # 搜索 API
│       ├── threads.py      # 帖子 API
│       ├── boards.py       # 版面 API
│       ├── favorites.py    # 收藏 API
│       ├── indexing.py     # 索引 API
│       ├── export.py       # 导出 API
│       ├── users.py        # 用户 API
│       └── status.py       # 状态 API
├── web/
│   ├── templates/          # Jinja2 模板
│   └── static/             # 静态资源 (app.js)
├── build.py                # PyInstaller 打包脚本
├── run.py                  # PyInstaller 入口
├── pyproject.toml
└── .github/workflows/
    └── build.yml           # CI 多平台构建
```

## 数据存储

SQLite 数据库 `search.db` 位于可执行文件同级目录，包含：

- `boards` — 版面列表
- `posts` — 帖子内容（含主题和回复）
- `favorites` — 收藏列表
- `users` — 用户搜索历史

## License

MIT