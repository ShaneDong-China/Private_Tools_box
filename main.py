# -*- coding: utf-8 -*-
"""
工具箱主程序 (PySide6)
布局：左侧分类 | 右侧九宫格/插件界面
插件：独立 .pyd，按需加载，启动时检测 GitHub 更新
"""
import sys
import os
import json
import logging
import threading
import urllib.request
import urllib.error
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QFrame,
    QSizePolicy, QScrollArea, QMessageBox, QSplitter, QProgressBar,
    QToolTip, QListWidget, QListWidgetItem, QDialog,
)
from PySide6.QtCore import Qt, QSize, Signal, QByteArray
from PySide6.QtGui import (QFont, QIcon, QAction, QEnterEvent, QColor,
                           QPalette, QPixmap, QPainter)
from PySide6.QtSvg import QSvgRenderer

# ── 框架组件 ────────────────────────────────────────────────
from framework.plugin_manager import PluginManager
from framework.plugin_updater import PluginUpdater
from framework.plugin_interface import PluginBase
from framework.logger import configure_logging, get_logger

# ── 常量 ─────────────────────────────────────────────────────
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
    else os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(APP_DIR, "config")
PLUGINS_DIR = os.path.join(APP_DIR, "plugins")
PLUGINS_JSON = os.path.join(CONFIG_DIR, "plugins.json")
CATEGORIES_JSON = os.path.join(CONFIG_DIR, "categories.json")
VERSION_URL = (
    "https://raw.githubusercontent.com/LegendaryScriptGenew/"
    "tools_box/master/config/plugins.json"
)
CATEGORIES_URL = (
    "https://raw.githubusercontent.com/LegendaryScriptGenew/"
    "tools_box/master/config/categories.json"
)

# ── 日志 ─────────────────────────────────────────────────────
configure_logging(os.path.join(APP_DIR, "logs"))
logger = get_logger("toolbox")

# 控制台输出（开发时用）
_log_console = logging.StreamHandler(sys.stdout)
_log_console.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
_log_console.setLevel(logging.INFO)
logging.getLogger().addHandler(_log_console)


# ═══════════════════════════════════════════════════════════
#  数据加载
# ═══════════════════════════════════════════════════════════

def load_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as exc:
        logger.warning("Load %s failed: %s", path, exc)
        return default


