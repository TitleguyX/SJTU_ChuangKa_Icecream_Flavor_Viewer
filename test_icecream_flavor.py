# -*- coding: utf-8 -*-
"""ice_cream_flavor 的单元测试（标准库 unittest，无需第三方依赖）

运行：
    python -m unittest -v test_ice_cream_flavor

核心要求是覆盖 5x5 = 25 种口味组合，另外覆盖命名变体、茶底干扰、
翻页、接口异常等边界情况。全部离线，不发真实网络请求。

可选的真实联网回归测试：
    设置环境变量 ICECREAM_LIVE_TEST=1 后再运行即可。
"""

import contextlib
import doctest
import io
import json
import os
import unittest
import urllib.parse

import ice_cream_flavor as icf
from ice_cream_flavor import (
    AID_HUANYUAN,
    AID_ZHUTU,
    COMBINATION_COUNT,
    FLAVOR_COMBINATIONS,
    FLAVORS,
    build_url,
    count_combinations,
    describe,
    detect_flavors_from_name,
    extract_flavors,
    fetch_all_product_names,
    find_combination,
    format_line,
    ice_cream_prefix,
    query_both,
    render_all_combinations,
    render_combination,
    validate_combinations,
)

# --------------------------------------------------------------------------
# 测试素材：每种口味在各站点可能出现的商品名写法
# --------------------------------------------------------------------------

#: 交图创咖（主图）风格，取自 2026-09 的真实接口快照命名的规律
ZHUTU_TEMPLATES = {
    "香草": ["香草冰淇淋雪底拿铁", "香草冰淇淋雪底美式", "香草·筒甜",
             "香草黑武士·筒甜", "香草雪底茉莉绿茶", "香草阿芙佳朵",
             "香草旗杆圣代", "香草圣代", "香草吐冰"],
    "草莓": ["草莓冰淇淋雪底拿铁", "草莓冰淇淋雪底美式", "草莓·筒甜",
             "草莓黑武士·筒甜", "草莓雪底茉莉绿茶", "草莓阿芙佳朵",
             "草莓旗杆圣代", "草莓圣代", "草莓吐冰"],
    "抹茶": ["抹茶冰淇淋雪底拿铁", "抹茶冰淇淋雪底美式", "抹茶·筒甜",
             "抹茶黑武士·筒甜", "抹茶雪底茉莉绿茶", "抹茶阿芙佳朵",
             "抹茶旗杆圣代", "抹茶圣代", "抹茶吐冰"],
    "巧克力": ["巧克力冰淇淋雪底拿铁", "巧克力冰淇淋雪底美式", "巧克力·筒甜",
               "巧克力黑武士·筒甜", "巧克力雪底茉莉绿茶", "巧克力阿芙佳朵",
               "巧克力旗杆圣代", "巧克力圣代", "巧克力吐冰"],
    "茉莉乌龙": ["茉莉乌龙冰淇淋雪底拿铁", "茉莉乌龙冰淇淋雪底美式", "茉莉乌龙·筒甜",
                 "茉莉乌龙黑武士·筒甜", "茉莉乌龙雪底茉莉绿茶", "茉莉乌龙阿芙佳朵",
                 "茉莉乌龙旗杆圣代", "茉莉乌龙圣代", "茉莉乌龙吐冰"],
}

#: 交环创咖（环院）风格，多一个"味"字
HUANYUAN_TEMPLATES = {
    "香草": ["香草冰淇淋雪底拿铁", "香草冰淇淋雪底美式", "香草雪底红茶",
             "香草味旗杆圣代", "香草味圣代", "香草味甜筒", "香草味阿芙佳朵",
             "香草黑武士·筒甜", "香草·筒甜", "香草吐冰"],
    "草莓": ["草莓冰淇淋雪底拿铁", "草莓冰淇淋雪底美式", "草莓雪底红茶",
             "草莓味旗杆圣代", "草莓味圣代", "草莓味甜筒", "草莓味阿芙佳朵",
             "草莓黑武士·筒甜", "草莓·筒甜", "草莓吐冰"],
    "抹茶": ["抹茶冰淇淋雪底拿铁", "抹茶冰淇淋雪底美式", "抹茶雪底红茶",
             "抹茶味旗杆圣代", "抹茶味圣代", "抹茶味甜筒", "抹茶味阿芙佳朵",
             "抹茶黑武士·筒甜", "抹茶·筒甜", "抹茶吐冰"],
    "巧克力": ["巧克力冰淇淋雪底拿铁", "巧克力冰淇淋雪底美式", "巧克力雪底红茶",
               "巧克力味旗杆圣代", "巧克力味圣代", "巧克力味甜筒", "巧克力味阿芙佳朵",
               "巧克力黑武士·筒甜", "巧克力·筒甜", "巧克力吐冰"],
    "茉莉乌龙": ["茉莉乌龙冰淇淋雪底拿铁", "茉莉乌龙冰淇淋雪底美式", "茉莉乌龙雪底红茶",
                 "茉莉乌龙味旗杆圣代", "茉莉乌龙味圣代", "茉莉乌龙味甜筒",
                 "茉莉乌龙味阿芙佳朵", "茉莉乌龙黑武士·筒甜", "茉莉乌龙·筒甜",
                 "茉莉乌龙吐冰"],
}

