# -*- coding: utf-8 -*-
"""PyRxOnload.py — PyRx onload 启动加载项通用管理工具（独立脚本）

背景：AutoCAD 启动组（APPLOAD 内容）只支持 .arx/.lsp/.vlx/.dvb，
不支持 .py。PyRx 的开机自动加载（onload）只支持单个 onload_path
（%APPDATA%\\pyrx\\pyrx.toml 的 [user] onload_path），且没有 GUI
管理工具（已核实 3.1.7 全包源码）。本脚本补上这个缺口：
    1. 自身作为 onload 入口（单值 onload_path 由 PyRx 自动加载）
    2. 在 toml 中维护一个「自动加载模块列表」（onload_modules，
       未知键，PyRx 会忽略；由本脚本依次加载）
    3. ONLOAD 命令弹出列表式管理界面（仿 QDSTYLE 设置对话框）：
       添加 / 移除 / 立即全部加载

用法（分发给任意用户，两步）：
    1. APPLOAD 加载 RxLoader*.arx（PyRx 加载器，按 CAD 版本选）
    2. PYLOAD 本文件：
       - 自动把本文件注册为 onload 入口（若原入口是其它文件，
         自动把它移入加载列表，不丢失）
       - 自动加载列表中的全部文件（等价 PYLOAD 逐个加载）
    之后每次启动 AutoCAD 自动加载本脚本 → 依次加载列表；
    输入 ONLOAD 命令随时管理列表。

CAD 外可 import 本模块（用于单测 toml 读写），命令注册、自动注册
与列表加载仅在 CAD 内执行。
"""
import os
import tomllib
from pathlib import Path

try:
    from pyrx import Ap, command
except Exception:  # pragma: no cover - CAD 外 pyrx 可 import，此处兜底
    Ap = None
    command = None


def _norm(path: str) -> str:
    """路径统一正斜杠（pydantic Path 接受，避免反斜杠转义问题）"""
    return str(path).replace("\\", "/")


# ====================================================================
# pyrx.toml 读写（纯函数，可脱离 CAD 单测）
# ====================================================================

def onload_toml_path() -> Path:
    """%APPDATA%\\pyrx\\pyrx.toml（PyRx 官方配置位置）"""
    return Path(os.environ.get("APPDATA", "") or ".") / "pyrx" / "pyrx.toml"


def _read_toml(toml_file: Path | None) -> dict:
    p = toml_file or onload_toml_path()
    if not p.is_file():
        return {}
    with p.open("rb") as fh:
        return tomllib.load(fh)


def _write_toml(data: dict, toml_file: Path | None) -> None:
    p = toml_file or onload_toml_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_dump_toml(data), encoding="utf-8")


def _user_section(data: dict, toml_file: Path | None) -> dict:
    """返回可变 user 段（tomllib 返回 dict，可直接改）"""
    return data.setdefault("user", {})


def read_onload_path(toml_file: Path | None = None) -> str | None:
    """读取 onload 入口（None = 未配置）。toml_file 仅测试用。"""
    data = _read_toml(toml_file)
    for section in (data.get("user", {}), data):
        v = section.get("onload_path")
        if v:
            return str(v)
    return None


def write_onload_path(path: str | None, toml_file: Path | None = None) -> None:
    """写入 / 清除 onload 入口，保留 toml 其它配置。path=None 表示清除。"""
    data = _read_toml(toml_file)
    user = _user_section(data, toml_file)
    if path is None:
        user.pop("onload_path", None)
    else:
        user["onload_path"] = _norm(path)
    _write_toml(data, toml_file)


def read_onload_modules(toml_file: Path | None = None) -> list[str]:
    """读取自动加载模块列表（空列表 = 无）。"""
    data = _read_toml(toml_file)
    for section in (data.get("user", {}), data):
        v = section.get("onload_modules")
        if isinstance(v, list):
            return [str(x) for x in v]
    return []


def write_onload_modules(modules: list[str], toml_file: Path | None = None) -> None:
    """写入自动加载模块列表，保留 toml 其它配置。"""
    data = _read_toml(toml_file)
    user = _user_section(data, toml_file)
    user["onload_modules"] = [_norm(m) for m in modules]
    _write_toml(data, toml_file)


def merge_self_entry(self_path: str, toml_file: Path | None = None) -> tuple[str, list[str]]:
    """确保 self_path 成为 onload 入口；原入口若是其它文件则移入加载列表。

    返回 (入口路径, 模块列表)。幂等：重复调用无副作用。"""
    current = read_onload_path(toml_file)
    if current and current != _norm(self_path):
        modules = read_onload_modules(toml_file)
        if current not in modules:
            write_onload_modules([current] + modules, toml_file)
    write_onload_path(self_path, toml_file)
    return read_onload_path(toml_file) or _norm(self_path), read_onload_modules(toml_file)


