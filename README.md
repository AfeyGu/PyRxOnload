# PyRxOnload

AutoCAD + PyRx 环境下的 **Python 插件开机自动加载管理工具**（单文件，开箱即用）。

## 背景

AutoCAD 的启动组（APPLOAD「内容」）只支持 `.arx` / `.lsp` / `.vlx` / `.dvb`，**不支持 `.py`**。
PyRx 自身虽支持开机自动加载（onload），但：

- 只支持**单个** onload 入口（`%APPDATA%\pyrx\pyrx.toml` 的 `[user] onload_path`）；
- 没有配套的 GUI 管理工具（已核实 PyRx 3.1.7 全包源码）。

本工具补上这个缺口：

1. 自身作为 onload 入口（单值入口由 PyRx 自动加载）；
2. 在 `pyrx.toml` 中维护一个「自动加载模块列表」（`onload_modules`，PyRx 未知键会忽略，由本脚本依次加载）；
3. `ONLOAD` 命令弹出列表式管理界面：**添加 / 移除 / 立即加载**，类似 APPLOAD 的启动组管理。

## 特性

- **单文件**：只依赖 Python 标准库 + PyRx + wx（均为 CAD 环境自带），无第三方安装；
- **自动迁移**：首次加载时若原 onload 入口是其它文件，自动把它移入加载列表，**不丢失原配置**；
- **智能加载/重载**：已加载的模块自动走卸载→重载（保证拿到新代码），未加载的走加载，不会出现「假成功」；
- **GUI 管理**：`ONLOAD` 命令随时增删列表、立即加载全部；
- **CAD 外可测**：模块顶层不依赖 PyRx（惰性导入），`pyrx.toml` 读写为纯函数，可脱离 CAD 单测。

## 使用方法

分发给任意用户，仅两步：

1. `APPLOAD` 加载 `RxLoader*.arx`（PyRx 加载器，按 CAD 版本选择）；
2. `PYLOAD` 本文件 `PyRxOnload.py`：

   - 自动把本文件注册为 onload 入口（若原入口是其它文件，自动移入加载列表，不丢失）；
   - 自动加载列表中的全部文件（等价逐个 `PYLOAD`）。

之后每次启动 AutoCAD 自动加载本脚本 → 依次加载列表中的插件；命令行输入 `ONLOAD` 随时管理列表。

### ONLOAD 命令界面

| 按钮 | 功能 |
| --- | --- |
| 添加... | 选择要自动加载的 `.py` 文件加入列表 |
| 移除 | 从列表中移除选中项 |
| 立即加载 | 加载选中项（已加载则自动重载） |
| 全部加载 | 加载列表全部（含入口，自动按需加载/重载） |

> 双击列表项 = 立即加载该插件。

## 工作原理

```
%APPDATA%\pyrx\pyrx.toml
  [user]
  onload_path = "D:/path/to/PyRxOnload.py"   ← PyRx 开机加载（官方键）
  onload_modules = ["D:/path/to/QuaintDim.py", ...]  ← 本工具维护（未知键，PyRx 忽略）
```

- PyRx 启动时只加载 `onload_path` 指向的 `PyRxOnload.py`；
- `PyRxOnload.py` 在 CAD 内被加载时（模块末尾）执行：
  1. `_auto_register_self()`：确保自己是入口，迁移旧配置；
  2. `_load_onload_modules()`：按列表依次加载/重载所有插件；
  3. 注册 `ONLOAD` 命令，供随时管理。

`onload_modules` 是 `pyrx.toml` 中的未知键，PyRx 官方代码会忽略它，不会产生副作用。

## 环境要求

| 依赖 | 说明 |
| --- | --- |
| AutoCAD | 2019+（PyRx 支持版本） |
| PyRx | 3.x（`pip install cad-pyrx`，建议 3.1.7+） |
| Python | 3.11+（PyRx 要求，`tomllib` 为标准库） |

## 测试

`pyrx.toml` 读写为纯 Python 函数，可脱离 CAD 直接单测（源仓库带 `test_pyrx_onload.py`）：

```bash
python -m unittest test_pyrx_onload
```

## 文件说明

```
PyRxOnload/
├── PyRxOnload.py   ← 唯一实现（入口 + toml 管理 + GUI + 加载逻辑）
└── README.md
```

## 许可证

[MIT](LICENSE)