#: 真实存在的干扰商品：含口味词，但不是冰淇淋，必须全部忽略
NOISE_PRODUCTS = [
    # --- 香草 ---
    "香草拿铁-PRO", "洱源·香草拿铁", "香草燕麦拿铁", "香草生椰拿铁",
    "香草拿铁", "香草风味咖啡浓缩液",
    # --- 草莓 ---
    "草莓雪顶气泡水",
    # --- 抹茶 ---
    "抹茶拿铁-PRO", "抹茶拿铁", "燕麦抹茶拿铁", "生椰抹茶", "椰青抹茶",
    "半熟芝士糕点（抹茶味）-1粒", "抹茶生巧", "牛奶抹茶绿豆沙",
    # --- 巧克力 ---
    "经典巧克力-PRO", "经典巧克力", "申浦酒心黑巧克力",
    "申浦酒心巧克力-小粒约6.5g", "申浦酒心巧克力-大粒约15g",
    "巧克力丹麦包-1个", "巧克力坚果脆", "申浦夜上海牛奶巧克力",
    "迪拜巧克力风味开心果千层蛋糕",
    # --- 茉莉乌龙 ---
    "桂花乌龙炖桃胶", "优倍鲜奶茉莉绿茶", "鲜奶茉莉绿茶", "茉莉绿茶",
    "芝士奶盖茉莉绿茶", "生椰茉莉绿茶", "燕麦茉莉绿茶",
]

#: 真实快照样本（2026-09 从接口实际抓到的名字）
SNAPSHOT_ZHUTU = [
    "回未幸运花酥·糕点", "纸杯", "豆浆绿茶", "BUFFTea全口味合集·交大伴手礼盒装",
    "桂花乌龙炖桃胶", "经典巧克力-PRO", "抹茶拿铁-PRO", "香草拿铁-PRO",
    "洱源·香草拿铁", "抹茶拿铁", "经典巧克力", "燕麦抹茶拿铁",
    "香草燕麦拿铁", "生椰抹茶", "椰青抹茶", "香草生椰拿铁", "香草拿铁",
    "香草风味咖啡浓缩液", "巧克力坚果脆", "茉莉绿茶",
    "香草冰淇淋雪底拿铁", "香草冰淇淋雪底美式", "香草·筒甜",
    "香草黑武士·筒甜", "香草雪底茉莉绿茶", "香草阿芙佳朵",
    "香草旗杆圣代", "香草圣代", "香草吐冰",
]
SNAPSHOT_HUANYUAN = [
    "抹茶生巧", "牛奶抹茶绿豆沙", "桂花乌龙炖桃胶", "半熟芝士糕点（抹茶味）-1粒",
    "抹茶拿铁-PRO", "抹茶拿铁", "燕麦抹茶拿铁", "生椰抹茶", "冰椰抹茶",
    "经典巧克力-PRO", "巧克力坚果脆", "茉莉绿茶", "鲜奶祁门红茶",
    "草莓雪底红茶", "草莓冰淇淋雪底拿铁", "草莓冰淇淋雪底美式",
    "草莓雪底茉莉绿茶", "草莓黑武士·筒甜", "草莓·筒甜",
    "草莓味旗杆圣代", "黑武士·草莓味甜筒", "草莓味圣代", "草莓味甜筒",
    "草莓味阿芙佳朵", "草莓吐冰",
]


# --------------------------------------------------------------------------
# 测试用的假接口
# --------------------------------------------------------------------------