def _dump_toml(data: dict) -> str:
    """dict → TOML 文本（字符串/布尔/数字/列表，保留段结构）"""
    lines = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for k, v in value.items():
                lines.append(_toml_kv(k, v))
        else:
            lines.append(_toml_kv(key, value))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _toml_kv(key: str, value) -> str:
    if isinstance(value, bool):
        return f"{key} = {str(value).lower()}"
    if isinstance(value, str):
        # TOML 基本字符串：双引号需转义
        escaped = value.replace('"', '\\"')
        return f'{key} = "{escaped}"'
    if isinstance(value, list):
        items = ", ".join(_toml_str(v) for v in value)
        return f"{key} = [{items}]"
    return f"{key} = {value}"


def _toml_str(value) -> str:
    """TOML 字符串字面量（转义双引号）"""
    return f'"{str(value).replace(chr(34), chr(92) + chr(34))}"'


# ====================================================================
# CAD 内执行：自动注册 + 列表加载
# ====================================================================

def _self_path() -> str:
    return _norm(Path(__file__).resolve())


def _auto_register_self() -> None:
    """确保本脚本成为 onload 入口（迁移旧的单文件配置到列表）。"""
    self_path = _self_path()
    if read_onload_path() == self_path and not read_onload_modules():
        return  # 已是入口且列表为空，无需任何操作
    try:
        entry, modules = merge_self_entry(self_path)
    except Exception as err:
        print(f"\n[PyRxOnload] 自动注册失败：{err}\n"
              f"              可手动输入 ONLOAD 命令配置。")
        return
    print(f"\n[PyRxOnload] 已注册为 onload 入口（下次启动 AutoCAD 生效）：\n"
          f"  {entry}\n"
          f"自动加载列表（{len(modules)} 项）：")
    for m in modules:
        print(f"  - {m}")
    print(f"输入 ONLOAD 命令可随时管理。")


def _module_name_keys(path: str) -> list[str]:
    """模块名候选键（原名/大写/小写；PyRx 以文件名全大写注册）"""
    stem = Path(path).stem
    return [stem, stem.upper(), stem.lower()]


def _module_loaded(path: str) -> bool:
    """判断「目标文件对应的模块」是否已加载。

    按候选键（原名/大写/小写）查 sys.modules，且校验模块的 __file__
    与目标文件匹配（或模块无 __file__ = 已被 exec 重载破坏，视为加载
    过）——**仅键名相同但指向其它文件的模块（如小写键 'quaintdim'
    = 包）不算**，否则会误判 QuaintDim.py 已加载而走重载分支。

    实验证实（PyRxReloadProbe 探针，3.1.7.5730）：
    - PyRx 以「文件名全大写」为模块名注册进 sys.modules（reload 提示
      "Module FOUNDATION was never loaded" / "Success module
      PYRXONLOAD is reloaded"），故候选键含大写形式；
    - reloadPythonModule 对未加载模块不抛异常但**不加载**（仅打印
      警告），因此「全部用 reload」不可行，必须先判断。"""
    import sys
    target = str(Path(path).resolve()).lower()
    for key in _module_name_keys(path):
        mod = sys.modules.get(key)
        if mod is None:
            continue
        mfile = getattr(mod, "__file__", None)
        if mfile is None or str(Path(mfile).resolve()).lower() == target:
            return True
    return False


def _unload_module(path: str) -> None:
    """从 sys.modules 卸载目标文件对应的模块（重载 = 卸载 + 重新加载）。

    只删除「__file__ 与目标文件匹配」或「无 __file__（已被 exec 重载
    破坏）」的模块；**名字碰巧相同但指向其它文件的模块必须保留**——
    例如小写候选键 'quaintdim' 恰好是包名，若误删包，QuaintDim.py
    的 reload 链会 ImportError: parent 'quaintdim' not in sys.modules，
    模块执行中断、命令未注册。

    不用 PyRx 的 reloadPythonModule：它对带子模块结构的插件
    （如 QuaintDim.py 顶部有 importlib.reload 循环）内部会
    importlib.reload(非模块) 抛 TypeError 且模块代码中断，导致
    命令未重新注册；卸载后 loadPythonModule 是干净加载，函数
    __globals__ 保留 __file__（@command 包装器 change_cwd 依赖）。"""
    import sys
    target = str(Path(path).resolve()).lower()
    for key in _module_name_keys(path):
        mod = sys.modules.get(key)
        if mod is None:
            continue
        mfile = getattr(mod, "__file__", None)
        if mfile is None or str(Path(mfile).resolve()).lower() == target:
            sys.modules.pop(key, None)


