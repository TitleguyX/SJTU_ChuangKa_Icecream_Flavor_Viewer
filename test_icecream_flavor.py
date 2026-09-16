#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""icecream_flavor 的离线单元测试（不访问网络）。"""

import builtins
import contextlib
import io
import os
import unittest

import icecream_flavor as icf


def p(name):
    return {"name": name}


class TestDetectFlavors(unittest.TestCase):
    def test_main_library_vanilla(self):
        products = [p(n) for n in (
            "香草冰淇淋雪底拿铁", "香草冰淇淋雪底美式", "香草·筒甜",
            "香草黑武士·筒甜", "香草雪底茉莉绿茶", "香草阿芙佳朵",
            "香草旗杆圣代", "香草圣代", "香草吐冰",
            "拿铁咖啡", "美式", "烤吐司", "厚切培根芝士卷",
        )]
        info = icf.detect_flavors(products)
        self.assertEqual(info["flavors"], ["香草"])
        self.assertEqual(len(info["items"]), 9)

    def test_env_school_strawberry(self):
        products = [p(n) for n in (
            "草莓雪底红茶", "草莓冰淇淋雪底拿铁", "草莓冰淇淋雪底美式",
            "草莓雪底茉莉绿茶", "草莓黑武士·筒甜", "草莓·筒甜",
            "草莓味旗杆圣代", "黑武士·草莓味甜筒", "草莓味圣代",
            "草莓味甜筒", "草莓味阿芙佳朵", "草莓吐冰",
            "原味伯爵瑞士卷-单个(口味随机)",
        )]
        info = icf.detect_flavors(products)
        self.assertEqual(info["flavors"], ["草莓"])
        self.assertEqual(len(info["items"]), 12)

    def test_no_ice_cream(self):
        info = icf.detect_flavors([p("美式"), p("拿铁咖啡"), p("原味酸奶碗")])
        self.assertEqual(info["flavors"], [])
        self.assertEqual(info["items"], [])

    def test_non_icecream_products_are_ignored(self):
        # 「原味伯爵瑞士卷」不含冰淇淋关键词，不应计入
        info = icf.detect_flavors([p("原味伯爵瑞士卷-单个(口味随机)")])
        self.assertEqual(info["flavors"], [])

    def test_flavor_is_taken_directly_without_voting(self):
        # 同一天口味一致：即使某口味只出现在一个商品上也应被采用
        products = [p(n) for n in ("抹茶圣代", "抹茶甜筒", "香草圣代")]
        info = icf.detect_flavors(products)
        self.assertEqual(info["flavors"], ["抹茶", "香草"])

    def test_flavors_are_deduplicated_in_order(self):
        products = [p("香草圣代"), p("香草甜筒"), p("草莓圣代"), p("香草阿芙佳朵")]
        info = icf.detect_flavors(products)
        self.assertEqual(info["flavors"], ["香草", "草莓"])

    def test_blank_and_missing_names(self):
        info = icf.detect_flavors([{"name": ""}, {}, {"name": None}, p("香草圣代")])
        self.assertEqual(info["flavors"], ["香草"])