def _fetch_remote_json(url: str, timeout: int = 5) -> Optional[dict]:
    """从 GitHub 拉取 JSON，失败返回 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Toolbox-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("Fetch remote JSON failed (%s): %s", url, exc)
        return None


def load_categories() -> list[dict]:
    """加载分类定义。"""
    data = load_json(CATEGORIES_JSON)
    if data and "categories" in data:
        return data["categories"]
    # 硬编码 fallback
    return [
        {"id": "linux",  "name": "Linux系统相关类", "icon": "🐧",
         "plugins": ["linux_tools_sub", "linux_yum_manager_sub", "linux_docker_sub"]},
        {"id": "network","name": "网络相关类",       "icon": "🌐",
         "plugins": ["network_pingscanner_sub", "network_ipv6_calculator_sub", "network_ipv4_calculator_sub", "other_passwd_generator_sub"]},
        {"id": "telecom","name": "通信网元相关类",    "icon": "📡",
         "plugins": ["ims_tools_sub", "other_pdf_tools_sub"]},
    ]


def load_plugins() -> dict[str, dict]:
    """加载插件注册表，返回 name -> info 字典。"""
    data = load_json(PLUGINS_JSON, {})
    raw = data.get("plugins", data if isinstance(data, list) else [])
    return {p["name"]: p for p in raw if isinstance(p, dict) and p.get("name")}


# ═══════════════════════════════════════════════════════════
#  SF Symbols 风格图标（内嵌 SVG 渲染，无外部资源依赖）
# ═══════════════════════════════════════════════════════════

_sf_icon_cache: dict[str, QIcon] = {}


def _sf_icon(svg: str, size: int = 24) -> QIcon:
    """把 SVG 字符串渲染为 QIcon（懒渲染 + 缓存，需在 QApplication 创建后调用）。

    Disabled 模式也注册同一张图：否则按钮禁用（如「已最新」）时，
    Qt 会把彩色图标自动灰度化。
    """
    icon = _sf_icon_cache.get(svg)
    if icon is None:
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon = QIcon(pixmap)
        icon.addPixmap(pixmap, QIcon.Mode.Disabled, QIcon.State.Off)
        _sf_icon_cache[svg] = icon
    return icon


def _sf_icon_svg(paths: str, bg: str, fg: str = "#ffffff") -> str:
    """SF Symbols 风格：圆角方形底 + 白色线条图标。"""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'width="24" height="24">'
        f'<rect x="1" y="1" width="22" height="22" rx="7" fill="{bg}"/>'
        f'<g stroke="{fg}" stroke-width="2" fill="none" '
        f'stroke-linecap="round" stroke-linejoin="round">{paths}</g>'
        '</svg>'
    )


# 更新按钮 4 态图标（只存 SVG 字符串，渲染在首次使用时惰性完成）
_SF_UPDATE_SVG = _sf_icon_svg(
    '<path d="M12 19 V6 M6.5 11.5 L12 6 L17.5 11.5"/>', "#f39c12")
_SF_LATEST_SVG = _sf_icon_svg(
    '<path d="M5.5 13 L10 17.5 L18.5 7"/>', "#27ae60")
_SF_UNKNOWN_SVG = _sf_icon_svg(
    '<circle cx="10.5" cy="10.5" r="5.5"/>'
    '<line x1="14.8" y1="14.8" x2="19.5" y2="19.5"/>', "#d5dbe0")
_SF_INSTALL_SVG = _sf_icon_svg(
    '<path d="M12 5 V18 M6.5 12.5 L12 18 L17.5 12.5"/>', "#f39c12")


# ═══════════════════════════════════════════════════════════
#  工具卡片
# ═══════════════════════════════════════════════════════════

class ToolCard(QFrame):
    """九宫格中的单个功能模块卡片。"""

    launch_clicked = Signal(dict)  # 发射 plugin_info
    update_clicked = Signal(dict)  # 点击更新/安装

    # 更新按钮状态
    STATE_HAS_UPDATE = "has_update"          # 橙「⬆ 更新」可点
    STATE_UP_TO_DATE = "up_to_date"          # 灰「已最新」禁用
    STATE_UNKNOWN = "unknown"                # 灰「更新」可点（重查）
    STATE_NOT_INSTALLED = "not_installed"    # 橙「⬇ 安装」可点

    CARD_STYLE = """
        QFrame#toolCard {
            background-color: #ffffff;
            border: 1px solid #e8eaed;
            border-radius: 10px;
        }
        QFrame#toolCard:hover {
            border: 1px solid #4361ee;
            background-color: #f8f9ff;
        }
    """

    def __init__(self, plugin_info: dict, parent=None):
        super().__init__(parent)
        self._info = plugin_info
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("toolCard")
        self.setStyleSheet(self.CARD_STYLE)
        self.setMinimumSize(140, 80)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(6)

        # ── 名称行：名称居中 + 更新小按钮（右上角） ──
        top_row = QHBoxLayout()
        top_row.setSpacing(0)
        top_row.addStretch(1)
        name = QLabel(self._info.get("display_name", "?"))
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        name.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        name.setStyleSheet("color: #2d3436;")
        top_row.addWidget(name, 1)
        top_row.addStretch(1)

        # 更新按钮（右上角，SF Symbols 风格图标 + 颜色表达状态）
        self._update_btn = QPushButton()
        self._update_btn.setCursor(Qt.PointingHandCursor)
        self._update_btn.setFixedSize(26, 26)
        self._update_btn.setIconSize(QSize(22, 22))
        self._update_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; }
            QPushButton:hover { background: rgba(0,0,0,0.06);
                                border-radius: 6px; }
        """)
        self._update_btn.clicked.connect(
            lambda: self.update_clicked.emit(self._info))
        top_row.addWidget(self._update_btn)

        layout.addLayout(top_row)

        # ── 版本号（居中） ──
        ver_text = f"v{self._info.get('version', '0.0.0')}"
        ver_label = QLabel(ver_text)
        ver_label.setAlignment(Qt.AlignCenter)
        ver_label.setFont(QFont("Consolas", 8))
        ver_label.setStyleSheet("color: #b2bec3; margin-bottom: 2px;")
        layout.addWidget(ver_label)

        # ── 简短描述 ──
        desc_text = self._info.get("description", "")
        if len(desc_text) > 30:
            desc_text = desc_text[:28] + "..."
        desc = QLabel(desc_text)
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setFont(QFont("Microsoft YaHei", 9))
        desc.setStyleSheet("color: #636e72;")
        layout.addWidget(desc)

        layout.addStretch()

        # ── 启动按钮（纯本地加载，全宽主按钮） ──
        self._btn = QPushButton("启动")
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setFixedHeight(32)
        self._btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn.setStyleSheet("""
            QPushButton {
                background: #4361ee; color: white;
                border: none; border-radius: 6px;
                font-size: 12px; font-weight: bold;
                padding: 0 8px;
            }
            QPushButton:hover { background: #3a56d4; }
            QPushButton:pressed { background: #3048c0; }
        """)
        self._btn.clicked.connect(self._on_btn_clicked)
        layout.addWidget(self._btn)

        self.set_update_state(self.STATE_UNKNOWN)

    def set_update_state(self, state: str):
        """设置更新按钮状态（has_update / up_to_date / unknown / not_installed）。

        右上角 SF Symbols 风格图标：线条图标 + 底色表达状态，文字在 tooltip。
        """
        if state == self.STATE_HAS_UPDATE:
            self._update_btn.setIcon(_sf_icon(_SF_UPDATE_SVG))
            self._update_btn.setEnabled(True)
            self._update_btn.setToolTip("有新版本，点击更新")
        elif state == self.STATE_UP_TO_DATE:
            self._update_btn.setIcon(_sf_icon(_SF_LATEST_SVG))
            self._update_btn.setEnabled(False)
            self._update_btn.setToolTip("已是最新版本")
        elif state == self.STATE_NOT_INSTALLED:
            self._update_btn.setIcon(_sf_icon(_SF_INSTALL_SVG))
            self._update_btn.setEnabled(True)
            self._update_btn.setToolTip("未安装，点击下载安装")
        else:  # unknown：可点，点击重新检查
            self._update_btn.setIcon(_sf_icon(_SF_UNKNOWN_SVG))
            self._update_btn.setEnabled(True)
            self._update_btn.setToolTip("未检测或网络不可达，点击重新检查")

    def _on_btn_clicked(self):
        """点击启动：直接发射信号（纯本地加载，无需进度动画）。"""
        self.launch_clicked.emit(self._info)

    def enterEvent(self, event: QEnterEvent):
        super().enterEvent(event)
        full_desc = self._info.get("description", "")
        QToolTip.showText(
            event.globalPosition().toPoint(), full_desc, self, msecShowTime=3000,
        )


# ═══════════════════════════════════════════════════════════
#  更新确认对话框（带进度条）
# ═══════════════════════════════════════════════════════════

