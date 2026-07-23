# -*- coding: utf-8 -*-
"""
统一日志模块。
所有日志写入 {APP_DIR}/logs/ 目录，按日滚动，保留 30 天。

用法：
    from framework.logger import get_logger
    logger = get_logger("toolbox")
    logger.info("消息")

在 main.py 中需先调用 configure_logging() 设定日志目录（支持打包后路径）。
"""
import os
import logging
from logging.handlers import TimedRotatingFileHandler


_log_dir: str | None = None


def configure_logging(log_dir: str):
    """设定日志目录（打包后需从 main.py 传入正确的 APP_DIR）。"""
    global _log_dir
    _log_dir = log_dir


def _resolve_log_dir() -> str:
    if _log_dir:
        return _log_dir
    # 自动探测：framework/logger.py → 项目根
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "logs")


def get_logger(name: str) -> logging.Logger:
    """获取带每日滚动文件输出的 Logger。

    Args:
        name: Logger 名称，同时也是日志文件名前缀（如 "toolbox" → toolbox.log）

    Returns:
        全局单例的 Logger 实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    log_dir = _resolve_log_dir()
    os.makedirs(log_dir, exist_ok=True)

    fh = TimedRotatingFileHandler(
        os.path.join(log_dir, f"{name}.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)

    return logger
