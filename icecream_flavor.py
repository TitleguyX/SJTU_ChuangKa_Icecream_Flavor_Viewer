#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动获取「交圕创咖」（主图）与「交环创咖」（环院）微信小程序中
当天的冰淇淋口味，并按指定格式输出（每家一行）：

    主图：香草冰淇淋
    环院：草莓冰淇淋

原理
----
两个小程序都是「凡科云咖」平台的商城小程序，商品数据由公开的
HTTP 接口提供，读取商品列表不需要登录态：

    GET https://m.yk.fkw.com/api/product/list
        ?aid=<商家ID>&yid=1&storeId=0&page=1&limit=100&vers=20260902&__from=1

其中 aid（商家 ID）来自小程序启动时微信注入的 ext 配置：

    交圕创咖  appid=wx75bb54d92afd9012  aid=32677668
    交环创咖  appid=wx22bf83bcf4641676  aid=32822471

程序拉取当前在售商品，筛出冰淇淋类商品（圣代 / 甜筒 / 筒甜 /
阿芙佳朵 / 雪底 / 吐冰 / 冰淇淋 …），其商品名中的口味词即为当天口味。
同一天同一家店内所有冰淇淋商品口味一致，因此直接取口味，无需统计。

依赖：仅标准库（Python 3.7+）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

API_HOST = "https://m.yk.fkw.com"
API_PATH = "/api/product/list"
API_VERS = "20260902"

# 两个小程序的配置（appid 来自微信小程序包目录，aid 来自微信注入的 ext.json）
SHOPS = [
    {
        "key": "主图",
        "title": "交圕创咖",
        "appid": "wx75bb54d92afd9012",
        "aid": 32677668,
        "yid": 1,
    },
    {
        "key": "环院",
        "title": "交环创咖",
        "appid": "wx22bf83bcf4641676",
        "aid": 32822471,
        "yid": 1,
    },
]

# 判定「这是冰淇淋类商品」的关键词
ICE_CREAM_HINTS = (
    "冰淇淋", "冰激凌", "冰淇凌", "雪糕", "圣代", "甜筒", "筒甜",
    "阿芙佳朵", "雪底", "吐冰",
)

# 口味关键词：只认这五种口味
FLAVORS = (
    "香草", "草莓", "巧克力", "抹茶", "茉莉乌龙",
)

NO_ICE_CREAM = "未找到冰淇淋商品"

PAUSE_ENV = "ICECREAM_NO_PAUSE"


# --------------------------------------------------------------------------
# 双击运行时也能看到输出：控制台编码 + 结束后暂停
# --------------------------------------------------------------------------

def _setup_console() -> None:
    """让 Windows 控制台能正确显示中文，并设置窗口标题。"""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
            ctypes.windll.kernel32.SetConsoleTitleW("创咖今日冰淇淋口味")
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _process_ancestors(limit: int = 5) -> list[str]:
    """返回当前进程的祖先进程名，从直接父进程开始，最多 limit 个。

    取不到时返回空列表（非 Windows、权限不足等），调用方需能容忍。
    """
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

        invalid = ctypes.c_void_p(-1).value
        snap = k32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
        if snap == invalid:
            return []
        table: dict[int, tuple[int, str]] = {}
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ok = k32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
                ok = k32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            k32.CloseHandle(snap)

        names: list[str] = []
        pid = os.getpid()
        for _ in range(limit):
            row = table.get(pid)
            if row is None:
                break
            ppid = row[0]
            if not ppid or ppid == pid:
                break
            parent = table.get(ppid)
            if parent is None:
                break
            names.append(parent[1])
            pid = ppid
        return names
    except Exception:
        return []


def _parent_process_name() -> str:
    """返回直接父进程的可执行文件名（取不到则返回空串）。"""
    names = _process_ancestors(1)
    return names[0] if names else ""


PYTHON_LAUNCHERS = frozenset(
    {"py.exe", "pyw.exe", "python.exe", "pythonw.exe", "python3.exe"}
)
EXPLORER_NAMES = frozenset({"explorer.exe", "explorer"})


def _launched_by_double_click() -> bool:
    """判断是否由资源管理器双击启动（此时控制台用完就会被关掉）。

    双击 .py 时链路通常是 explorer.exe -> python.exe；
    若 .py 关联到 py 启动器，则是 explorer.exe -> py.exe -> python.exe。
    因此要跳过中间的 Python 启动器，看第一个「真正的」父进程。
    从终端运行时该父进程是 powershell.exe / cmd.exe 等，不会误判。
    """
    for name in _process_ancestors(4):
        if name.lower() in PYTHON_LAUNCHERS:
            continue
        return name.lower() in EXPLORER_NAMES
    return False


def _maybe_pause(force: bool = False, disable: bool = False) -> None:
    """双击启动时暂停，等用户看完输出再关闭窗口。"""
    if disable or os.environ.get(PAUSE_ENV):
        return
    if not force and not _launched_by_double_click():
        return
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        input("\n按回车键关闭窗口...")
    except (EOFError, KeyboardInterrupt):
        pass


class FetchError(RuntimeError):
    """接口请求失败。"""