class TestFlavorWhitelist(unittest.TestCase):
    """FLAVORS 只认指定的五种口味。"""

    def test_exact_flavor_list(self):
        self.assertEqual(
            list(icf.FLAVORS),
            ["香草", "草莓", "巧克力", "抹茶", "茉莉乌龙"],
        )

    def test_each_allowed_flavor_is_detected(self):
        for flavor in ("香草", "草莓", "巧克力", "抹茶", "茉莉乌龙"):
            with self.subTest(flavor=flavor):
                info = icf.detect_flavors([p(flavor + "圣代")])
                self.assertEqual(info["flavors"], [flavor])

    def test_removed_flavors_are_ignored(self):
        for flavor in ("芒果", "蓝莓", "焦糖", "榴莲", "奥利奥", "芝士", "原味"):
            with self.subTest(flavor=flavor):
                info = icf.detect_flavors([p(flavor + "圣代")])
                self.assertEqual(info["flavors"], [], f"{flavor} 不该再被识别")

    def test_moli_oolong_needs_full_match(self):
        # 只写「茉莉」不足，必须是完整的「茉莉乌龙」
        info = icf.detect_flavors([p("茉莉乌龙甜筒")])
        self.assertEqual(info["flavors"], ["茉莉乌龙"])

    def test_moli_green_tea_is_not_a_flavor(self):
        info = icf.detect_flavors([p("茉莉绿茶圣代")])
        self.assertEqual(info["flavors"], [])

    def test_real_shop_menu_names(self):
        """两家店真实在售的冰淇淋商品名仍要正确识别。"""
        main = [p(n) for n in (
            "香草冰淇淋雪底拿铁", "香草冰淇淋雪底美式", "香草·筒甜",
            "香草黑武士·筒甜", "香草雪底茉莉绿茶", "香草阿芙佳朵",
            "香草旗杆圣代", "香草圣代", "香草吐冰",
        )]
        huan = [p(n) for n in (
            "草莓雪底红茶", "草莓冰淇淋雪底拿铁", "草莓冰淇淋雪底美式",
            "草莓雪底茉莉绿茶", "草莓黑武士·筒甜", "草莓·筒甜",
            "草莓味旗杆圣代", "黑武士·草莓味甜筒", "草莓味圣代",
            "草莓味甜筒", "草莓味阿芙佳朵", "草莓吐冰",
        )]
        self.assertEqual(icf.detect_flavors(main)["flavors"], ["香草"])
        self.assertEqual(icf.detect_flavors(huan)["flavors"], ["草莓"])


class TestFormatResult(unittest.TestCase):
    def test_one_shop_per_line_without_comma(self):
        results = {
            "主图": {"flavors": ["香草"]},
            "环院": {"flavors": ["草莓"]},
        }
        self.assertEqual(
            icf.format_result(results, icf.SHOPS),
            "主图：香草冰淇淋\n环院：草莓冰淇淋",
        )
        self.assertNotIn("，", icf.format_result(results, icf.SHOPS))

    def test_multiple_flavors_joined(self):
        results = {"主图": {"flavors": ["香草", "草莓"]}, "环院": {"flavors": ["抹茶"]}}
        self.assertEqual(
            icf.format_result(results, icf.SHOPS),
            "主图：香草冰淇淋、草莓冰淇淋\n环院：抹茶冰淇淋",
        )

    def test_missing_flavor_placeholder(self):
        results = {"主图": {"flavors": []}, "环院": {"flavors": ["草莓"]}}
        self.assertEqual(
            icf.format_result(results, icf.SHOPS),
            "主图：未找到冰淇淋商品\n环院：草莓冰淇淋",
        )

    def test_fetch_error_is_shown(self):
        results = {
            "主图": {"flavors": [], "error": "连接超时"},
            "环院": {"flavors": ["草莓"], "error": None},
        }
        self.assertEqual(
            icf.format_result(results, icf.SHOPS),
            "主图：获取失败（连接超时）\n环院：草莓冰淇淋",
        )