def _sync_module_keys(path: str) -> None:
    """load 后补全 sys.modules 键，保持 PyRx 内部状态一致。

    PyRx 加载模块时注册键为文件名全大写（如 'QUAINTDIM'），而模块
    对象的 __name__ 是原始大小写（如 'QuaintDim'）。PyRx 的 PYLOAD
    对已加载模块执行 importlib.reload(模块对象)，reload 检查
    sys.modules[对象.__name__]——若该键缺失（被卸载）会
    ImportError: module QuaintDim not in sys.modules。

    因此把目标模块同时注册到 __name__ 键与候选键；**键已被其它文件
    占用的不动**（如小写键 'quaintdim' 是包，绝不能覆盖）。"""
    import sys
    target = str(Path(path).resolve()).lower()
    mod = None
    for m in sys.modules.values():
        mf = getattr(m, "__file__", None)
        if mf and str(Path(mf).resolve()).lower() == target:
            mod = m
            break
    if mod is None:
        return
    keys = set(_module_name_keys(path))
    name = getattr(mod, "__name__", "") or ""
    if name:
        keys.add(name)
    for k in keys:
        if not k:
            continue
        existing = sys.modules.get(k)
        if existing is not None and existing is not mod:
            emf = getattr(existing, "__file__", None)
            if emf and str(Path(emf).resolve()).lower() != target:
                continue  # 键被其它文件占用（如 quaintdim 包），不动
        sys.modules[k] = mod


def _load_module(path: str) -> tuple[bool, str]:
    """加载/重载单个模块：已加载 → 卸载后重新加载，否则 → 加载。

    实验证实（探针 PROBE-3/4）：load 已加载模块无异常但不刷新代码，
    必须卸载后重载才拿到新代码；reload 未加载只是假成功。故必须按
    是否已加载分流，不能统一 load 或统一 reload。

    返回 (是否成功, 动作描述)。"""
    if _module_loaded(path):
        _unload_module(path)
        try:
            Ap.Application.loadPythonModule(path)
            _sync_module_keys(path)
            print(f"[PyRxOnload] 重载: {path}")
            return True, "重载"
        except Exception as err:
            print(f"[PyRxOnload] 失败 {path}: {err}")
            return False, "重载"
    try:
        Ap.Application.loadPythonModule(path)
        _sync_module_keys(path)
        print(f"[PyRxOnload] 加载: {path}")
        return True, "加载"
    except Exception as err:
        print(f"[PyRxOnload] 失败 {path}: {err}")
        return False, "加载"


def _load_onload_modules() -> tuple[int, int]:
    """加载列表中的全部模块（跳过自身，避免递归）。返回 (成功数, 失败数)。

    成功数含「入口自身」1 项：PyRxOnload.py 由 PyRx 的 onload_path
    负责加载，且当前正在运行（用户正通过它执行本函数），视为已加载
    成功——这样「自动加载项」总数 = 入口 + 列表，与用户看到的一致。"""
    ok = 1  # 入口自身（正在运行）
    fail = 0
    for mod in read_onload_modules():
        if _norm(mod) == _self_path():
            continue
        ok_, _ = _load_module(mod)
        if ok_:
            ok += 1
        else:
            fail += 1
    return ok, fail


# ====================================================================
# wx 管理界面（列表式，仿 QDSTYLE 设置对话框）
# ====================================================================

def _dialog_parent():
    """CAD 主窗口（wx.Window 或 None）。

    注意：PyRx 的 Ap.Application().mainWnd() 返回 HWND（int），不是
    wx.Window，不能作 wx 父窗口；Document.getWxWindow() 才是 wx.Window。"""
    try:
        win = Ap.curDoc().getWxWindow()
        if win is not None:
            return win
    except Exception:
        pass
    return None


