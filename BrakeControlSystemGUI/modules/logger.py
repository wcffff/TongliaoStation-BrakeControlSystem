import datetime
import os

from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QWidget

from uis.history import Ui_Form


class Logger(QObject):
    """集中管理日志记录与显示的类"""

    log_signal = pyqtSignal(str)
    show_window_signal = pyqtSignal()
    close_window_signal = pyqtSignal()

    def __init__(self, parent=None):
        """初始化日志目录、窗口和信号连接"""
        super().__init__(parent)
        self.log_dir = "logs"
        os.makedirs(self.log_dir, exist_ok=True)
        self.logs = []  # 最新100条日志
        self.window = self._init_window()

        self._load_recent_logs()

        self.log_signal.connect(self.append_log)
        self.show_window_signal.connect(self.window.show)
        self.close_window_signal.connect(self.window.close)

    def _init_window(self):
        """初始化日志显示窗口"""
        form = QWidget()
        # form.setWindowFlags(
        #     form.windowFlags() | QtCore.Qt.WindowStaysOnTopHint
        # )
        form.setWindowFlags(
                QtCore.Qt.Window |
                QtCore.Qt.WindowTitleHint |
                QtCore.Qt.CustomizeWindowHint |
                QtCore.Qt.WindowCloseButtonHint |
                QtCore.Qt.WindowStaysOnTopHint  # 添加此标志位
        )
        self.ui = Ui_Form()
        self.ui.setupUi(form)
        return form

    def _load_recent_logs(self):
        """读取今天日志文件中最近的100行"""
        path = self._get_log_file_path()
        if not os.path.exists(path):
            return

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.logs = [line.strip() for line in lines[-100:]]

        # 显示到 textBrowser
        self.ui.textBrowser.setPlainText("\n".join(self.logs))
        self.ui.textBrowser.verticalScrollBar().setValue(
            self.ui.textBrowser.verticalScrollBar().maximum()
        )

        self.ui.textBrowser.verticalScrollBar().setValue(
            self.ui.textBrowser.verticalScrollBar().maximum()
        )

    def _get_log_file_path(self):
        """返回当天日志文件的完整路径"""
        today = datetime.date.today().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"{today}.log")

    @pyqtSlot(str)
    def append_log(self, msg: str):
        """追加日志记录到界面和文件"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        self.logs.append(full_msg)
        if len(self.logs) > 100:
            self.logs.pop(0)

        # 写入UI
        self.ui.textBrowser.setPlainText("\n".join(self.logs))
        self.ui.textBrowser.verticalScrollBar().setValue(
            self.ui.textBrowser.verticalScrollBar().maximum()
        )

        self.ui.textBrowser.verticalScrollBar().setValue(
            self.ui.textBrowser.verticalScrollBar().maximum()
        )

        # 写入文件
        with open(self._get_log_file_path(), "a", encoding="utf-8") as f:
            f.write(full_msg + "\n")

    def show(self):
        """显示日志窗口"""
        self.show_window_signal.emit()

    def close(self):
        """关闭日志窗口"""
        self.close_window_signal.emit()