class TestVisibleOutput(unittest.TestCase):
    """双击运行时必须能看到输出：窗口结束前要暂停。"""

    def test_pause_can_be_disabled(self):
        # 不能阻塞：disable=True 时必须立即返回
        icf._maybe_pause(disable=True)

    def test_pause_skipped_by_env_var(self):
        os.environ[icf.PAUSE_ENV] = "1"
        try:
            icf._maybe_pause()
        finally:
            del os.environ[icf.PAUSE_ENV]

    def test_double_click_detection_returns_bool(self):
        self.assertIsInstance(icf._launched_by_double_click(), bool)

    def test_double_click_detection_false_in_test_run(self):
        # 测试由 python.exe / py.exe 启动，不是资源管理器双击
        self.assertFalse(icf._launched_by_double_click())

    def test_console_setup_is_safe(self):
        icf._setup_console()  # 不应抛异常

    def test_parent_process_name_is_string(self):
        self.assertIsInstance(icf._parent_process_name(), str)

    def test_ancestors_is_list(self):
        self.assertIsInstance(icf._process_ancestors(), list)

    # --- 祖先链判定 ---

    def _with_ancestors(self, names, func):
        orig = icf._process_ancestors
        icf._process_ancestors = lambda limit=5: list(names)
        try:
            return func()
        finally:
            icf._process_ancestors = orig

    def test_double_click_via_python_directly(self):
        # .py 直接关联 python.exe：explorer.exe -> python.exe
        self.assertTrue(
            self._with_ancestors(["python.exe", "explorer.exe"],
                                 icf._launched_by_double_click)
        )

    def test_double_click_via_py_launcher(self):
        # .py 关联 py 启动器：explorer.exe -> py.exe -> python.exe
        self.assertTrue(
            self._with_ancestors(["py.exe", "explorer.exe"],
                                 icf._launched_by_double_click)
        )

    def test_terminal_run_is_not_double_click(self):
        # 从终端运行：python.exe -> powershell.exe -> ...（更上面才是 explorer）
        self.assertFalse(
            self._with_ancestors(["python.exe", "powershell.exe", "explorer.exe"],
                                 icf._launched_by_double_click)
        )

    def test_cmd_run_is_not_double_click(self):
        self.assertFalse(
            self._with_ancestors(["python.exe", "cmd.exe"], icf._launched_by_double_click)
        )

    def test_unknown_ancestors_default_to_no_pause(self):
        self.assertFalse(self._with_ancestors([], icf._launched_by_double_click))
        self.assertFalse(
            self._with_ancestors(["python.exe"], icf._launched_by_double_click)
        )

    # --- 暂停行为 ---

    def test_pause_waits_when_launched_from_explorer(self):
        """模拟双击：必须等待用户回车，否则窗口会一闪而过。"""
        prompts = []
        orig_anc, orig_input = icf._process_ancestors, builtins.input
        icf._process_ancestors = lambda limit=5: ["py.exe", "explorer.exe"]
        builtins.input = lambda prompt="": prompts.append(prompt)
        try:
            icf._maybe_pause()
        finally:
            icf._process_ancestors, builtins.input = orig_anc, orig_input
        self.assertEqual(len(prompts), 1, "双击启动时没有暂停，窗口会一闪而过")

    def test_force_pause_flag(self):
        """--pause 强制暂停（供 .bat 调用）。"""
        prompts = []
        orig_input = builtins.input
        builtins.input = lambda prompt="": prompts.append(prompt)
        try:
            icf._maybe_pause(force=True)
        finally:
            builtins.input = orig_input
        self.assertEqual(len(prompts), 1)

    def test_no_pause_flag_beats_force(self):
        prompts = []
        orig_input = builtins.input
        builtins.input = lambda prompt="": prompts.append(prompt)
        try:
            icf._maybe_pause(force=True, disable=True)
        finally:
            builtins.input = orig_input
        self.assertEqual(prompts, [])

    def test_pause_survives_eof(self):
        """用户直接关掉输入时不应崩溃。"""
        orig_anc, orig_input = icf._process_ancestors, builtins.input
        icf._process_ancestors = lambda limit=5: ["explorer.exe"]

        def boom(prompt=""):
            raise EOFError

        builtins.input = boom
        try:
            icf._maybe_pause()
        finally:
            icf._process_ancestors, builtins.input = orig_anc, orig_input

    # --- 端到端（mock 掉网络） ---

    def test_main_runs_offline_and_prints_expected_line(self):
        """参数解析、输出格式、退出码都要正确。"""
        fixtures = {"主图": [p("香草圣代")], "环院": [p("草莓甜筒"), p("草莓阿芙佳朵")]}
        orig = icf.fetch_products
        icf.fetch_products = lambda shop, **kw: fixtures[shop["key"]]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = icf.main(["--no-pause"])
        finally:
            icf.fetch_products = orig
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue().strip(), "主图：香草冰淇淋\n环院：草莓冰淇淋")

    def test_main_reports_error_instead_of_crashing(self):
        """接口失败时要打印可读信息并以非 0 退出，而不是抛异常关窗。"""

        def boom(shop, **kw):
            raise icf.FetchError("模拟网络故障")

        orig = icf.fetch_products
        icf.fetch_products = boom
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = icf.main(["--no-pause"])
        finally:
            icf.fetch_products = orig
        self.assertEqual(code, 1)
        self.assertIn("获取失败（模拟网络故障）", buf.getvalue())


class TestShopConfig(unittest.TestCase):
    def test_two_shops_configured(self):
        keys = [s["key"] for s in icf.SHOPS]
        self.assertEqual(keys, ["主图", "环院"])
        for shop in icf.SHOPS:
            self.assertTrue(shop["appid"].startswith("wx"))
            self.assertIsInstance(shop["aid"], int)
            self.assertGreater(shop["aid"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
