# 工具链约定：uv 与 just

## uv 单文件脚本（PEP 723）

本项目所有 Python 一律是 [uv](https://docs.astral.sh/uv/) 可直接运行的
单文件脚本，不维护 `requirements.txt` / `pyproject.toml` / venv。

脚本头部模板（[scripts/build.py](../scripts/build.py)）：

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
```

- `# /// script ... ///` 是 [PEP 723](https://peps.python.org/pep-0723/)
  内联元数据：声明 Python 版本下限和第三方依赖，uv 运行时自动解析、
  按需建临时环境。
- 运行方式：`uv run scripts/build.py`（或 `chmod +x` 后直接执行，shebang
  的 `-S` 让 env 能传多个参数给 uv）。
- 以后需要第三方库时**只改 `dependencies` 列表**，例如
  `# dependencies = ["httpx", "pyyaml"]`——不需要任何安装步骤，uv 第一次
  运行时自动装好并缓存。
- CI 用 [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) 装 uv，
  不再需要 `actions/setup-python`（uv 会按 `requires-python` 自动取
  合适的 Python）。

## just

[just](https://just.systems/) 是命令别名层（比 make 干净，无依赖追踪语义）。
[Justfile](../Justfile) 提供：

| 命令 | 作用 |
|---|---|
| `just` | 列出所有 recipe |
| `just build` | `uv run scripts/build.py`：校验 + 产出 `dist/` |
| `just check` | 同上但丢弃输出，纯校验快速失败 |
| `just stats` | 各类别规则行数统计 |
| `just clean` | 删除 `dist/` |

日常改规则的最小闭环：编辑 `rules/<cat>.list` → `just build` → commit/push
→ CI 自动发布（见 [release-pipeline.md](release-pipeline.md)）。