def _http_get_json(url: str, timeout: float = 20.0, retries: int = 3) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 MicroMessenger/3.9.0 MiniProgramEnv/Windows"
        ),
        "Referer": API_HOST + "/",
        "Accept": "application/json, text/plain, */*",
    }
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw)
        except urllib.error.HTTPError as exc:  # 业务错误也会带 JSON body
            body = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"success": False, "msg": f"HTTP {exc.code}"}
            # 400 表示参数不合法，重试无意义
            if exc.code == 400:
                raise FetchError(payload.get("msg") or f"HTTP {exc.code}") from exc
            last = FetchError(f"HTTP {exc.code}: {payload.get('msg')}")
        except Exception as exc:  # 网络抖动，重试
            last = exc
        if attempt < retries:
            time.sleep(0.8 * attempt)
    raise FetchError(str(last))


def fetch_products(shop: dict, page_size: int = 100, max_pages: int = 20) -> list[dict]:
    """拉取指定商家的全部在售商品。"""
    products: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "aid": shop["aid"],
            "yid": shop["yid"],
            "storeId": 0,
            "page": page,
            "limit": page_size,
            "vers": API_VERS,
            "__from": 1,
        }
        url = f"{API_HOST}{API_PATH}?{urllib.parse.urlencode(params)}"
        resp = _http_get_json(url)
        if not resp.get("success", False):
            raise FetchError(f"{shop['key']} 接口返回失败: {resp.get('msg')}")
        batch = resp.get("dataList") or []
        if isinstance(batch, dict):
            batch = batch.get("list") or batch.get("dataList") or []
        products.extend(batch)
        if len(batch) < page_size:
            break
    return products


def detect_flavors(products: list[dict]) -> dict:
    """从商品列表读出冰淇淋口味。

    返回 {'flavors': [...], 'items': [(商品名, 命中口味), ...]}
    flavors 按首次出现顺序去重；同一天同一家店口味一致，正常只有一个。
    """
    flavors: list[str] = []
    items: list[tuple[str, list[str]]] = []

    for product in products:
        name = (product.get("name") or "").strip()
        if not name or not any(hint in name for hint in ICE_CREAM_HINTS):
            continue
        hit = [flavor for flavor in FLAVORS if flavor in name]
        items.append((name, hit))
        for flavor in hit:
            if flavor not in flavors:
                flavors.append(flavor)

    return {"flavors": flavors, "items": items}


def format_result(results: dict[str, dict], shops: list[dict]) -> str:
    """拼成每家一行、逗号换行的形式：

    主图：香草冰淇淋
    环院：草莓冰淇淋
    """
    lines = []
    for shop in shops:
        info = results[shop["key"]]
        if info.get("error"):
            value = f"获取失败（{info['error']}）"
        else:
            flavors = info["flavors"]
            value = "、".join(f + "冰淇淋" for f in flavors) if flavors else NO_ICE_CREAM
        lines.append(f"{shop['key']}：{value}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="获取交圕创咖（主图）与交环创咖（环院）当天冰淇淋口味",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出完整结果")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示命中的冰淇淋商品")
    parser.add_argument("--timeout", type=float, default=20.0, help="单次请求超时秒数")
    parser.add_argument("--pause", action="store_true", help="结束后暂停等待回车")
    parser.add_argument("--no-pause", action="store_true",
                        help="结束后不暂停（脚本调用时使用）")
    args = parser.parse_args(argv)

    _setup_console()

    code = 1
    try:
        code = _run(args)
    except Exception:
        traceback.print_exc()
        code = 1
    finally:
        _maybe_pause(force=args.pause, disable=args.no_pause)
    return code


def _run(args: argparse.Namespace) -> int:
    results: dict[str, dict] = {}
    errors: list[str] = []

    for shop in SHOPS:
        try:
            products = fetch_products(shop)
        except FetchError as exc:
            results[shop["key"]] = {"flavors": [], "items": [],
                                    "error": str(exc), "product_count": 0}
            errors.append(f"{shop['key']}({shop['title']}): {exc}")
            continue
        info = detect_flavors(products)
        info["product_count"] = len(products)
        info["error"] = None
        results[shop["key"]] = info

    output = format_result(results, SHOPS)

    if args.json:
        payload = {
            "date": time.strftime("%Y-%m-%d"),
            "shops": {
                shop["key"]: {
                    "title": shop["title"],
                    "appid": shop["appid"],
                    "aid": shop["aid"],
                    "flavors": results[shop["key"]]["flavors"],
                    "product_count": results[shop["key"]].get("product_count", 0),
                    "ice_cream_items": [
                        {"name": name, "flavors": hit}
                        for name, hit in results[shop["key"]]["items"]
                    ],
                    "error": results[shop["key"]].get("error"),
                }
                for shop in SHOPS
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(output)
        if args.verbose:
            print()
            for shop in SHOPS:
                info = results[shop["key"]]
                print(f"[{shop['key']}] {shop['title']} aid={shop['aid']} "
                      f"商品 {info.get('product_count', 0)} 件，冰淇淋商品 {len(info['items'])} 件")
                for name, hit in info["items"]:
                    print(f"    - {name}  ->  {'/'.join(hit) or '未识别口味'}")
                if info.get("error"):
                    print(f"    错误：{info['error']}")

    return 1 if errors and all(results[s["key"]].get("error") for s in SHOPS) else 0


if __name__ == "__main__":
    sys.exit(main())