class UpdateDialog(QDialog):
    """「发现新版本，是否更新？」对话框。"""

    def __init__(self, plugin_info: dict, update_info: dict, parent=None):
        super().__init__(parent)
        self._update_info = update_info
        self._user_choice: Optional[bool] = None  # True=更新, False=取消
        self._setup_ui(plugin_info, update_info)

    def _setup_ui(self, pinfo, uinfo):
        self.setWindowTitle("发现新版本")
        self.setFixedSize(460, 200)
        self.setStyleSheet("QDialog { background: #ffffff; border-radius: 8px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 消息
        msg = QLabel(
            f"<b>{pinfo.get('display_name', pinfo.get('name', '?'))}</b> "
            f"有新版本可用"
        )
        msg.setFont(QFont("Microsoft YaHei", 13))
        layout.addWidget(msg)

        ver_label = QLabel(
            f"本地版本: <b style='color:#636e72'>{uinfo.get('local_version', '?')}</b>  "
            f"→ 远程版本: <b style='color:#0984e3'>{uinfo.get('remote_version', '?')}</b>"
        )
        ver_label.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(ver_label)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消，使用本地版本")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #dfe6e9; color: #2d3436;
                border: none; border-radius: 6px;
                padding: 0 20px; font-size: 12px;
            }
            QPushButton:hover { background: #b2bec3; }
        """)
        cancel_btn.clicked.connect(lambda: self._done(False))
        btn_layout.addWidget(cancel_btn)

        btn_layout.addSpacing(10)

        update_btn = QPushButton("📥 下载更新")
        update_btn.setFixedHeight(36)
        update_btn.setStyleSheet("""
            QPushButton {
                background: #0984e3; color: white;
                border: none; border-radius: 6px;
                padding: 0 24px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #0873c4; }
        """)
        update_btn.clicked.connect(lambda: self._done(True))
        btn_layout.addWidget(update_btn)

        layout.addLayout(btn_layout)

    def _done(self, choice: bool):
        self._user_choice = choice
        if choice:
            self.accept()
        else:
            self.reject()

    def user_wants_update(self) -> bool:
        return self._user_choice is True


class ProgressDialog(QDialog):
    """更新下载进度对话框。"""

    progress_changed = Signal(int, int)  # (downloaded, total)

    def __init__(self, plugin_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("正在更新")
        self.setFixedSize(400, 130)
        self.setStyleSheet("QDialog { background: #ffffff; }")
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowCloseButtonHint
        )

        self.progress_changed.connect(self._on_progress)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self._label = QLabel(f"正在下载 {plugin_name} ...")
        self._label.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFixedHeight(22)
        self._bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0; border-radius: 6px;
                background: #f5f6fa; text-align: center;
                font-size: 10px; color: #2d3436;
            }
            QProgressBar::chunk {
                background: #0984e3; border-radius: 5px;
            }
        """)
        layout.addWidget(self._bar)

    def _on_progress(self, downloaded: int, total: int):
        pct = int(downloaded / total * 100) if total > 0 else 0
        self._bar.setValue(pct)
        self._label.setText(
            f"正在下载... {downloaded // 1024} KB / {total // 1024} KB"
        )


# ═══════════════════════════════════════════════════════════
#  待开发占位卡片
# ═══════════════════════════════════════════════════════════

class PlaceholderCard(QFrame):
    """空位占位卡片 — 显示"待开发"，点击可检查 GitHub 是否有新模块。"""

    placeholder_clicked = Signal(object)  # 携带 {"category_id": str, "slot_index": int}

    PLACEHOLDER_STYLE = """
        QFrame#placeholderCard {
            background: transparent;
            border: none;
        }
    """

    def __init__(self, category_id: str, slot_index: int, parent=None):
        super().__init__(parent)
        self._category_id = category_id
        self._slot_index = slot_index
        self.setObjectName("placeholderCard")
        self.setStyleSheet(self.PLACEHOLDER_STYLE)
        self.setMinimumSize(140, 80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.placeholder_clicked.emit({
                "category_id": self._category_id,
                "slot_index": self._slot_index,
            })


# ═══════════════════════════════════════════════════════════
#  右侧九宫格页面
# ═══════════════════════════════════════════════════════════

class GridPage(QWidget):
    """右侧网格视图 — 2列3排，显示当前分类下的插件卡片 + 待开发占位。"""

    launch_plugin = Signal(dict)  # 点击启动时发射
    update_plugin = Signal(dict)  # 点击更新/安装时发射
    check_placeholder = Signal(dict)  # 点击待开发时发射

    COLS = 2
    ROWS = 3
    TOTAL_SLOTS = COLS * ROWS  # 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._category: Optional[dict] = None
        self._plugins_map: dict[str, dict] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(8)

        # ── 分类标题栏 ──
        self._header = QLabel("请从左侧选择一个分类")
        self._header.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        self._header.setStyleSheet("color: #1a1a2e;")
        layout.addWidget(self._header)

        # ── 副标题 ──
        self._subtitle = QLabel("")
        self._subtitle.setFont(QFont("Microsoft YaHei", 11))
        self._subtitle.setStyleSheet("color: #b2bec3; margin-bottom: 4px;")
        layout.addWidget(self._subtitle)

        # ── 可滚动的网格 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 8, 0, 8)
        self._grid_layout.setSpacing(16)

        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

    def show_category(self, category: dict, plugins_map: dict[str, dict]):
        """切换显示指定分类下的网格卡片（2列×3排，空位显示待开发）。"""
        self._category = category
        self._plugins_map = plugins_map

        cat_name = category.get("name", "?")
        self._header.setText(f"{category.get('icon', '📁')} {cat_name}")

        # 清空网格
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        plugin_names = category.get("plugins", [])
        active_count = len(plugin_names)
        placeholder_count = self.TOTAL_SLOTS - active_count

        self._subtitle.setText(
            f"共 {active_count} 个功能模块"
            + (f"，{placeholder_count} 个待开发" if placeholder_count > 0 else "")
        )

        # 固定 2列×3排 = 6格
        idx = 0
        for slot in range(self.TOTAL_SLOTS):
            row = slot // self.COLS
            col = slot % self.COLS

            if idx < active_count:
                # ── 真实插件卡片 ──
                pname = plugin_names[idx]
                info = plugins_map.get(pname, {
                    "name": pname,
                    "display_name": pname,
                    "version": "0.0.0",
                    "icon": "🔧",
                    "description": "",
                })
                card = ToolCard(info)
                card.launch_clicked.connect(self.launch_plugin.emit)
                card.update_clicked.connect(self.update_plugin.emit)
                self._grid_layout.addWidget(card, row, col)
                idx += 1
            else:
                # ── 待开发占位卡 ──
                placeholder = PlaceholderCard(
                    category.get("id", ""), slot
                )
                placeholder.placeholder_clicked.connect(
                    self.check_placeholder.emit
                )
                self._grid_layout.addWidget(placeholder, row, col)

            self._grid_layout.setRowStretch(row, 1)
            self._grid_layout.setColumnStretch(col, 1)



# ═══════════════════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """工具箱主窗口。"""

    # 跨线程安全信号
    _network_result = Signal(str, bool)  # ("gh"/"dl", ok)
    _refresh_done = Signal()  # 刷新完成后通知主线程
    _update_proceed = Signal(dict, dict)  # (plugin_info, update_info) 主线程弹确认框
    _update_finished = Signal(str, object, bool, bool)  # (pname, 状态, 下载成功?, 更新前已安装?)
    _updates_ready = Signal(dict, bool)  # (状态映射, 是否拉取成功)
    _placeholder_done = Signal(str, object)  # 占位卡检查完成 (kind, payload)
    _module_install_done = Signal(bool, str)  # 新模块安装完成 (ok, display_name)

    def __init__(self):
        super().__init__()
        # ── 核心数据 ──
        self._categories = load_categories()
        self._plugins_map = load_plugins()
        self._plugin_mgr = PluginManager(PLUGINS_DIR)
        self._plugin_updater = PluginUpdater(VERSION_URL, PLUGINS_DIR,
                                             config_path=PLUGINS_JSON, timeout=20)

        # ── 运行态 ──
        self._loaded_plugin_windows: dict[str, list[QWidget]] = {}
        self._progress_dlg: Optional[QDialog] = None
        # 卡片更新按钮状态映射（插件名 → ToolCard 状态），重建卡片时恢复
        self._update_states: dict[str, str] = {}
        self._update_checking: bool = False  # 全量检测进行中（防连点）
        # ── 网络状态（None=未完成，False=红，True=绿；纯展示，不拦截任何操作）──
        self._net: dict = {"gh": None, "dl": None}
        self._net_checking: bool = False    # 检测进行中（防连点）

        # 连接跨线程信号
        self._network_result.connect(self._on_network_result)
        self._refresh_done.connect(self._finish_refresh)
        self._update_proceed.connect(self._on_update_proceed)
        self._update_finished.connect(self._on_update_finished)
        self._updates_ready.connect(self._on_updates_ready)
        self._placeholder_done.connect(self._on_placeholder_done)
        self._module_install_done.connect(self._on_module_install_done)

        self._setup_window()
        self._setup_ui()
        self._setup_status_bar()

        # 默认选中第一个分类
        if self._categories:
            self._category_list.setCurrentRow(0)

        logger.info("MainWindow initialized: %d categories, %d plugins",
                     len(self._categories), len(self._plugins_map))

        # 网络状态检测（后台，不影响启动）
        self._check_network_status_raw()
        # 自动检测各插件更新状态（后台，异步回填卡片按钮）
        self._check_all_updates()

    # ── 窗口 ────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("工具箱 Toolbox")
        self.setMinimumSize(1100, 680)

        screen = QApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.58)
        h = int(screen.height() * 0.65)
        x = (screen.width() - w) // 2 + screen.x()
        y = (screen.height() - h) // 2 + screen.y()
        self.setGeometry(x, y, w, h)

        self.setStyleSheet("""
            QMainWindow { background: #f0f2f5; }
            QToolTip {
                background: #1a1a2e; color: #ffffff;
                border: 1px solid #4361ee; border-radius: 8px;
                padding: 10px; font-size: 12px;
            }
            QScrollBar:vertical {
                width: 6px; background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #c8ccd4; border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #4361ee; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0; width: 0;
            }
            QSplitter::handle { background: #e0e0e0; }
        """)

    # ── UI 构建 ─────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_top_bar())

        # Splitter: 左侧分类 | 右侧内容
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(2)
        self._splitter.setChildrenCollapsible(False)

        self._splitter.addWidget(self._build_category_panel())
        self._splitter.addWidget(self._build_right_panel())

        self._splitter.setSizes([200, 800])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._splitter, 1)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet("""
            QWidget {
                background: #1a1a2e;
                border-bottom: 2px solid #4361ee;
            }
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 20, 0)

        logo = QLabel("🧰")
        logo.setFont(QFont("Segoe UI Emoji", 18))
        layout.addWidget(logo)

        title = QLabel("工具箱 Toolbox")
        title.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(title)

        layout.addStretch()

        # 刷新插件列表
        self._refresh_btn = QPushButton("🔄 刷新插件列表")
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08); color: #c8ccd4;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px; padding: 7px 18px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.15); color: #ffffff; }
        """)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        layout.addWidget(self._refresh_btn)

        # ── 刷新更新状态（手动全量重查各插件更新按钮） ──
        self._check_updates_btn = QPushButton("🔄 刷新更新状态")
        self._check_updates_btn.setCursor(Qt.PointingHandCursor)
        self._check_updates_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08); color: #c8ccd4;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px; padding: 7px 18px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.15); color: #ffffff; }
            QPushButton:disabled { color: #636e72; }
        """)
        self._check_updates_btn.clicked.connect(self._on_check_updates_clicked)
        layout.addWidget(self._check_updates_btn)

        # ── 网络状态指示灯 ──
        layout.addSpacing(12)

        self._dot_gh = QLabel("⬤")
        self._dot_gh.setStyleSheet("color: #636e72; font-size: 16px; background: transparent;")
        layout.addWidget(self._dot_gh)
        lbl_gh = QLabel("GitHub")
        lbl_gh.setStyleSheet("color: #636e72; font-size: 11px; background: transparent;")
        layout.addWidget(lbl_gh)

        layout.addSpacing(6)

        self._dot_dl = QLabel("⬤")
        self._dot_dl.setStyleSheet("color: #636e72; font-size: 16px; background: transparent;")
        layout.addWidget(self._dot_dl)
        lbl_dl = QLabel("下载")
        lbl_dl.setStyleSheet("color: #636e72; font-size: 11px; background: transparent;")
        layout.addWidget(lbl_dl)

        # 手动重测网络按钮
        self._refresh_net_btn = QPushButton("🔄")
        self._refresh_net_btn.setToolTip("重新检测网络状态")
        self._refresh_net_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_net_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08); color: #c8ccd4;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px; padding: 2px 7px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.15); color: #ffffff; }
            QPushButton:disabled { color: #636e72; }
        """)
        self._refresh_net_btn.setFixedHeight(22)
        self._refresh_net_btn.clicked.connect(self._on_net_refresh_clicked)
        layout.addWidget(self._refresh_net_btn)

        return bar

    def _build_category_panel(self) -> QWidget:
        """左侧分类列表面板。"""
        panel = QWidget()
        panel.setStyleSheet("background: #ffffff; border-right: 1px solid #e8eaed;")
        panel.setMinimumWidth(170)
        panel.setMaximumWidth(240)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        hdr = QLabel("功能分类")
        hdr.setAlignment(Qt.AlignCenter)
        hdr.setFixedHeight(52)
        hdr.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        hdr.setStyleSheet("color: #1a1a2e; background: #ffffff; "
                          "padding: 0 20px; border-bottom: 1px solid #f0f0f0;")
        layout.addWidget(hdr)

        # 分类列表
        self._category_list = QListWidget()
        self._category_list.setFrameShape(QFrame.NoFrame)
        self._category_list.setStyleSheet("""
            QListWidget {
                background: #ffffff; border: none;
                padding: 8px 10px;
            }
            QListWidget::item {
                padding: 12px 16px;
                border-radius: 8px;
                color: #2d3436;
                font-size: 13px;
                margin: 2px 0;
            }
            QListWidget::item:hover {
                background: #f0f2f5;
                color: #4361ee;
            }
            QListWidget::item:selected {
                background: #4361ee;
                color: white;
                font-weight: bold;
            }
        """)

        for cat in self._categories:
            item = QListWidgetItem(f"  {cat.get('icon', '📁')}  {cat.get('name', '?')}")
            item.setData(Qt.UserRole, cat.get("id"))
            item.setSizeHint(QSize(0, 46))
            self._category_list.addItem(item)

        self._category_list.currentRowChanged.connect(self._on_category_changed)
        layout.addWidget(self._category_list, 1)

        # 底部分类数量
        count = QLabel(f"共 {len(self._categories)} 个分类")
        count.setFixedHeight(36)
        count.setStyleSheet("color: #b2bec3; font-size: 11px; padding: 0 20px; "
                           "border-top: 1px solid #f0f0f0;")
        layout.addWidget(count)

        return panel

    def _build_right_panel(self) -> QWidget:
        """右侧面板：九宫格视图。"""
        panel = QWidget()
        panel.setStyleSheet("background: #f0f2f5;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._grid_page = GridPage()
        self._grid_page.launch_plugin.connect(self._on_launch_plugin)
        self._grid_page.update_plugin.connect(self._on_update_clicked)
        self._grid_page.check_placeholder.connect(self._on_placeholder_clicked)

        layout.addWidget(self._grid_page)
        return panel

    def _setup_status_bar(self):
        self._status_bar = self.statusBar()
        self._status_bar.setStyleSheet("""
            QStatusBar {
                background: #ffffff; color: #636e72;
                font-size: 11px; padding: 2px 16px;
                border-top: 1px solid #e8eaed;
            }
        """)
        self._status_label = QLabel("💡 就绪 — 请从左侧选择一个分类")
        self._status_bar.addWidget(self._status_label)

    def _set_status(self, text: str):
        self._status_label.setText(text)
        logger.info("Status: %s", text)

    # ── 分类切换 ────────────────────────────────────────────

    def _on_category_changed(self, row: int):
        if row < 0 or row >= len(self._categories):
            return
        cat = self._categories[row]
        self._grid_page.show_category(cat, self._plugins_map)
        self._apply_all_card_states()  # 重建卡片后恢复更新按钮状态
        self._set_status(f"已选: {cat.get('name', '')}")

    def _apply_all_card_states(self):
        """把 _update_states 应用到所有已显示的卡片（分类切换/重建后恢复）。"""
        for card in self._grid_page.findChildren(ToolCard):
            name = card._info.get("name", "")
            if name in self._update_states:
                card.set_update_state(self._update_states[name])

    # ── 启动插件 ────────────────────────────────────────────

    def _on_launch_plugin(self, plugin_info: dict):
        """点击[启动] → 纯本地加载，零网络。

        安装/更新一律走卡片左侧的「更新」按钮。
        """
        pname = plugin_info.get("name", "")
        display = plugin_info.get("display_name", pname)

        pyd_path = os.path.join(PLUGINS_DIR, f"{pname}.pyd")
        py_path = os.path.join(PLUGINS_DIR, f"{pname}.py")
        if not os.path.exists(pyd_path) and not os.path.exists(py_path):
            self._set_status(f"{display} 未安装，请点「⬇ 安装」下载")
            return

        self._do_launch(pname)


    # ── 待开发占位点击 ─────────────────────────────────────

    def _on_placeholder_clicked(self, data: dict):
        """用户点击"待开发"占位卡 — 检查 GitHub 是否有新模块可下载。"""
        cat_id = data.get("category_id", "")
        self._set_status(f"正在检查是否有新模块上线 ...")

        def _check():
            # 显式点击 → 强制真实请求（绕过 TTL 缓存）
            manifest = self._plugin_updater.fetch_remote_manifest(force=True)
            if manifest is None:
                self._network_result.emit("gh", False)  # 回写灯红
                self._placeholder_done.emit("fail", None)
                return
            self._network_result.emit("gh", True)   # 回写灯绿

            # 找出当前分类下，本地还没装载的远程插件
            cat = next((c for c in load_categories() if c.get("id") == cat_id), None)
            if not cat:
                self._placeholder_done.emit("status", "分类无效")
                return

            remote_names = {p.get("name")
                           for p in manifest.get("plugins", [])}
            local_names = set(self._plugins_map.keys())
            new_plugins = remote_names - local_names

            if not new_plugins:
                self._placeholder_done.emit("none", None)
                return

            # 筛选属于当前分类的新插件
            cat_plugins = cat.get("plugins", [])
            available = [p for p in manifest.get("plugins", [])
                         if p.get("name") in cat_plugins
                         and p.get("name") in new_plugins]

            if not available:
                self._placeholder_done.emit("none_cat", None)
                return

            # 有可用的新模块，交由主线程逐一询问下载
            self._placeholder_done.emit("available", available)

        threading.Thread(target=_check, daemon=True).start()

    def _on_placeholder_done(self, kind: str, payload):
        """主线程：占位卡检查结果（信号驱动，安全更新 UI）。"""
        if kind == "fail":
            self._set_status("⚠️ 网络不可达，无法检查新模块")
        elif kind == "status":
            self._set_status(str(payload))
        elif kind == "none":
            QMessageBox.information(
                self, "暂无新模块",
                "目前没有新的功能模块上线，敬请期待后续更新 📅")
            self._set_status("无新模块")
        elif kind == "none_cat":
            QMessageBox.information(
                self, "暂无新模块",
                "当前分类暂无新模块，请关注其他分类的更新 📅")
            self._set_status("无新模块")
        elif kind == "available":
            for plugin in payload:
                display = plugin.get("display_name", plugin.get("name", ""))
                self._prompt_new_module(plugin, display)

    def _prompt_new_module(self, plugin_info: dict, display_name: str):
        """提示用户下载新模块。"""
        reply = QMessageBox.question(
            self, "发现新模块",
            f"发现新的功能模块「{display_name}」可下载安装！\n\n"
            f"版本: {plugin_info.get('version', '1.0.0')}\n"
            f"大小: 约 1-5 MB\n\n是否立即下载？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 下载并安装新模块
        pname = plugin_info.get("name", "")
        url = plugin_info.get("download_url", "")
        version = plugin_info.get("version", "1.0.0")

        self._module_progress_dlg = ProgressDialog(display_name, self)
        self._module_progress_dlg.show()

        def _download():
            ok = self._plugin_updater.download_plugin(
                pname, url,
                progress_callback=lambda d, t:
                    self._module_progress_dlg.progress_changed.emit(d, t),
            )
            if ok:
                self._plugin_updater.set_local_version(pname, version)
                # 更新本地注册表
                self._plugins_map[pname] = plugin_info
            # 切回主线程统一处理 UI（子线程不能安全操作界面）
            self._module_install_done.emit(ok, display_name)

        threading.Thread(target=_download, daemon=True).start()

    def _on_module_install_done(self, ok: bool, display_name: str):
        """主线程：新模块安装完成。"""
        if self._module_progress_dlg:
            self._module_progress_dlg.close()
            self._module_progress_dlg = None
        if ok:
            self._finish_refresh()
            self._set_status(f"✅ 新模块已安装: {display_name}")
            QMessageBox.information(
                self, "安装完成",
                f"「{display_name}」已安装成功 ✅\n\n"
                f"现在可以在对应分类中找到它并点击[启动]使用。")
        else:
            self._set_status(f"⚠️ 下载「{display_name}」失败，请检查网络后重试")
            QMessageBox.warning(
                self, "下载失败",
                f"下载「{display_name}」失败，请检查网络后重试。")

    def _do_launch(self, plugin_name: str):
        """加载插件 .pyd 并打开独立窗口（主线程执行，纯本地操作）。"""
        # 关掉可能还在的下载进度窗
        if self._progress_dlg:
            self._progress_dlg.close()
            self._progress_dlg = None

        display = self._plugins_map.get(plugin_name, {}).get(
            "display_name", plugin_name)
        self._set_status(f"正在加载: {display} ...")

        class_name = self._plugins_map.get(plugin_name, {}).get("class_name")

        try:
            cls = self._plugin_mgr.get_plugin_class(plugin_name, class_name)
            instance = cls()
            widget = instance.create_widget()
            widget.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            widget.show()
            widget.raise_()
            widget.activateWindow()
            if plugin_name not in self._loaded_plugin_windows:
                self._loaded_plugin_windows[plugin_name] = []
            self._loaded_plugin_windows[plugin_name].append(widget)
            self._set_status(f"已启动: {display}")
        except Exception as exc:
            logger.error("Launch plugin '%s' failed: %s", plugin_name, exc,
                         exc_info=True)
            self._set_status(f"启动失败: {display}")
            QMessageBox.warning(
                self, "插件启动失败",
                f"无法启动插件 '{plugin_name}':\n\n{exc}\n\n"
                f"请确认 plugins/{plugin_name}.pyd 文件存在且版本正确。",
            )


    # ── 后台更新检查 ─────────────────────────────────────


    # ── 更新 / 安装 ────────────────────────────────────────

    @staticmethod
    def _is_installed(pname: str) -> bool:
        """本地是否已有该插件的 .pyd 或 .py。"""
        return (os.path.exists(os.path.join(PLUGINS_DIR, f"{pname}.pyd"))
                or os.path.exists(os.path.join(PLUGINS_DIR, f"{pname}.py")))

    def _on_update_clicked(self, plugin_info: dict):
        """点击卡片「更新/安装」→ 检查 → 确认框 → 下载 → 刷新状态。"""
        pname = plugin_info.get("name", "")
        display = plugin_info.get("display_name", pname)
        self._set_status(f"正在检查 {display} 是否有新版本 ...")

        # 按钮禁用防连点（结果回来时 set_update_state 恢复）
        for card in self._grid_page.findChildren(ToolCard):
            if card._info.get("name") == pname:
                card._update_btn.setEnabled(False)

        def _check():
            # 显式点击 → 强制真实请求（绕过 TTL 缓存）
            manifest = self._plugin_updater.fetch_remote_manifest(force=True)
            if manifest is None:
                self._network_result.emit("gh", False)  # 回写灯红
                self._update_finished.emit(
                    pname, ToolCard.STATE_UNKNOWN, False, False)
                return
            self._network_result.emit("gh", True)
            update_info = self._plugin_updater.check_plugin_update(
                pname, manifest)
            if update_info is None:
                self._update_finished.emit(
                    pname, ToolCard.STATE_UP_TO_DATE, False, False)
                return
            self._update_proceed.emit(plugin_info, update_info)

        threading.Thread(target=_check, daemon=True).start()

    def _on_update_proceed(self, plugin_info: dict, update_info: dict):
        """主线程：弹确认框；确认后下载。"""
        pname = update_info.get("name", "")
        display = plugin_info.get("display_name", pname)

        dlg = UpdateDialog(plugin_info, update_info, self)
        if dlg.exec() != QDialog.Accepted:
            # 取消：恢复「有更新 / 可安装」状态
            state = (ToolCard.STATE_NOT_INSTALLED
                     if not self._is_installed(pname)
                     else ToolCard.STATE_HAS_UPDATE)
            self._update_finished.emit(pname, state, False, False)
            return

        # 确认 → 下载
        self._progress_dlg = ProgressDialog(display, self)
        self._progress_dlg.show()
        remote_ver = update_info.get("remote_version", "0.0.0")

        def _dl():
            was_installed = self._is_installed(pname)  # 下载前是否已装
            ok = self._plugin_updater.download_plugin(
                pname, update_info["download_url"],
                progress_callback=lambda d, t, dlg=self._progress_dlg:
                    dlg.progress_changed.emit(d, t),
            )
            if ok:
                self._plugin_updater.set_local_version(pname, remote_ver)
                self._plugins_map[pname]["version"] = remote_ver
                state = ToolCard.STATE_UP_TO_DATE
            else:
                state = (ToolCard.STATE_NOT_INSTALLED
                         if not was_installed
                         else ToolCard.STATE_HAS_UPDATE)
            self._update_finished.emit(pname, state, ok, was_installed)

        threading.Thread(target=_dl, daemon=True).start()

    def _on_update_finished(self, pname: str, state: str, downloaded: bool,
                            was_installed: bool):
        """主线程：更新按钮状态 + 状态栏提示。"""
        if self._progress_dlg:
            self._progress_dlg.close()
            self._progress_dlg = None

        display = self._plugins_map.get(pname, {}).get("display_name", pname)
        self._update_states[pname] = state
        for card in self._grid_page.findChildren(ToolCard):
            if card._info.get("name") == pname:
                card.set_update_state(state)

        if downloaded:
            self._finish_refresh()  # 重建列表与当前分类卡片（从磁盘重载新版本号）
            new_ver = self._plugins_map.get(pname, {}).get("version", "?")
            if was_installed:
                self._set_status(
                    f"{display} 已更新到 v{new_ver}，重新启动插件生效")
            else:
                self._set_status(f"✅ {display} 已安装 v{new_ver}，点击启动使用")
        elif state == ToolCard.STATE_UP_TO_DATE:
            self._set_status(f"{display} 已是最新版本")
        elif state == ToolCard.STATE_UNKNOWN:
            self._set_status(f"⚠️ 网络不可达，无法检查 {display} 更新")
        elif state == ToolCard.STATE_NOT_INSTALLED:
            self._set_status(f"⚠️ {display} 下载失败，请检查网络后重试")
        elif state == ToolCard.STATE_HAS_UPDATE:
            self._set_status(f"{display} 有新版本可更新")

    # ── 全量更新状态检测 ───────────────────────────────────

    def _on_check_updates_clicked(self):
        """手动触发全量重查各插件更新状态（强制真实请求，不走缓存）。"""
        if self._update_checking:
            return
        self._check_updates_btn.setText("⏳ 检查中...")
        self._set_status("正在检查各插件更新状态 ...")
        self._check_all_updates(force=True)

    def _check_all_updates(self, force: bool = False):
        """后台全量检测各插件更新状态（启动自动 + 手动按钮共用）。

        Args:
            force: True 时强制真实请求（手动刷新），False 走 TTL 缓存（启动自动）。
        """
        if self._update_checking:
            return
        self._update_checking = True
        if self._check_updates_btn:
            self._check_updates_btn.setEnabled(False)

        def _check():
            states: dict[str, str] = {}
            manifest = self._plugin_updater.fetch_remote_manifest(force=force)
            if manifest:
                for name in self._plugins_map:
                    try:
                        if self._is_installed(name):
                            uinfo = self._plugin_updater.check_plugin_update(
                                name, manifest)
                            states[name] = (ToolCard.STATE_HAS_UPDATE if uinfo
                                            else ToolCard.STATE_UP_TO_DATE)
                        else:
                            states[name] = ToolCard.STATE_NOT_INSTALLED
                    except Exception:
                        states[name] = ToolCard.STATE_UNKNOWN
                self._network_result.emit("gh", True)  # 回写灯绿
            self._updates_ready.emit(states, manifest is not None)

        threading.Thread(target=_check, daemon=True).start()

    def _on_updates_ready(self, states: dict, ok: bool):
        """主线程：应用全量检测结果到所有卡片。"""
        self._update_checking = False
        if self._check_updates_btn:
            self._check_updates_btn.setText("🔄 刷新更新状态")
            self._check_updates_btn.setEnabled(True)

        if not ok:
            # 网络不可达：全部置 unknown（可点重查）
            self._set_status("⚠️ 网络不可达，无法检查更新")
            self._update_states = {name: ToolCard.STATE_UNKNOWN
                                   for name in self._plugins_map}
            self._apply_all_card_states()
            return

        self._update_states = states
        self._apply_all_card_states()
        n_upd = sum(1 for s in states.values()
                    if s == ToolCard.STATE_HAS_UPDATE)
        self._set_status(
            f"检查完成：{n_upd} 个插件有更新" if n_upd
            else "检查完成：全部已是最新")

    # ── 刷新与更新 ──────────────────────────────────────────

    def _on_refresh_clicked(self):
        """点刷新按钮：后台同步 GitHub → 刷新界面。"""
        self._refresh_btn.setText("⏳ 刷新中...")
        self._refresh_btn.setEnabled(False)
        QApplication.processEvents()

        def _sync():
            ok = self._sync_from_github()
            # 同步成功与否都回写灯（以真实请求为准）
            self._network_result.emit("gh", ok)
            self._refresh_done.emit()

        threading.Thread(target=_sync, daemon=True).start()

    def _sync_from_github(self) -> bool:
        """从 GitHub 拉取配置（后台线程执行），返回 raw 域是否可达。"""
        remote_cat = _fetch_remote_json(CATEGORIES_URL)
        if remote_cat and "categories" in remote_cat:
            try:
                with open(CATEGORIES_JSON, "w", encoding="utf-8") as f:
                    json.dump(remote_cat, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except Exception:
                pass
        remote_plg = _fetch_remote_json(VERSION_URL)
        if remote_plg and "plugins" in remote_plg:
            local_data = load_json(PLUGINS_JSON, {})
            local_plugins = {
                p["name"]: p for p in local_data.get("plugins", [])
                if isinstance(p, dict) and p.get("name")
            }
            for gh_p in remote_plg["plugins"]:
                if not isinstance(gh_p, dict) or not gh_p.get("name"):
                    continue
                name = gh_p["name"]
                if name in local_plugins:
                    gh_p["version"] = local_plugins[name]["version"]
            try:
                with open(PLUGINS_JSON, "w", encoding="utf-8") as f:
                    json.dump(remote_plg, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except Exception:
                pass
        return remote_cat is not None or remote_plg is not None

    def _finish_refresh(self):
        """刷新完成，更新界面（主线程）。"""
        self._refresh_btn.setText("🔄 刷新插件列表")
        self._refresh_btn.setEnabled(True)

        self._categories = load_categories()
        self._plugins_map = load_plugins()

        self._category_list.blockSignals(True)
        self._category_list.clear()
        for cat in self._categories:
            item = QListWidgetItem(
                f"  {cat.get('icon', '📁')}  {cat.get('name', '?')}")
            item.setData(Qt.UserRole, cat.get("id"))
            item.setSizeHint(QSize(0, 48))
            self._category_list.addItem(item)
        self._category_list.blockSignals(False)

        if self._categories:
            self._category_list.setCurrentRow(0)
        self._set_status(f"已刷新，{len(self._categories)} 个分类，"
                         f"{len(self._plugins_map)} 个插件")

    # ── 网络状态检测 ──────────────────────────────────────

    @staticmethod
    def _url_reachable(url: str, timeout: int = 10) -> bool:
        """检测 URL 是否可达（轻量 GET，只读一小段）。

        超时设 10s：检测在后台线程跑、结果存内存，慢不阻塞任何操作；
        太短（2s）会在网络波动时误报红灯。
        """
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Toolbox-Updater/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read(1)
                return True
        except Exception:
            return False

    def _set_dot_color(self, dot: QLabel, ok: bool):
        """设置指示灯颜色。"""
        color = "#27ae60" if ok else "#e74c3c"
        dot.setStyleSheet(f"color: {color}; font-size: 16px; background: transparent;")

    def _on_network_result(self, target: str, ok: bool):
        """网络检测结果回调（主线程执行）。

        灯是纯展示，不拦截任何操作；真实请求成功/失败也会回写灯色。
        """
        self._net[target] = ok
        dot = self._dot_gh if target == "gh" else self._dot_dl
        self._set_dot_color(dot, ok)
        if target == "dl" and not ok:
            self._set_status("⚠️ 下载不可达，无法更新插件")
        # gh + dl 都有结果 → 本次检测完成，恢复刷新按钮
        if self._net.get("gh") is not None and self._net.get("dl") is not None:
            self._net_checking = False
            if self._refresh_net_btn:
                self._refresh_net_btn.setEnabled(True)
        logger.info("Network check — %s: %s", target, "OK" if ok else "FAIL")

    def _check_network_status_raw(self):
        """并行检测 gh/dl 连通性（后台线程，纯展示用途）。"""
        if self._net_checking:
            return  # 检测进行中，忽略重复触发
        self._net_checking = True
        self._net = {"gh": None, "dl": None}  # 重置，等两个结果回来才记为完成
        if self._refresh_net_btn:
            self._refresh_net_btn.setEnabled(False)

        def _check_gh():
            # 用跟更新检测相同的 URL + User-Agent，结果才可靠
            ok = self._url_reachable(VERSION_URL + "?_=1", timeout=10)
            self._network_result.emit("gh", ok)

        def _check_dl():
            # dl 灯 = github.com 域可达（下载第一跳就在这个域）
            ok = self._url_reachable(
                "https://github.com/LegendaryScriptGenew/tools_box/releases",
                timeout=10)
            self._network_result.emit("dl", ok)

        threading.Thread(target=_check_gh, daemon=True).start()
        threading.Thread(target=_check_dl, daemon=True).start()

    def _on_net_refresh_clicked(self):
        """手动重测网络（gh + dl 两灯）。"""
        if self._net_checking:
            return
        self._set_status("正在检测网络 ...")
        self._check_network_status_raw()


    # ── 关闭 ────────────────────────────────────────────────

    def closeEvent(self, event):
        for name, windows in self._loaded_plugin_windows.items():
            for w in windows:
                try:
                    w.close()
                except Exception:
                    pass
        self._loaded_plugin_windows.clear()
        logger.info("Toolbox shutdown.")
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei", 10))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()