def make_opener(datasets, calls=None):
    """构造一个假的接口实现。

    ``datasets``：{aid: [商品名, ...]}，超过 200 条会自动分页。
    ``calls``：可选列表，记录每次请求的 (aid, page)，用于验证翻页。
    """
    def opener(url, timeout=None):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        aid = int(query["aid"][0])
        page = int(query["page"][0])
        limit = int(query["limit"][0])
        if calls is not None:
            calls.append((aid, page))
        items = datasets.get(aid, [])
        chunk = items[(page - 1) * limit: page * limit]
        return {"code": 0, "dataList": [{"name": n} for n in chunk]}

    return opener


class IceCreamFlavorTest(unittest.TestCase):
    """主测试集。"""

    # ------------------------------------------------------------------
    # 1. 核心要求：5x5 = 25 种口味组合
    # ------------------------------------------------------------------
    def test_all_25_flavor_combinations(self):
        """遍历搭配表的 25 个元素，逐个元素验证两个变量与各自的输出。"""
        self.assertEqual(len(FLAVOR_COMBINATIONS), 25)

        for index, pair in enumerate(FLAVOR_COMBINATIONS, 1):
            main_flavor, huan_flavor = pair
            with self.subTest(序号=index, 主图=main_flavor, 环院=huan_flavor):
                datasets = {
                    AID_ZHUTU: ZHUTU_TEMPLATES[main_flavor] + NOISE_PRODUCTS,
                    AID_HUANYUAN: HUANYUAN_TEMPLATES[huan_flavor] + NOISE_PRODUCTS,
                }
                main_flavors, huan_flavors = query_both(opener=make_opener(datasets))

                # 两个变量各自独立、互不串味
                self.assertEqual(main_flavors, [main_flavor])
                self.assertEqual(huan_flavors, [huan_flavor])
                self.assertIsNot(main_flavors, huan_flavors)

                # 该元素自己的输出
                self.assertEqual(
                    format_line(main_flavors, huan_flavors),
                    f"主图：{main_flavor}冰淇淋，环院：{huan_flavor}冰淇淋",
                )
                self.assertEqual(render_combination(pair),
                                 format_line(main_flavors, huan_flavors))

    def test_25_combinations_with_single_product_each(self):
        """极简场景：每个站点当天只有 1 个冰淇淋商品，也要能正确识别。"""
        checked = 0
        for zhutu_flavor in FLAVORS:
            for huanyuan_flavor in FLAVORS:
                datasets = {
                    AID_ZHUTU: [f"{zhutu_flavor}·筒甜", "拿铁咖啡"],
                    AID_HUANYUAN: [f"{huanyuan_flavor}味甜筒", "美式"],
                }
                main_flavors, huan_flavors = query_both(opener=make_opener(datasets))
                self.assertEqual(main_flavors, [zhutu_flavor])
                self.assertEqual(huan_flavors, [huanyuan_flavor])
                checked += 1
        self.assertEqual(checked, 25)

    def test_25_combinations_with_real_snapshot_shape(self):
        """把 25 种组合混入真实快照，验证不被真实噪声商品干扰。"""
        for zhutu_flavor in FLAVORS:
            for huanyuan_flavor in FLAVORS:
                datasets = {
                    AID_ZHUTU: SNAPSHOT_ZHUTU + ZHUTU_TEMPLATES[zhutu_flavor],
                    AID_HUANYUAN: SNAPSHOT_HUANYUAN + HUANYUAN_TEMPLATES[huanyuan_flavor],
                }
                main_flavors, huan_flavors = query_both(opener=make_opener(datasets))
                self.assertIn(zhutu_flavor, main_flavors)
                self.assertIn(huanyuan_flavor, huan_flavors)

    # ------------------------------------------------------------------
    # 2. 真实快照
    # ------------------------------------------------------------------
    def test_real_snapshot_zhutu(self):
        """2026-09 的真实快照：交图创咖当天是香草。"""
        self.assertEqual(extract_flavors(SNAPSHOT_ZHUTU), ["香草"])

    def test_real_snapshot_huanyuan(self):
        """2026-09 的真实快照：交环创咖当天是草莓。"""
        self.assertEqual(extract_flavors(SNAPSHOT_HUANYUAN), ["草莓"])

    # ------------------------------------------------------------------
    # 3. 命名变体与口味别名
    # ------------------------------------------------------------------
    def test_every_flavor_naming_variant(self):
        """每一种命名模板都能被识别成对应口味。"""
        for flavor in FLAVORS:
            for name in ZHUTU_TEMPLATES[flavor] + HUANYUAN_TEMPLATES[flavor]:
                with self.subTest(口味=flavor, 商品=name):
                    self.assertEqual(detect_flavors_from_name(name), [flavor])

    def test_flavor_aliases(self):
        """茉莉乌龙允许写成 乌龙 / 茉莉。"""
        self.assertEqual(detect_flavors_from_name("乌龙味甜筒"), ["茉莉乌龙"])
        self.assertEqual(detect_flavors_from_name("茉莉乌龙味甜筒"), ["茉莉乌龙"])
        self.assertEqual(detect_flavors_from_name("茉莉味圣代"), ["茉莉乌龙"])

    def test_tea_base_is_not_flavor(self):
        """特征词之后的茶底不算口味："香草雪底茉莉绿茶" 只能是香草。"""
        self.assertEqual(detect_flavors_from_name("香草雪底茉莉绿茶"), ["香草"])
        self.assertEqual(detect_flavors_from_name("草莓雪底红茶"), ["草莓"])
        self.assertEqual(detect_flavors_from_name("草莓冰淇淋雪底拿铁"), ["草莓"])
        self.assertEqual(detect_flavors_from_name("草莓冰淇淋雪底美式"), ["草莓"])

    def test_ice_cream_prefix(self):
        self.assertEqual(ice_cream_prefix("香草冰淇淋雪底拿铁"), "香草")
        self.assertEqual(ice_cream_prefix("黑武士·草莓味甜筒"), "黑武士·草莓味")
        self.assertIsNone(ice_cream_prefix("香草拿铁"))
        self.assertIsNone(ice_cream_prefix(""))
        self.assertIsNone(ice_cream_prefix("桂花乌龙炖桃胶"))

    def test_shortest_marker_wins(self):
        """同时命中多个特征词时，取位置最靠前的那个作为分界。"""
        # "草莓·筒甜" 里 "筒甜" 位置为 3，前缀应为 "草莓·"
        self.assertEqual(ice_cream_prefix("草莓·筒甜"), "草莓·")
        self.assertEqual(detect_flavors_from_name("草莓·筒甜"), ["草莓"])

    # ------------------------------------------------------------------
    # 4. 噪声商品必须被忽略
    # ------------------------------------------------------------------
    def test_noise_products_ignored(self):
        self.assertEqual(extract_flavors(NOISE_PRODUCTS), [])

    def test_noise_with_each_flavor(self):
        """每种口味的冰淇淋商品 + 全部噪声，只能识别出那一种口味。"""
        for flavor in FLAVORS:
            with self.subTest(口味=flavor):
                self.assertEqual(
                    extract_flavors([f"{flavor}冰淇淋雪底拿铁"] + NOISE_PRODUCTS),
                    [flavor],
                )

    # ------------------------------------------------------------------
    # 5. 边界情况
    # ------------------------------------------------------------------
    def test_no_ice_cream_at_all(self):
        """当天没上冰淇淋。"""
        datasets = {AID_ZHUTU: NOISE_PRODUCTS, AID_HUANYUAN: ["拿铁", "美式"]}
        main_flavors, huan_flavors = query_both(opener=make_opener(datasets))
        self.assertEqual(main_flavors, [])
        self.assertEqual(huan_flavors, [])
        self.assertEqual(format_line(main_flavors, huan_flavors),
                         "主图：无冰淇淋，环院：无冰淇淋")

    def test_multiple_flavors_same_day(self):
        """当天同时卖两种口味时全部列出。"""
        datasets = {
            AID_ZHUTU: ["香草·筒甜", "草莓味甜筒"],
            AID_HUANYUAN: ["抹茶圣代"],
        }
        main_flavors, huan_flavors = query_both(opener=make_opener(datasets))
        self.assertEqual(main_flavors, ["香草", "草莓"])
        self.assertEqual(format_line(main_flavors, huan_flavors),
                         "主图：香草、草莓冰淇淋，环院：抹茶冰淇淋")

    def test_flavor_order_is_stable(self):
        """输出顺序固定按 FLAVORS，与商品出现顺序无关。"""
        self.assertEqual(
            extract_flavors(["茉莉乌龙·筒甜", "巧克力圣代", "抹茶味甜筒",
                             "草莓·筒甜", "香草圣代"]),
            ["香草", "草莓", "抹茶", "巧克力", "茉莉乌龙"],
        )

    def test_describe_and_format(self):
        self.assertEqual(describe(["香草"]), "香草冰淇淋")
        self.assertEqual(describe([]), "无冰淇淋")
        self.assertEqual(describe(None), "未知")
        self.assertEqual(format_line(None, ["草莓"]), "主图：未知，环院：草莓冰淇淋")

    def test_two_variables_are_independent(self):
        """两个变量互不影响：改其中一个不会影响另一个。"""
        datasets = {AID_ZHUTU: ["香草·筒甜"], AID_HUANYUAN: ["草莓·筒甜"]}
        main_flavors, huan_flavors = query_both(opener=make_opener(datasets))
        main_flavors.append("抹茶")
        self.assertEqual(huan_flavors, ["草莓"])

    # ------------------------------------------------------------------
    # 6. 接口地址与翻页
    # ------------------------------------------------------------------
    def test_build_url_matches_given_links(self):
        self.assertEqual(
            build_url(32677668, 1),
            "https://m.yk.fkw.com/api/product/list?aid=32677668&yid=1&storeId=0"
            "&page=1&limit=200&vers=20260902&__from=1",
        )
        self.assertEqual(
            build_url(32822471, 2),
            "https://m.yk.fkw.com/api/product/list?aid=32822471&yid=1&storeId=0"
            "&page=2&limit=200&vers=20260902&__from=1",
        )

    def test_pagination_multi_page(self):
        """超过 200 条时要翻页，第 2 页里的口味不能被漏掉。"""
        names = [f"普通商品{i}" for i in range(205)]
        names.append("香草·筒甜")           # 落在第 2 页
        calls = []
        got = fetch_all_product_names(AID_ZHUTU, opener=make_opener({AID_ZHUTU: names}, calls))
        self.assertEqual(len(got), 206)
        self.assertEqual(extract_flavors(got), ["香草"])
        self.assertEqual(calls, [(AID_ZHUTU, 1), (AID_ZHUTU, 2)])

    def test_pagination_stops_at_short_page(self):
        """不足一页时不再请求第 2 页。"""
        calls = []
        got = fetch_all_product_names(
            AID_ZHUTU,
            opener=make_opener({AID_ZHUTU: ["香草·筒甜", "美式"]}, calls),
        )
        self.assertEqual(got, ["香草·筒甜", "美式"])
        self.assertEqual(calls, [(AID_ZHUTU, 1)])

    def test_pagination_empty_store(self):
        calls = []
        got = fetch_all_product_names(AID_ZHUTU, opener=make_opener({}, calls))
        self.assertEqual(got, [])
        self.assertEqual(calls, [(AID_ZHUTU, 1)])

    # ------------------------------------------------------------------
    # 7. 异常处理
    # ------------------------------------------------------------------
    def test_api_error_code_raises(self):
        def opener(url, timeout=None):
            return {"code": 500, "msg": "boom", "dataList": []}

        with self.assertRaises(RuntimeError):
            fetch_all_product_names(AID_ZHUTU, opener=opener, retries=0)

    def test_network_failure_after_retries(self):
        attempts = []

        def opener(url, timeout=None):
            attempts.append(url)
            raise OSError("网络不可达")

        with self.assertRaises(RuntimeError):
            fetch_all_product_names(AID_ZHUTU, opener=opener, retries=1)
        self.assertEqual(len(attempts), 2, "失败后应重试一次")

    def test_one_site_down_does_not_break_the_other(self):
        """一个站点挂了，另一个照常返回，挂掉的那个是 None。"""

        def opener(url, timeout=None):
            if f"aid={AID_HUANYUAN}" in url:
                raise OSError("环院接口不可达")
            return {"code": 0, "dataList": [{"name": "香草·筒甜"}]}

        main_flavors, huan_flavors = query_both(opener=opener)
        self.assertEqual(main_flavors, ["香草"])
        self.assertIsNone(huan_flavors)
        self.assertEqual(format_line(main_flavors, huan_flavors),
                         "主图：香草冰淇淋，环院：未知")

    def test_main_returns_nonzero_when_site_down(self):
        def opener(url, timeout=None):
            if f"aid={AID_ZHUTU}" in url:
                raise OSError("主图接口不可达")
            return {"code": 0, "dataList": [{"name": "草莓·筒甜"}]}

        # 注入假 opener 后跑 main（把模块内的 http_get_json 换掉）
        original = icf.http_get_json
        icf.http_get_json = lambda url, timeout=icf.TIMEOUT: opener(url)
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = icf.main([])
        finally:
            icf.http_get_json = original
        self.assertEqual(code, 1)
        self.assertIsNone(icf.main_flavors)
        self.assertEqual(icf.huan_flavors, ["草莓"])

    def test_module_level_variables_exist(self):
        """查询结果保存在两个独立的模块级变量里。"""
        self.assertTrue(hasattr(icf, "main_flavors"))
        self.assertTrue(hasattr(icf, "huan_flavors"))

    # ------------------------------------------------------------------
    # 8. 文档示例
    # ------------------------------------------------------------------
    def test_doctests(self):
        results = doctest.testmod(icf, verbose=False)
        self.assertEqual(results.failed, 0, f"{results.failed} 个 doctest 失败")