class _OnloadDialog:
    """启动加载项管理对话框（对应 APPLOAD 的「内容/启动组」）"""

    def __init__(self):
        import wx
        self.wx = wx
        parent = _dialog_parent()
        self.dlg = wx.Dialog(parent, title="PyRx 启动加载项 (onload)")
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(self.dlg, label="自动加载的 Python 文件（每次启动依次加载）:"),
                  0, wx.ALL, 8)

        self.listbox = wx.ListBox(self.dlg, style=wx.LB_SINGLE)
        sizer.Add(self.listbox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.txt_status = wx.StaticText(self.dlg, label="")
        sizer.Add(self.txt_status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        b_add = wx.Button(self.dlg, label="添加...")
        b_remove = wx.Button(self.dlg, label="移除")
        b_load_sel = wx.Button(self.dlg, label="立即加载")
        b_load_all = wx.Button(self.dlg, label="全部加载")
        b_close = wx.Button(self.dlg, label="关闭")
        for b in (b_add, b_remove, b_load_sel, b_load_all, b_close):
            btn_row.Add(b, 0, wx.ALL, 4)
        sizer.Add(btn_row, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        b_add.Bind(wx.EVT_BUTTON, self._on_add)
        b_remove.Bind(wx.EVT_BUTTON, self._on_remove)
        b_load_sel.Bind(wx.EVT_BUTTON, self._on_load_selected)
        b_load_all.Bind(wx.EVT_BUTTON, self._on_load_all)
        b_close.Bind(wx.EVT_BUTTON, self._on_close)
        self.dlg.Bind(wx.EVT_CLOSE, self._on_close)
        # 双击列表项 = 立即加载选中项（已加载则重载）
        self.listbox.Bind(wx.EVT_LISTBOX_DCLICK, self._on_load_selected)
        # Esc = 关闭（对话框无标准 ID 按钮时 Esc 默认被忽略）
        self.dlg.Bind(wx.EVT_CHAR_HOOK, self._on_escape)

        # 关键：必须 SetSizer，否则控件不参与布局（按钮会丢失/重叠）
        self.dlg.SetSizer(sizer)
        self.dlg.SetMinSize((640, 340))
        self.dlg.Fit()
        self.dlg.Centre()

        self._refresh()

    # ---- 内部 ----

    def _set_status(self, text: str):
        self.txt_status.SetLabel(text)
        self.dlg.Layout()

    def _refresh(self):
        """按当前配置刷新列表与状态行"""
        self.modules = read_onload_modules()
        self.listbox.Clear()
        for m in self.modules:
            self.listbox.Append(m)
        entry = read_onload_path()
        self._set_status(f"onload 入口：{entry or '未设置'}\n"
                         f"列表共 {len(self.modules)} 项。下次启动依次加载；"
                         f"选中项「立即加载」/双击，已加载的自动重载，否则加载")

    def _on_add(self, event):
        import wx
        dlg = wx.FileDialog(
            self.dlg, message="选择要自动加载的 Python 文件",
            defaultDir=str(Path(__file__).resolve().parent),
            wildcard="Python 文件 (*.py)|*.py|所有文件 (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        # 注意：with 退出即销毁对话框，GetPath() 必须在 with 块内取
        with dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = _norm(dlg.GetPath())
        modules = read_onload_modules()
        if path in modules:
            self._set_status(f"已在列表中：{path}")
            return
        write_onload_modules(modules + [path])
        self._refresh()
        self._set_status(f"已添加：{path}（下次启动生效）")

    def _on_remove(self, event):
        sel = self.listbox.GetSelection()
        modules = read_onload_modules()
        if sel < 0 or sel >= len(modules):
            self._set_status("请先选中要移除的项")
            return
        removed = modules.pop(sel)
        write_onload_modules(modules)
        self._refresh()
        self._set_status(f"已移除：{removed}（下次启动生效）")

    def _on_load_selected(self, event):
        """立即加载选中项：已加载 → 重载（PYRELOAD），否则 → 加载（PYLOAD）"""
        sel = self.listbox.GetSelection()
        modules = read_onload_modules()
        if sel < 0 or sel >= len(modules):
            self._set_status("请先选中要加载的项")
            return
        ok, verb = _load_module(modules[sel])
        self._set_status(f"{verb}完成：{modules[sel]}" if ok
                         else f"{verb}失败：{modules[sel]}")

    def _on_load_all(self, event):
        """立即加载列表全部（每项同样先判断 load / reload）"""
        ok, fail = _load_onload_modules()
        self._set_status(f"加载完成：成功 {ok} 项（含入口 1 项），失败 {fail} 项")

    def _on_close(self, event):
        self.dlg.EndModal(0)

    def _on_escape(self, event):
        """Esc = 关闭对话框"""
        if event.GetKeyCode() == self.wx.WXK_ESCAPE:
            self._on_close(event)
        else:
            event.Skip()

    def show(self):
        self.dlg.ShowModal()
        self.dlg.Destroy()


# ====================================================================
# 命令注册 + 自动注册（仅 CAD 内）
# ====================================================================

if Ap is not None and command is not None:
    @command
    def onload():
        """PyRx onload 启动加载项管理（GUI，类似 APPLOAD 启动组）"""
        _OnloadDialog().show()

    _auto_register_self()
    ok, fail = _load_onload_modules()
    print(f"\n[PyRxOnload.py loaded] 自动加载项共 {ok + fail} 项（含入口自身）："
          f"成功 {ok} 项，失败 {fail} 项。输入 ONLOAD 管理。")
