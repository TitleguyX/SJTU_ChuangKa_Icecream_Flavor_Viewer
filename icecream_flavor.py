# -*- coding: utf-8 -*-
"""交图创咖 / 交环创咖 —— 当日冰淇淋口味自动查询

数据来源
--------
微信小程序商城（凡科）的商品列表接口：

* 交图创咖（主图） aid = 32677668
* 交环创咖（环院） aid = 32822471

工作原理
--------
商家并不在 SKU 规格里写冰淇淋口味，而是直接改写**商品名称**来代表当天供应
的口味，例如：

    香草冰淇淋雪底拿铁 / 香草·筒甜 / 香草黑武士·筒甜 / 香草圣代 /
    香草阿芙佳朵 / 香草雪底茉莉绿茶 / 香草吐冰
    草莓冰淇淋雪底美式 / 草莓·筒甜 / 草莓味甜筒 / 草莓味旗杆圣代 / 草莓雪底红茶

所以流程是：

    拉取全部商品名  ->  筛出"冰淇淋类"商品  ->  从名字里提取口味

只有下面 5 种口味会被识别（其余一切商品名一律忽略）：

    香草 / 草莓 / 抹茶 / 巧克力 / 茉莉乌龙

关键点是**不能**直接全名搜索口味词，否则"香草拿铁""桂花乌龙炖桃胶"
"半熟芝士糕点（抹茶味）"这类非冰淇淋商品会污染结果；同时"香草雪底茉莉绿茶"
里的"茉莉绿茶"只是茶底，不是口味。因此识别时只看冰淇淋特征词**之前**的
那一段文字（兜底才看全名）。

用法
----
    python ice_cream_flavor.py                # 主图：香草冰淇淋，环院：草莓冰淇淋
    python ice_cream_flavor.py --json         # 结构化输出，便于别的程序读取
    python ice_cream_flavor.py -v             # 附带调试信息（命中的商品名）
    python ice_cream_flavor.py --combinations # 不联网，逐个打印 25 种搭配各自的行

5x5 = 25 种口味搭配总表
------------------------
``FLAVOR_COMBINATIONS`` 是一个 25 元素的列表，每个元素含两个变量：

    [主图口味, 环院口味]

例如 ``["香草", "香草"]``、``["香草", "草莓"]`` ... ``["茉莉乌龙", "茉莉乌龙"]``，
``render_all_combinations()`` 会针对 25 个元素分别生成各自不同的输出行。

实时查询结果分别存放在两个独立变量里：

    main_flavors  -> 交图创咖（主图）的口味列表，如 ["香草"]
    huan_flavors  -> 交环创咖（环院）的口味列表，如 ["草莓"]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------
# 常量配置
# --------------------------------------------------------------------------

API_URL = "https://m.yk.fkw.com/api/product/list"
API_VERS = "20260902"
LIMIT = 200          # 每页条数（接口上限 200）
MAX_PAGES = 10       # 翻页保护上限
TIMEOUT = 15         # 单次请求超时（秒）
RETRIES = 2          # 每页失败重试次数

AID_ZHUTU = 32677668   # 交图创咖（主图）
AID_HUANYUAN = 32822471  # 交环创咖（环院）

SITE_ZHUTU = "主图"
SITE_HUANYUAN = "环院"

#: 允许出现的全部口味，输出顺序也按这个顺序排列
FLAVORS = ("香草", "草莓", "抹茶", "巧克力", "茉莉乌龙")

#: 口味别名：商品名里可能出现的写法
FLAVOR_ALIASES = {
    "香草": ("香草",),
    "草莓": ("草莓",),
    "抹茶": ("抹茶",),
    "巧克力": ("巧克力",),
    # "茉莉乌龙"可能被简写成"乌龙"或"茉莉"；"茉莉绿茶"只是茶底，
    # 因此仅在冰淇淋特征词之前的那段文字里才认这几个别名。
    "茉莉乌龙": ("茉莉乌龙", "乌龙", "茉莉"),
}

#: 5x5 = 25 种口味搭配总表。每个元素都是一个**二元列表**，
#: 第一个变量是该搭配下"主图（交图创咖）"的冰淇淋口味，
#: 第二个变量是"环院（交环创咖）"的冰淇淋口味。
#: 顺序为 FLAVORS 的笛卡尔积：主图口味在外层，环院口味在内层。
FLAVOR_COMBINATIONS: list[list[str]] = [
    # ---- 主图：香草 ----
    ["香草", "香草"],
    ["香草", "草莓"],
    ["香草", "抹茶"],
    ["香草", "巧克力"],
    ["香草", "茉莉乌龙"],
    # ---- 主图：草莓 ----
    ["草莓", "香草"],
    ["草莓", "草莓"],
    ["草莓", "抹茶"],
    ["草莓", "巧克力"],
    ["草莓", "茉莉乌龙"],
    # ---- 主图：抹茶 ----
    ["抹茶", "香草"],
    ["抹茶", "草莓"],
    ["抹茶", "抹茶"],
    ["抹茶", "巧克力"],
    ["抹茶", "茉莉乌龙"],
    # ---- 主图：巧克力 ----
    ["巧克力", "香草"],
    ["巧克力", "草莓"],
    ["巧克力", "抹茶"],
    ["巧克力", "巧克力"],
    ["巧克力", "茉莉乌龙"],
    # ---- 主图：茉莉乌龙 ----
    ["茉莉乌龙", "香草"],
    ["茉莉乌龙", "草莓"],
    ["茉莉乌龙", "抹茶"],
    ["茉莉乌龙", "巧克力"],
    ["茉莉乌龙", "茉莉乌龙"],
]

#: 搭配总数下限，5x5 = 25
COMBINATION_COUNT = len(FLAVORS) ** 2

#: 商品名里只要出现其中之一，就认为是"冰淇淋类"商品
ICE_CREAM_MARKERS = (
    "冰淇淋",
    "冰激凌",
    "雪底",     # 香草雪底红茶 / 草莓雪底茉莉绿茶
    "筒甜",     # 香草·筒甜 / 黑武士·筒甜
    "甜筒",     # 草莓味甜筒
    "圣代",     # 香草圣代 / 香草旗杆圣代
    "阿芙佳朵",
    "吐冰",     # 香草吐冰
)

#: 小程序请求头（微信 UA，服务端对小程序的接口偶有校验）
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
        "MicroMessenger/8.0.40(0x18002832) NetType/WIFI Language/zh_CN"
    ),
    "Referer": "https://m.yk.fkw.com/",
    "Accept": "application/json, text/plain, */*",
}

# --------------------------------------------------------------------------
# 两个独立变量：分别保存两个小程序的当日冰淇淋口味
# --------------------------------------------------------------------------
#: 交图创咖（主图）的口味，如 ["香草"]
main_flavors: list[str] | None = None
#: 交环创咖（环院）的口味，如 ["草莓"]
huan_flavors: list[str] | None = None


# --------------------------------------------------------------------------
# 一、口味识别（纯函数，可离线单元测试）
# --------------------------------------------------------------------------

def ice_cream_prefix(name: str) -> str | None:
    """返回商品名中第一个冰淇淋特征词之前的部分。

    不是冰淇淋类商品时返回 ``None``。

    >>> ice_cream_prefix("香草冰淇淋雪底拿铁")
    '香草'
    >>> ice_cream_prefix("黑武士·草莓味甜筒")
    '黑武士·草莓味'
    >>> ice_cream_prefix("香草拿铁") is None
    True
    """
    cut = None
    for marker in ICE_CREAM_MARKERS:
        pos = name.find(marker)
        if pos >= 0 and (cut is None or pos < cut):
            cut = pos
    return None if cut is None else name[:cut]


def _match_flavors(text: str) -> list[str]:
    """在给定文本里按固定顺序找出所有出现的口味。"""
    return [
        flavor
        for flavor in FLAVORS
        if any(alias in text for alias in FLAVOR_ALIASES[flavor])
    ]


def detect_flavors_from_name(name: str) -> list[str]:
    """从单个商品名里识别冰淇淋口味，非冰淇淋商品返回空列表。

    >>> detect_flavors_from_name("香草冰淇淋雪底拿铁")
    ['香草']
    >>> detect_flavors_from_name("香草雪底茉莉绿茶")   # 茉莉绿茶是茶底，不是口味
    ['香草']
    >>> detect_flavors_from_name("桂花乌龙炖桃胶")
    []
    """
    if not name:
        return []
    prefix = ice_cream_prefix(name)
    if prefix is None:
        return []
    # 正常情况下口味写在特征词之前；"冰淇淋·茉莉乌龙"这类前缀为空的名字
    # 兜底用全名再匹配一次。
    return _match_flavors(prefix) or _match_flavors(name)


def extract_flavors(product_names) -> list[str]:
    """从商品名列表里汇总当天冰淇淋口味（去重、按 FLAVORS 固定顺序）。

    >>> extract_flavors(["香草·筒甜", "香草圣代", "香草拿铁"])
    ['香草']
    >>> extract_flavors(["草莓味甜筒", "香草圣代"])
    ['香草', '草莓']
    """
    found = set()
    for name in product_names:
        found.update(detect_flavors_from_name(name or ""))
    return [flavor for flavor in FLAVORS if flavor in found]


def ice_cream_products(product_names) -> list[str]:
    """筛出全部冰淇淋类商品名（调试用）。"""
    return [n for n in product_names if ice_cream_prefix(n or "") is not None]


# --------------------------------------------------------------------------
# 二、结果格式化
# --------------------------------------------------------------------------

def describe(flavors) -> str:
    """把口味列表描述成 "香草冰淇淋" / "香草、草莓冰淇淋" / "无冰淇淋" / "未知"。

    >>> describe(["香草"])
    '香草冰淇淋'
    >>> describe(["香草", "草莓"])
    '香草、草莓冰淇淋'
    >>> describe([])
    '无冰淇淋'
    >>> describe(None)
    '未知'
    """
    if flavors is None:
        return "未知"
    if not flavors:
        return "无冰淇淋"
    return "、".join(flavors) + "冰淇淋"


def format_line(main_result, huan_result) -> str:
    """生成最终输出："主图：xx冰淇淋，环院：xx冰淇淋"。

    >>> format_line(["香草"], ["草莓"])
    '主图：香草冰淇淋，环院：草莓冰淇淋'
    """
    return f"{SITE_ZHUTU}：{describe(main_result)}，{SITE_HUANYUAN}：{describe(huan_result)}"


# --------------------------------------------------------------------------
# 二之二、25 种口味搭配表：逐元素生成各自的输出
# --------------------------------------------------------------------------

def validate_combinations(combinations=None) -> None:
    """自检搭配表：元素个数不少于 25，每个元素恰好两个合法口味，且不重不漏。

    不满足时抛 ``ValueError``。

    >>> validate_combinations()          # 默认表通过检查
    >>> validate_combinations([["香草", "草莓"]])
    Traceback (most recent call last):
        ...
    ValueError: 搭配表元素个数 1，少于要求的 25
    """
    combinations = FLAVOR_COMBINATIONS if combinations is None else combinations

    if len(combinations) < COMBINATION_COUNT:
        raise ValueError(
            f"搭配表元素个数 {len(combinations)}，少于要求的 {COMBINATION_COUNT}"
        )

    expected = {(main, huan) for main in FLAVORS for huan in FLAVORS}
    seen = set()

    for index, pair in enumerate(combinations):
        if len(pair) != 2:
            raise ValueError(f"第 {index} 个元素不是两个变量：{pair!r}")
        main_flavor, huan_flavor = pair
        for flavor in (main_flavor, huan_flavor):
            if flavor not in FLAVORS:
                raise ValueError(f"第 {index} 个元素含未知口味：{pair!r}")
        seen.add((main_flavor, huan_flavor))

    missing = expected - seen
    if missing:
        raise ValueError(f"搭配表缺少 {len(missing)} 种组合：{sorted(missing)}")


def count_combinations(combinations=None) -> int:
    """搭配表元素个数。

    >>> count_combinations()
    25
    """
    combinations = FLAVOR_COMBINATIONS if combinations is None else combinations
    return len(combinations)


def render_combination(pair) -> str:
    """把单个搭配元素渲染成一行输出。

    元素里的两个变量分别当作主图、环院当天的口味。

    >>> render_combination(["香草", "香草"])
    '主图：香草冰淇淋，环院：香草冰淇淋'
    >>> render_combination(["香草", "草莓"])
    '主图：香草冰淇淋，环院：草莓冰淇淋'
    >>> render_combination(["茉莉乌龙", "巧克力"])
    '主图：茉莉乌龙冰淇淋，环院：巧克力冰淇淋'
    """
    main_flavor, huan_flavor = pair          # 第一个变量：主图口味
    return format_line([main_flavor], [huan_flavor])


def render_all_combinations(combinations=None) -> list[str]:
    """逐个元素生成各自不同的输出行，返回 25 行文本。

    >>> lines = render_all_combinations()
    >>> len(lines)
    25
    >>> len(set(lines))          # 25 行互不相同
    25
    >>> lines[0]
    '主图：香草冰淇淋，环院：香草冰淇淋'
    >>> lines[1]
    '主图：香草冰淇淋，环院：草莓冰淇淋'
    >>> lines[-1]
    '主图：茉莉乌龙冰淇淋，环院：茉莉乌龙冰淇淋'
    """
    combinations = FLAVOR_COMBINATIONS if combinations is None else combinations
    return [render_combination(pair) for pair in combinations]


def find_combination(main_result, huan_result):
    """把实际查询到的口味对回搭配表：返回 ``(下标, 元素)``，无法定位则 ``None``。

    下标从 0 开始；展示给用户时记得 +1。
    只有两个站点各自都恰好识别出 1 种口味时才能定位。

    >>> find_combination(["香草"], ["草莓"])
    (1, ['香草', '草莓'])
    >>> find_combination(["香草", "草莓"], ["抹茶"]) is None
    True
    >>> find_combination([], ["抹茶"]) is None
    True
    """
    if not main_result or not huan_result:
        return None
    if len(main_result) != 1 or len(huan_result) != 1:
        return None
    pair = [main_result[0], huan_result[0]]
    for index, item in enumerate(FLAVOR_COMBINATIONS):
        if item == pair:
            return index, item
    return None


# --------------------------------------------------------------------------
# 三、网络请求
# --------------------------------------------------------------------------

def build_url(aid: int, page: int = 1, limit: int = LIMIT, vers: str = API_VERS) -> str:
    """拼出商品列表接口地址。

    >>> build_url(32677668, 1)
    'https://m.yk.fkw.com/api/product/list?aid=32677668&yid=1&storeId=0&page=1&limit=200&vers=20260902&__from=1'
    """
    query = urllib.parse.urlencode(
        {
            "aid": aid,
            "yid": 1,
            "storeId": 0,
            "page": page,
            "limit": limit,
            "vers": vers,
            "__from": 1,
        }
    )
    return f"{API_URL}?{query}"


def http_get_json(url: str, timeout: int = TIMEOUT) -> dict:
    """GET 一个 JSON 接口并返回解析后的字典。"""
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def fetch_all_product_names(
    aid: int,
    *,
    limit: int = LIMIT,
    max_pages: int = MAX_PAGES,
    timeout: int = TIMEOUT,
    retries: int = RETRIES,
    opener=None,
) -> list[str]:
    """翻页拉取某个小程序（aid）的全部商品名。

    ``opener`` 可注入，便于离线测试；默认走 ``http_get_json``。
    """
    opener = opener or http_get_json
    names: list[str] = []

    for page in range(1, max_pages + 1):
        last_error: Exception | None = None
        payload = None
        for attempt in range(retries + 1):
            try:
                payload = opener(build_url(aid, page, limit), timeout)
                break
            except Exception as exc:  # noqa: BLE001 - 网络异常种类多，统一重试
                last_error = exc
                if attempt < retries:
                    time.sleep(0.5 * (attempt + 1))
        if payload is None:
            raise RuntimeError(f"第 {page} 页请求失败：{last_error!r}") from last_error

        if payload.get("code") not in (0, None):
            raise RuntimeError(f"接口返回错误：code={payload.get('code')} msg={payload.get('msg')!r}")

        items = payload.get("dataList") or []
        names.extend(str(item.get("name") or "") for item in items)

        if len(items) < limit:   # 已经是最后一页
            break

    return names


def query_flavors(aid: int, *, opener=None, verbose: bool = False) -> list[str]:
    """查询单个小程序当天的冰淇淋口味。"""
    names = fetch_all_product_names(aid, opener=opener)
    flavors = extract_flavors(names)
    if verbose:
        print(f"    [aid={aid}] 商品 {len(names)} 条，冰淇淋商品：")
        for name in ice_cream_products(names):
            print(f"      - {name}")
        print(f"    [aid={aid}] 识别口味：{flavors or '无'}")
    return flavors


# --------------------------------------------------------------------------
# 四、主流程
# --------------------------------------------------------------------------

def query_both(*, opener=None, verbose: bool = False):
    """查询两个小程序，返回 ``(main_flavors, huan_flavors)`` 两个独立变量。

    查询失败时对应变量为 ``None``。
    """
    results: dict[str, list[str] | None] = {}
    for label, aid in ((SITE_ZHUTU, AID_ZHUTU), (SITE_HUANYUAN, AID_HUANYUAN)):
        if verbose:
            print(f"  -> 查询{label}创咖（aid={aid}）...")
        try:
            results[label] = query_flavors(aid, opener=opener, verbose=verbose)
        except Exception as exc:  # noqa: BLE001 - 单站失败不影响另一站
            print(f"  !! {label}查询失败：{exc}", file=sys.stderr)
            results[label] = None
    return results[SITE_ZHUTU], results[SITE_HUANYUAN]


def print_combinations(as_json: bool = False) -> None:
    """逐元素打印 25 种搭配各自的输出。"""
    lines = render_all_combinations()
    if as_json:
        print(json.dumps(
            [
                {
                    "序号": index,
                    "主图": pair[0],
                    "环院": pair[1],
                    "line": line,
                }
                for index, (pair, line) in enumerate(zip(FLAVOR_COMBINATIONS, lines), 1)
            ],
            ensure_ascii=False,
            indent=2,
        ))
        return
    width = len(str(len(lines)))
    for index, (pair, line) in enumerate(zip(FLAVOR_COMBINATIONS, lines), 1):
        print(f"{index:>{width}}. [主图={pair[0]} 环院={pair[1]}]  {line}")


def main(argv=None) -> int:
    global main_flavors, huan_flavors

    parser = argparse.ArgumentParser(
        description="查询交图创咖 / 交环创咖当天的冰淇淋口味"
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 形式输出")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印调试信息")
    parser.add_argument(
        "--combinations", action="store_true",
        help="不联网，逐个打印 5x5=25 种口味搭配各自的输出",
    )
    args = parser.parse_args(argv)

    try:  # Windows 控制台默认 GBK，强制 UTF-8 避免中文乱码
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - 不支持时忽略
        pass

    # 搭配表自检：必须覆盖全部 25 种组合
    validate_combinations()

    if args.combinations:
        print_combinations(as_json=args.json)
        return 0

    main_flavors, huan_flavors = query_both(verbose=args.verbose)
    line = format_line(main_flavors, huan_flavors)
    matched = find_combination(main_flavors, huan_flavors)

    if args.verbose:
        if matched is None:
            print("  -> 未能定位到 25 种搭配中的某一种")
        else:
            index, pair = matched
            print(f"  -> 命中搭配表第 {index + 1} 个元素：[主图={pair[0]} 环院={pair[1]}]")

    if args.json:
        print(json.dumps(
            {
                "主图": {"aid": AID_ZHUTU, "flavors": main_flavors,
                        "text": describe(main_flavors)},
                "环院": {"aid": AID_HUANYUAN, "flavors": huan_flavors,
                        "text": describe(huan_flavors)},
                "line": line,
                "combination_index": None if matched is None else matched[0],
                "combination_number": None if matched is None else matched[0] + 1,
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(line)

    # 任一站点查询失败 -> 非零退出码，方便脚本/定时任务告警
    return 1 if (main_flavors is None or huan_flavors is None) else 0


if __name__ == "__main__":
    raise SystemExit(main())