class CombinationTableTest(unittest.TestCase):
    """5x5 = 25 元素搭配表本身的测试。"""

    # ------------------------------------------------------------------
    # 表结构
    # ------------------------------------------------------------------
    def test_table_shape(self):
        """至少 25 个元素，每个元素恰好两个变量，且都是合法口味。"""
        self.assertGreaterEqual(len(FLAVOR_COMBINATIONS), 25)
        self.assertEqual(len(FLAVOR_COMBINATIONS), COMBINATION_COUNT)
        self.assertEqual(count_combinations(), 25)

        for index, pair in enumerate(FLAVOR_COMBINATIONS):
            with self.subTest(序号=index):
                self.assertEqual(len(pair), 2, "每个元素必须含两个变量")
                self.assertIsInstance(pair[0], str)
                self.assertIsInstance(pair[1], str)
                self.assertIn(pair[0], FLAVORS)
                self.assertIn(pair[1], FLAVORS)

    def test_table_is_full_cartesian_product(self):
        """不重不漏：恰好等于 FLAVORS 的 5x5 笛卡尔积。"""
        expected = [[main, huan] for main in FLAVORS for huan in FLAVORS]
        self.assertEqual(FLAVOR_COMBINATIONS, expected)

        pairs = [tuple(pair) for pair in FLAVOR_COMBINATIONS]
        self.assertEqual(len(pairs), 25)
        self.assertEqual(len(set(pairs)), 25, "不能有重复元素")

    def test_explicit_examples_present(self):
        """逐个检查需求里点名举例的搭配都在表中。"""
        for pair in (["香草", "香草"], ["香草", "草莓"], ["香草", "抹茶"],
                     ["香草", "巧克力"], ["香草", "茉莉乌龙"],
                     ["草莓", "香草"], ["草莓", "草莓"],
                     ["茉莉乌龙", "茉莉乌龙"]):
            with self.subTest(搭配=pair):
                self.assertIn(pair, FLAVOR_COMBINATIONS)

    # ------------------------------------------------------------------
    # 逐元素输出
    # ------------------------------------------------------------------
    def test_each_element_renders_its_own_line(self):
        """25 个元素分别生成 25 行互不相同的输出。"""
        lines = render_all_combinations()
        self.assertEqual(len(lines), 25)
        self.assertEqual(len(set(lines)), 25, "25 行必须互不相同")

        for pair, line in zip(FLAVOR_COMBINATIONS, lines):
            with self.subTest(搭配=pair):
                self.assertEqual(line, f"主图：{pair[0]}冰淇淋，环院：{pair[1]}冰淇淋")

        # 抽样对照
        self.assertEqual(lines[0], "主图：香草冰淇淋，环院：香草冰淇淋")
        self.assertEqual(lines[1], "主图：香草冰淇淋，环院：草莓冰淇淋")
        self.assertEqual(lines[4], "主图：香草冰淇淋，环院：茉莉乌龙冰淇淋")
        self.assertEqual(lines[6], "主图：草莓冰淇淋，环院：草莓冰淇淋")
        self.assertEqual(lines[24], "主图：茉莉乌龙冰淇淋，环院：茉莉乌龙冰淇淋")

    def test_render_combination_uses_both_variables(self):
        self.assertEqual(render_combination(["香草", "香草"]),
                         "主图：香草冰淇淋，环院：香草冰淇淋")
        self.assertEqual(render_combination(["香草", "草莓"]),
                         "主图：香草冰淇淋，环院：草莓冰淇淋")
        self.assertEqual(render_combination(["茉莉乌龙", "巧克力"]),
                         "主图：茉莉乌龙冰淇淋，环院：巧克力冰淇淋")

    def test_render_all_accepts_custom_table(self):
        custom = [["抹茶", "巧克力"], ["巧克力", "抹茶"]]
        self.assertEqual(render_all_combinations(custom),
                         ["主图：抹茶冰淇淋，环院：巧克力冰淇淋",
                          "主图：巧克力冰淇淋，环院：抹茶冰淇淋"])

    # ------------------------------------------------------------------
    # 表自检与定位
    # ------------------------------------------------------------------
    def test_validate_combinations_accepts_default(self):
        validate_combinations()          # 默认表必须通过，不抛异常

    def test_validate_combinations_rejects_bad_tables(self):
        full = [[main, huan] for main in FLAVORS for huan in FLAVORS]

        with self.assertRaises(ValueError):      # 元素太少
            validate_combinations([["香草", "草莓"]])
        with self.assertRaises(ValueError):      # 缺一种组合
            validate_combinations(full[:-1])
        with self.assertRaises(ValueError):      # 元素不足两个变量
            validate_combinations(full + [["香草"]])
        with self.assertRaises(ValueError):      # 出现未知口味
            validate_combinations(full + [["榴莲", "香草"]])

    def test_find_combination(self):
        self.assertEqual(find_combination(["香草"], ["草莓"]), (1, ["香草", "草莓"]))
        self.assertEqual(find_combination(["茉莉乌龙"], ["茉莉乌龙"]),
                         (24, ["茉莉乌龙", "茉莉乌龙"]))
        self.assertIsNone(find_combination(["香草", "草莓"], ["抹茶"]))
        self.assertIsNone(find_combination([], ["抹茶"]))
        self.assertIsNone(find_combination(None, ["抹茶"]))

    def test_every_flavor_pair_locates_in_table(self):
        """任意一对口味都能在表中定位到唯一序号。"""
        for main_flavor in FLAVORS:
            for huan_flavor in FLAVORS:
                with self.subTest(主图=main_flavor, 环院=huan_flavor):
                    index, pair = find_combination([main_flavor], [huan_flavor])
                    self.assertEqual(pair, [main_flavor, huan_flavor])
                    self.assertEqual(FLAVOR_COMBINATIONS[index], pair)

    # ------------------------------------------------------------------
    # 命令行模式
    # ------------------------------------------------------------------
    def test_combinations_cli_prints_25_lines(self):
        """--combinations 逐个打印 25 行。"""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = icf.main(["--combinations"])
        self.assertEqual(code, 0)

        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 25)

        for index, (line, pair) in enumerate(zip(lines, FLAVOR_COMBINATIONS), 1):
            with self.subTest(序号=index):
                stripped = line.strip()
                self.assertTrue(stripped.startswith(f"{index}. "), line)
                self.assertIn(f"主图={pair[0]} 环院={pair[1]}", line)
                self.assertIn(f"主图：{pair[0]}冰淇淋，环院：{pair[1]}冰淇淋", line)

    def test_combinations_cli_json(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = icf.main(["--combinations", "--json"])
        self.assertEqual(code, 0)

        payload = json.loads(buffer.getvalue())
        self.assertEqual(len(payload), 25)
        self.assertEqual([item["序号"] for item in payload], list(range(1, 26)))
        self.assertEqual(payload[0]["主图"], "香草")
        self.assertEqual(payload[0]["环院"], "香草")
        self.assertEqual(payload[0]["line"], "主图：香草冰淇淋，环院：香草冰淇淋")
        self.assertEqual(payload[24]["line"], "主图：茉莉乌龙冰淇淋，环院：茉莉乌龙冰淇淋")


@unittest.skipUnless(os.environ.get("ICECREAM_LIVE_TEST") == "1",
                     "需要 ICECREAM_LIVE_TEST=1 才跑真实联网测试")
class LiveApiTest(unittest.TestCase):
    """真实接口回归测试（默认跳过）。"""

    def test_live_query(self):
        main_flavors, huan_flavors = query_both(verbose=True)
        print("主图：", main_flavors, " 环院：", huan_flavors)
        for flavors in (main_flavors, huan_flavors):
            self.assertIsNotNone(flavors)
            for flavor in flavors:
                self.assertIn(flavor, FLAVORS)
        print(format_line(main_flavors, huan_flavors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
