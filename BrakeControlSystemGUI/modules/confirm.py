from PyQt5 import QtCore
from PyQt5.QtWidgets import QDialog
from uis.manual_control_confirm import Ui_Form as Ui_ManualControlForm
from uis.auto_control_confirm import Ui_Form as Ui_AutoControlForm


class ManualControlConfirmDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)  # 始终置顶
        self.ui = Ui_ManualControlForm()
        self.ui.setupUi(self)
        self.setWindowTitle("场控模式确认")
        # 连接按钮
        self.ui.btn_confirm.clicked.connect(self.accept)
        self.ui.btn_cancel.clicked.connect(self.reject)


class AutoControlConfirmDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)  # 始终置顶
        self.ui = Ui_AutoControlForm()
        self.ui.setupUi(self)
        self.setWindowTitle("集控模式确认")
        # 连接按钮
        self.ui.btn_confirm.clicked.connect(self.accept)
        self.ui.btn_cancel.clicked.connect(self.reject)

    def on_confirm_clicked(self):
        if self.sam_client:
            print("[确认] 已点击集中控制确认按钮，发送ACQ指令")
            self.sam_client.post_command_signal.emit("REQUEST_CENTRAL_CONTROL", {})
        self.accept()