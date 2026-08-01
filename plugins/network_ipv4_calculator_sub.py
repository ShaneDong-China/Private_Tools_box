#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPv4 掩码计算器 — IPv4 Calculator
==================================
功能：IPv4 地址计算、子网划分、掩码速查
"""
import sys
import ipaddress
import logging

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QTabWidget,
    QGroupBox, QFrame, QSizePolicy, QSpinBox, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

from framework.logger import get_logger
from framework.plugin_interface import PluginBase

logger = get_logger("network_ipv4_calculator_sub")


# ═══════════════════════════════════════════════════════════
#  核心计算
# ═══════════════════════════════════════════════════════════

class IPv4CalculatorCore:
    """IPv4 核心计算引擎。"""

    @staticmethod
    def from_cidr(network: str) -> dict:
        """计算 CIDR 表示的网络信息。"""
        try:
            net = ipaddress.IPv4Network(network, strict=False)
        except ValueError as exc:
            return {"error": str(exc)}

        hosts = list(net.hosts())
        info = {
            "network_address": str(net.network_address),
            "broadcast_address": str(net.broadcast_address),
            "netmask": str(net.netmask),
            "wildcard": str(net.hostmask),
            "cidr": f"/{net.prefixlen}",
            "prefixlen": net.prefixlen,
            "num_addresses": net.num_addresses,
            "num_hosts": max(0, net.num_addresses - 2) if net.prefixlen < 31 else net.num_addresses,
            "first_host": str(hosts[0]) if hosts else "N/A",
            "last_host": str(hosts[-1]) if hosts else "N/A",
            "is_private": net.is_private,
            "is_global": net.is_global,
            "is_multicast": net.is_multicast,
            "is_loopback": net.is_loopback,
            "ip_class": IPv4CalculatorCore._get_ip_class(net.network_address),
            "binary_network": IPv4CalculatorCore._to_bin(str(net.network_address)),
            "binary_mask": IPv4CalculatorCore._to_bin(str(net.netmask)),
        }
        return info

    @staticmethod
    def subnetting(network: str, target_prefix: int) -> list[dict]:
        """子网划分。"""
        try:
            net = ipaddress.IPv4Network(network, strict=False)
        except ValueError as exc:
            return [{"error": str(exc)}]

        if target_prefix <= net.prefixlen:
            return [{"error": "目标前缀必须大于原前缀"}]

        subnets = list(net.subnets(new_prefix=target_prefix))
        results = []
        for i, sn in enumerate(subnets):
            hosts = list(sn.hosts())
            results.append({
                "index": i + 1,
                "network": str(sn),
                "netmask": str(sn.netmask),
                "first_host": str(hosts[0]) if hosts else "N/A",
                "last_host": str(hosts[-1]) if hosts else "N/A",
                "broadcast": str(sn.broadcast_address),
                "hosts": max(0, sn.num_addresses - 2) if sn.prefixlen < 31 else sn.num_addresses,
            })
        return results

    @staticmethod
    def _get_ip_class(addr) -> str:
        a = int(addr.exploded.split(".")[0])
        if a < 128: return "A"
        if a < 192: return "B"
        if a < 224: return "C"
        if a < 240: return "D"
        return "E"

    @staticmethod
    def _to_bin(ip_str: str) -> str:
        parts = ip_str.split(".")
        return ".".join(f"{int(p):08b}" for p in parts)


# ═══════════════════════════════════════════════════════════
#  样式表（Catppuccin Mocha 风格）
# ═══════════════════════════════════════════════════════════

APP_STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Microsoft YaHei', 'Consolas', 'Segoe UI', sans-serif;
}
QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    padding: 8px 24px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: 13px;
}
QTabBar::tab:selected {
    background-color: #313244;
    color: #cdd6f4;
    border-bottom: 2px solid #89b4fa;
}
QTabBar::tab:hover:!selected {
    background-color: #252536;
}
QGroupBox {
    font-size: 13px;
    font-weight: bold;
    color: #89b4fa;
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 15px;
    font-family: 'Consolas', 'Courier New', monospace;
}
QLineEdit:focus {
    border-color: #89b4fa;
}
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 6px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #74c7ec;
}
QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QTextEdit {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 8px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 14px;
}
QLabel {
    color: #cdd6f4;
    font-size: 13px;
}
QSpinBox {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 4px 8px; font-size: 15px; font-weight: bold;
    font-family: 'Consolas', monospace;
}
QSpinBox:focus { border-color: #89b4fa; }
QTableWidget {
    background-color: #181825; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px;
    font-size: 12px; gridline-color: #313244;
}
QHeaderView::section {
    background-color: #252536; color: #a6adc8;
    padding: 6px; font-weight: bold;
    border: none; border-bottom: 2px solid #45475a;
}
/* corner 由各表格单独设置样式，全局不处理避免冲突 */
QScrollBar:vertical {
    background-color: #181825; width: 10px; border: none;
}
QScrollBar::handle:vertical {
    background-color: #45475a; border-radius: 5px; min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""


# ═══════════════════════════════════════════════════════════
#  后台计算线程
# ═══════════════════════════════════════════════════════════

class CalcWorker(QThread):
    """后台执行 IPv4 计算，不阻塞 UI。"""
    finished = Signal(object)  # dict result

    def __init__(self, cidr: str, parent=None):
        super().__init__(parent)
        self._cidr = cidr

    def run(self):
        result = IPv4CalculatorCore.from_cidr(self._cidr)
        self.finished.emit(result)


class SubnetWorker(QThread):
    """后台执行子网划分（大网段可能产生数千上万个子网），不阻塞 UI。"""
    finished = Signal(object)  # list[dict] result

    def __init__(self, network: str, target_prefix: int, parent=None):
        super().__init__(parent)
        self._network = network
        self._target = target_prefix

    def run(self):
        results = IPv4CalculatorCore.subnetting(self._network, self._target)
        self.finished.emit(results)


# ═══════════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════════

class IPv4CalculatorApp(QMainWindow):
    """IPv4 计算器主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("IPv4 Calculator")
        self.setMinimumSize(800, 720)
        self.resize(880, 780)
        self.setStyleSheet(APP_STYLE)
        self._setup_ui()
        self._apply_fonts()

    def _apply_fonts(self):
        font = QFont("Microsoft YaHei", 10)
        self.setFont(font)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        layout.addWidget(self.tabs)

        self._build_tab_calculator()
        self._build_tab_subnet()
        self._build_tab_lookup()

        self.statusBar().setStyleSheet(
            "background-color: #181825; color: #6c7086;"
            "border-top: 1px solid #313244; padding: 2px;"
        )
        self.statusBar().showMessage("就绪 — 输入 IPv4 地址开始计算")

    # ── Tab 1: 地址计算 ───────────────────────────────────

    def _build_tab_calculator(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        layout.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        cl = QVBoxLayout(container)
        cl.setSpacing(10)
        cl.setContentsMargins(16, 12, 16, 12)

        # ── 输入区域（IP + 掩码同一行）──
        input_group = QGroupBox("IPv4 地址输入")
        ig = QHBoxLayout(input_group)
        ig.setSpacing(8)

        self.addr_input = QLineEdit()
        self.addr_input.setPlaceholderText("例: 192.168.1.1")
        self.addr_input.returnPressed.connect(self._do_calculate)
        ig.addWidget(self.addr_input, 1)

        lbl_slash = QLabel("  /")
        lbl_slash.setStyleSheet("color: #a6adc8; font-size: 16px; font-weight: bold; padding: 0 2px;")
        ig.addWidget(lbl_slash)

        self.mask_combo = QComboBox()
        self.mask_combo.setStyleSheet("""
            QComboBox {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 8px 12px; font-size: 14px;
                font-family: 'Consolas', monospace;
                min-width: 200px;
            }
            QComboBox:focus { border-color: #89b4fa; }
            QComboBox::drop-down { border: none; width: 28px; }
            QComboBox QAbstractItemView {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; outline: none;
                selection-background-color: #45475a;
                font-family: 'Consolas', monospace;
            }
        """)
        for i in range(1, 33):
            mask_str = str(ipaddress.IPv4Network(f"0.0.0.0/{i}", strict=False).netmask)
            self.mask_combo.addItem(f"/{i:>2d}  —  {mask_str}", i)
        self.mask_combo.setCurrentIndex(23)  # /24
        ig.addWidget(self.mask_combo)

        self.btn_calc = QPushButton("🔍  计算")
        self.btn_calc.setFixedWidth(110)
        self.btn_calc.setFixedHeight(40)
        self.btn_calc.clicked.connect(self._do_calculate)
        ig.addWidget(self.btn_calc)

        cl.addWidget(input_group)

        # ── 结果显示区域 ──
        core_group = QGroupBox("计算结果")
        cg = QVBoxLayout(core_group)
        cg.setSpacing(6)

        grid = QGridLayout()
        grid.setVerticalSpacing(6)
        grid.setHorizontalSpacing(12)
        grid.setColumnStretch(1, 1)

        def add_row(grid, row, label_text, attr_name, mono=True):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #6c7086; font-size: 13px;")
            grid.addWidget(lbl, row, 0, Qt.AlignTop)

            val = QLabel("—")
            val.setObjectName(attr_name)
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if mono:
                val.setStyleSheet(
                    "font-family: 'Consolas', 'Courier New', monospace;"
                    "color: #cdd6f4; font-size: 14px;"
                )
            else:
                val.setStyleSheet("color: #cdd6f4; font-size: 14px;")
            grid.addWidget(val, row, 1)

            copy_btn = QPushButton("📋")
            copy_btn.setFixedSize(26, 26)
            copy_btn.setToolTip("复制")
            copy_btn.setStyleSheet(
                "background-color: transparent; border: 1px solid #45475a;"
                "border-radius: 13px; font-size: 11px; padding: 0;"
            )
            copy_btn.clicked.connect(lambda checked, v=val: self._copy_text(v.text()))
            grid.addWidget(copy_btn, row, 2)
            return val

        self.res_network = add_row(grid, 0, "网络地址 (Network):", "res_network", mono=True)
        self.res_first = add_row(grid, 1, "首台主机 (First Host):", "res_first", mono=True)
        self.res_last = add_row(grid, 2, "末台主机 (Last Host):", "res_last", mono=True)
        self.res_broadcast = add_row(grid, 3, "广播地址 (Broadcast):", "res_broadcast", mono=True)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color: #313244;")
        grid.addWidget(sep1, 4, 0, 1, 3)

        self.res_netmask = add_row(grid, 5, "子网掩码 (Netmask):", "res_netmask", mono=True)
        self.res_wildcard = add_row(grid, 6, "通配符掩码 (Wildcard):", "res_wildcard", mono=True)
        self.res_hosts = add_row(grid, 7, "可用主机数:", "res_hosts", mono=False)
        self.res_hosts.setStyleSheet("color: #fab387; font-size: 14px; font-weight: bold;")

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #313244;")
        grid.addWidget(sep2, 8, 0, 1, 3)

        self.res_class = add_row(grid, 9, "IP 类别:", "res_class", mono=False)
        self.res_private = add_row(grid, 10, "私有地址:", "res_private", mono=False)
        self.res_binary_net = add_row(grid, 11, "二进制网络:", "res_binary_net", mono=True)
        self.res_binary_mask = add_row(grid, 12, "二进制掩码:", "res_binary_mask", mono=True)

        cg.addLayout(grid)
        cg.addStretch()
        cl.addWidget(core_group, 1)

        self.tabs.addTab(tab, "地址计算")

        # 默认输入
        self.addr_input.setText("192.168.1.1")
        self._do_calculate()

    def _do_calculate(self):
        text = self.addr_input.text().strip()
        if not text:
            return

        ip = text.split("/")[0]
        prefix = self.mask_combo.currentData()

        # 禁用按钮，显示加载状态
        self.btn_calc.setEnabled(False)
        self.btn_calc.setText("⏳ 计算中...")
        self.statusBar().showMessage("正在计算...")

        # 后台线程计算
        self._worker = CalcWorker(f"{ip}/{prefix}")
        self._worker.finished.connect(self._on_calc_done)
        self._worker.start()

    def _on_calc_done(self, result):
        self.btn_calc.setEnabled(True)
        self.btn_calc.setText("🔍  计算")

        if "error" in result:
            self.statusBar().showMessage(f"❌ {result['error']}")
            for attr in ["res_network", "res_broadcast", "res_first", "res_last",
                         "res_netmask", "res_wildcard", "res_hosts", "res_class",
                         "res_private", "res_binary_net", "res_binary_mask"]:
                getattr(self, attr).setText("—")
            return

        self.res_network.setText(f"{result['network_address']}{result['cidr']}")
        self.res_broadcast.setText(result["broadcast_address"])
        self.res_first.setText(result["first_host"])
        self.res_last.setText(result["last_host"])
        self.res_netmask.setText(f"{result['netmask']}  ({result['cidr']})")
        self.res_wildcard.setText(result["wildcard"])
        self.res_hosts.setText(f"{result['num_hosts']:,}")
        self.res_class.setText(result["ip_class"])
        self.res_private.setText("✅ 是" if result["is_private"] else "❌ 否")
        self.res_binary_net.setText(result["binary_network"])
        self.res_binary_mask.setText(result["binary_mask"])

        self.statusBar().showMessage(
            f"✅ {result['network_address']}{result['cidr']}  —  "
            f"{result['ip_class']}类  ·  {result['num_hosts']:,} 台主机"
        )

    def _copy_text(self, text):
        clip = QApplication.clipboard()
        clip.setText(text)
        self.statusBar().showMessage(f"📋 已复制: {text[:40]}{'…' if len(text) > 40 else ''}", 2000)

    # ── Tab 2: 子网划分 ───────────────────────────────────

    def _build_tab_subnet(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 12, 16, 12)

        form = QHBoxLayout()
        form.addWidget(QLabel("网络 (CIDR):"))

        self._snet_input = QLineEdit()
        self._snet_input.setPlaceholderText("例: 192.168.1.0/24")
        self._snet_input.setStyleSheet(
            "background-color: #313244; color: #cdd6f4;"
            "border: 1px solid #45475a; border-radius: 6px;"
            "padding: 8px 12px; font-size: 14px;"
            "font-family: 'Consolas', monospace;"
        )
        self._snet_input.returnPressed.connect(self._subnet_calc)
        form.addWidget(self._snet_input, 1)

        form.addWidget(QLabel("划分为 /"))
        self._snet_prefix = QComboBox()
        self._snet_prefix.setStyleSheet("""
            QComboBox {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 8px 12px; font-size: 14px;
                font-family: 'Consolas', monospace;
                min-width: 80px;
            }
            QComboBox:focus { border-color: #89b4fa; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; outline: none;
                selection-background-color: #45475a;
                font-family: 'Consolas', monospace;
            }
        """)
        for i in range(1, 33):
            self._snet_prefix.addItem(f"{i}", i)
        self._snet_prefix.setCurrentIndex(29)  # /30
        form.addWidget(self._snet_prefix)

        self._subnet_btn = QPushButton("✂️ 划分")
        self._subnet_btn.setStyleSheet(
            "QPushButton { background-color: #a6e3a1; color: #1e1e2e;"
            "border: none; border-radius: 6px;"
            "padding: 8px 24px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #94e2d5; }"
            "QPushButton:disabled { background-color: #45475a; color: #6c7086; }"
        )
        self._subnet_btn.clicked.connect(self._subnet_calc)
        form.addWidget(self._subnet_btn)

        form.addStretch()

        self._export_btn = QPushButton("📤 导出 Excel")
        self._export_btn.setStyleSheet(
            "QPushButton { background-color: #89b4fa; color: #1e1e2e;"
            "border: none; border-radius: 6px;"
            "padding: 8px 20px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #74c7ec; }"
        )
        self._export_btn.clicked.connect(self._subnet_export)
        form.addWidget(self._export_btn)

        layout.addLayout(form)

        self._subnet_table = QTableWidget()
        self._subnet_table.setAlternatingRowColors(False)
        self._subnet_table.setStyleSheet("""
            QTableWidget {
                background-color: #181825; color: #cdd6f4;
                border: 1px solid #313244; border-radius: 6px;
                font-size: 12px; gridline-color: #313244;
            }
            QTableWidget::corner { background-color: #252536; border: none; }
            QHeaderView { background-color: #252536; }
            QHeaderView::section {
                background-color: #252536; color: #a6adc8;
                padding: 6px; font-weight: bold; border: none;
                border-bottom: 2px solid #45475a;
            }
            QHeaderView::corner { background-color: #252536; border: none; }
        """)
        layout.addWidget(self._subnet_table, 1)

        self._snet_input.setText("192.168.1.0/24")
        self._subnet_calc()

        self.tabs.addTab(tab, "子网划分")

    def _subnet_calc(self):
        """点击划分 → 后台线程计算（大网段子网多，避免卡死界面）。"""
        # 防重复触发（按钮已禁用，回车键仍可能触发）
        if getattr(self, "_subnet_worker", None) and self._subnet_worker.isRunning():
            return

        network = self._snet_input.text().strip()
        target = self._snet_prefix.currentData()

        # 禁用按钮，显示加载状态
        self._subnet_btn.setEnabled(False)
        self._subnet_btn.setText("⏳ 划分中...")
        self.statusBar().showMessage("正在计算子网...")

        self._subnet_worker = SubnetWorker(network, target)
        self._subnet_worker.finished.connect(self._on_subnet_done)
        self._subnet_worker.start()

    def _on_subnet_done(self, results):
        """后台计算完成（主线程）：恢复按钮 + 填充结果表格。"""
        self._subnet_btn.setEnabled(True)
        self._subnet_btn.setText("✂️ 划分")

        if not results or "error" in results[0]:
            self._subnet_table.setRowCount(0)
            if results and "error" in results[0]:
                self.statusBar().showMessage(f"❌ {results[0]['error']}")
            return

        # 结果过多时截断显示，避免一次填充上万行卡顿
        MAX_ROWS = 10000
        shown = results if len(results) <= MAX_ROWS else results[:MAX_ROWS]

        cols = ["子网", "掩码", "网络位", "首台主机", "末台主机", "广播位", "可用主机数"]
        self._subnet_table.setColumnCount(len(cols))
        self._subnet_table.setHorizontalHeaderLabels(cols)
        self._subnet_table.setRowCount(len(shown))

        for row, r in enumerate(shown):
            # 网络位 = 子网去掉掩码部分（如 "192.168.0.0/24" → "192.168.0.0"）
            net_addr = r["network"].split("/")[0] if "/" in r["network"] else r["network"]
            self._subnet_table.setItem(row, 0, QTableWidgetItem(r["network"]))
            self._subnet_table.setItem(row, 1, QTableWidgetItem(r["netmask"]))
            self._subnet_table.setItem(row, 2, QTableWidgetItem(net_addr))
            self._subnet_table.setItem(row, 3, QTableWidgetItem(r["first_host"]))
            self._subnet_table.setItem(row, 4, QTableWidgetItem(r["last_host"]))
            self._subnet_table.setItem(row, 5, QTableWidgetItem(r["broadcast"]))
            self._subnet_table.setItem(row, 6, QTableWidgetItem(str(r["hosts"])))

        self._subnet_table.horizontalHeader().setStretchLastSection(True)
        self._subnet_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._subnet_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._subnet_table.setSelectionBehavior(QTableWidget.SelectRows)

        if len(results) > MAX_ROWS:
            self.statusBar().showMessage(
                f"✅ 共 {len(results):,} 个子网，仅显示前 {MAX_ROWS:,} 行")
        else:
            self.statusBar().showMessage(f"✅ 划分完成：{len(results):,} 个子网")

    def _subnet_export(self):
        """将子网划分结果导出为 Excel 文件。"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出子网划分结果", "subnet_export.xlsx",
            "Excel 文件 (*.xlsx)"
        )
        if not path:
            return

        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "子网划分"

        headers = ["子网", "掩码", "网络位", "首台主机", "末台主机", "广播位", "可用主机数"]
        ws.append(headers)

        for row in range(self._subnet_table.rowCount()):
            row_data = []
            for col in range(self._subnet_table.columnCount()):
                item = self._subnet_table.item(row, col)
                row_data.append(item.text() if item else "")
            ws.append(row_data)

        wb.save(path)
        self.statusBar().showMessage(f"✅ 已导出: {path}", 3000)

    # ── Tab 3: IP 地址分类速查 ────────────────────────────

    def _build_tab_lookup(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        layout.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(16, 8, 16, 8)
        cl.setSpacing(10)

        TABLE_STYLE = """
            QTableWidget {
                background-color: #181825; color: #cdd6f4;
                border: 1px solid #313244; border-radius: 6px;
                font-size: 12px; gridline-color: #313244;
            }
            QTableWidget::corner { background-color: #252536; border: none; }
            QHeaderView { background-color: #252536; }
            QHeaderView::section {
                background-color: #252536; color: #a6adc8;
                padding: 5px; font-weight: bold; border: none;
                border-bottom: 2px solid #45475a;
            }
            QHeaderView::corner { background-color: #252536; border: none; }
        """

        def make_table(headers, rows, col_stretch=None):
            t = QTableWidget()
            t.setStyleSheet(TABLE_STYLE)
            t.setColumnCount(len(headers))
            t.setHorizontalHeaderLabels(headers)
            t.setRowCount(len(rows))
            for r, row_data in enumerate(rows):
                for c, val in enumerate(row_data):
                    item = QTableWidgetItem(str(val))
                    if c == 0:
                        item.setFont(QFont("Consolas", 11, QFont.Bold))
                    t.setItem(r, c, item)
            t.setAlternatingRowColors(False)
            t.horizontalHeader().setStretchLastSection(True)
            for c in range(len(headers)):
                t.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
            if col_stretch is not None:
                for c in col_stretch:
                    t.horizontalHeader().setSectionResizeMode(c, QHeaderView.Stretch)
            t.setEditTriggers(QTableWidget.NoEditTriggers)
            t.setSelectionMode(QTableWidget.NoSelection)
            t.verticalHeader().setVisible(False)
            return t

        # ── 第一节：IPv4 基础分类 ──────────────────────────
        g1 = QGroupBox("一、IPv4 基础分类（按首位字节）")
        g1.setStyleSheet("QGroupBox { color: #89b4fa; font-size: 13px; font-weight: bold; border: none; margin-top: 8px; } QGroupBox::title { padding: 0 4px; }")
        v1 = QVBoxLayout(g1)
        v1.setContentsMargins(0, 4, 0, 0)
        t1 = make_table(
            ["类别", "起始范围", "结束范围", "默认掩码", "用途"],
            [
                ("A 类", "1.0.0.0",     "126.255.255.255",  "/8  (255.0.0.0)",     "超大型网络"),
                ("B 类", "128.0.0.0",   "191.255.255.255",  "/16 (255.255.0.0)",    "中型网络"),
                ("C 类", "192.0.0.0",   "223.255.255.255",  "/24 (255.255.255.0)",  "小型网络"),
                ("D 类", "224.0.0.0",   "239.255.255.255",  "—",                    "组播"),
                ("E 类", "240.0.0.0",   "255.255.255.255",  "—",                    "实验 / 保留"),
            ],
            col_stretch=[4],
        )
        v1.addWidget(t1)
        cl.addWidget(g1)

        # ── 特殊保留 ──
        g1b = QGroupBox("特殊保留地址")
        g1b.setStyleSheet("QGroupBox { color: #fab387; font-size: 12px; font-weight: bold; border: none; margin-top: 4px; } QGroupBox::title { padding: 0 4px; }")
        v1b = QVBoxLayout(g1b)
        v1b.setContentsMargins(0, 4, 0, 0)
        t1b = make_table(
            ["地址范围", "CIDR", "说明"],
            [
                ("127.0.0.0 — 127.255.255.255", "127.0.0.0/8",   "环回地址（localhost），本机通信"),
                ("0.0.0.0 — 0.255.255.255",     "0.0.0.0/8",     "未指定地址，代表任意源或默认路由"),
            ],
            col_stretch=[2],
        )
        v1b.addWidget(t1b)
        cl.addWidget(g1b)

        # ── 第二节：私网地址 ──────────────────────────────
        g2 = QGroupBox("二、私网地址（RFC 1918 — 内网专用，不可公网路由）")
        g2.setStyleSheet("QGroupBox { color: #a6e3a1; font-size: 13px; font-weight: bold; border: none; margin-top: 8px; } QGroupBox::title { padding: 0 4px; }")
        v2 = QVBoxLayout(g2)
        v2.setContentsMargins(0, 4, 0, 0)
        t2 = make_table(
            ["类别", "CIDR", "范围", "可用 IP 数", "说明"],
            [
                ("A 类私网", "10.0.0.0/8",      "10.0.0.0 — 10.255.255.255",     "约 1,677 万", "大型内网"),
                ("B 类私网", "172.16.0.0/12",   "172.16.0.0 — 172.31.255.255",   "约 104 万",   "中型内网"),
                ("C 类私网", "192.168.0.0/16",  "192.168.0.0 — 192.168.255.255", "约 6.5 万",   "小型内网 / 家庭"),
            ],
            col_stretch=[4],
        )
        note2 = QLabel("判定规则：任何目的 IP 命中上述三段之一即为私网流量，NAT 设备须将其源地址转换为公网 IP 后才可访问互联网。")
        note2.setStyleSheet("color: #6c7086; font-size: 11px; padding: 2px 4px;")
        note2.setWordWrap(True)
        v2.addWidget(t2)
        v2.addWidget(note2)
        cl.addWidget(g2)

        # ── 第三节：组播地址 ──────────────────────────────
        g3 = QGroupBox("三、组播地址（D 类 — 一对多通信）")
        g3.setStyleSheet("QGroupBox { color: #89dceb; font-size: 13px; font-weight: bold; border: none; margin-top: 8px; } QGroupBox::title { padding: 0 4px; }")
        v3 = QVBoxLayout(g3)
        v3.setContentsMargins(0, 4, 0, 0)
        t3 = make_table(
            ["范围", "CIDR", "说明"],
            [
                ("224.0.0.0 — 224.0.0.255",  "224.0.0.0/24", "本地链路组播，路由器不转发（TTL=1）"),
                ("224.0.1.0 — 238.255.255.255", "—",          "全球 / 公开组播（需申请）"),
                ("239.0.0.0 — 239.255.255.255", "239.0.0.0/8", "私有组播，内部网络自由使用（类似私网 IP）"),
            ],
            col_stretch=[2],
        )
        note3 = QLabel("用途场景：视频直播分发、路由协议（OSPF / RIP）、设备自动发现（mDNS / UPnP）")
        note3.setStyleSheet("color: #6c7086; font-size: 11px; padding: 2px 4px;")
        note3.setWordWrap(True)
        v3.addWidget(t3)
        v3.addWidget(note3)
        cl.addWidget(g3)

        cl.addStretch()
        self.tabs.addTab(tab, "IP 分类速查")


# ═══════════════════════════════════════════════════════════
#  PluginBase 包装
# ═══════════════════════════════════════════════════════════

class IPv4Plugin(PluginBase):
    @property
    def plugin_name(self) -> str: return "IPv4掩码计算器"
    @property
    def plugin_name_en(self) -> str: return "IPv4 Calculator"
    @property
    def plugin_version(self) -> str: return "1.0.0"
    @property
    def plugin_icon(self) -> str: return "🌐"
    @property
    def plugin_description(self) -> str: return "IPv4 地址计算、子网划分、掩码转换、CIDR 速查"
    @property
    def plugin_description_en(self) -> str: return "IPv4 address calc, subnetting, mask conversion, CIDR lookup"
    @property
    def plugin_tags(self) -> list: return ["network", "ipv4"]

    def create_widget(self, parent=None):
        return IPv4CalculatorApp()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = IPv4CalculatorApp()
    w.show()
    sys.exit(app.exec())
