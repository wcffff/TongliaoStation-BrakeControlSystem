import datetime
import enum

from PyQt5.QtCore import pyqtSlot, QTimer
from PyQt5.QtWidgets import QMainWindow, QFrame, QDialog

from modules.hot_standby import HotStandby, MachineRole, HeartbeatStatus
from modules.logger import Logger
from modules.tcp_client import DownlinkTcpClient
from modules.up_link import SamTcpClient
from uis.brake_control_system import Ui_Form

from modules.confirm import ManualControlConfirmDialog
from modules.confirm import AutoControlConfirmDialog

#KVM引入TCP
from modules.tcp_client import TcpClient

#语音播报
from modules.sound import VoiceAlertPlayer

"""异常捕获"""
import sys
import traceback

import queue

def excepthook(type_, value, tb):
    print("全局未捕获异常:")
    traceback.print_exception(type_, value, tb)

sys.excepthook = excepthook

VALID_FUNCTIONS = {"STOPPER", "ANTI_SLIP"}
VALID_TRACKS = set(range(2, 25))

# 每个功能类型允许的设备编号集合（整数值）
VALID_DEVICE_IDS = {
    "STOPPER": {1, 2, 3},     # 1号，2号，3号
    "ANTI_SLIP": {1},               # 1号
}


class StopperState(enum.IntEnum):
    STATE_INIT = 1,
    STATE_STOP_AT_BRAKE = 2,
    STATE_STOP_AT_RELEASE = 3,
    STATE_MAINTAIN = 4,
    ERROR_VALVE_ANOMALY = 100,
    ERROR_RELEASE_CONTACT_ERROR_CLOSED = 101,
    ERROR_BRAKE_CONTACT_ERROR_OPEN = 102,
    ERROR_BRAKE_CONTACT_ERROR_CLOSED = 103,
    ERROR_RELEASE_CONTACT_ERROR_OPEN = 104,
    ERROR_CONTACTS_BOTH_CLOSED = 105,
    ERROR_CONTACTS_BOTH_OPEN = 106,
    ERROR_VALVE_FAULT = 110,  # 111–141 电磁阀故障范围起点RELEASE_CONTACT_ERROR_CLOSED = 101


stopper_state_map = {
    StopperState.STATE_INIT: "正在初始化",
    StopperState.STATE_STOP_AT_BRAKE: "制动到位",
    StopperState.STATE_STOP_AT_RELEASE: "缓解到位",
    StopperState.STATE_MAINTAIN: "处于检修状态",
    StopperState.ERROR_VALVE_ANOMALY: "无控制指令电磁阀动作",
    StopperState.ERROR_RELEASE_CONTACT_ERROR_CLOSED: "缓解触点错误闭合",
    StopperState.ERROR_BRAKE_CONTACT_ERROR_OPEN: "制动触点错误断开",
    StopperState.ERROR_BRAKE_CONTACT_ERROR_CLOSED: "制动触点错误闭合",
    StopperState.ERROR_RELEASE_CONTACT_ERROR_OPEN: "缓解触点错误断开",
    StopperState.ERROR_CONTACTS_BOTH_CLOSED: "制动/缓解触点同时闭合",
    StopperState.ERROR_CONTACTS_BOTH_OPEN: "制动/缓解触点同时断开",
    StopperState.ERROR_VALVE_FAULT: "电磁阀故障"
}


class AntiSlipState(enum.IntEnum):
    STATE_INIT = 1,
    STATE_STOP_AT_BRAKE_REMOTE = 2,
    STATE_STOP_AT_RELEASE_REMOTE = 3,
    STATE_STOP_LOCAL = 4,
    STATE_BRAKING_REMOTE = 5,
    STATE_RELEASING_REMOTE = 6,
    STATE_BRAKING_LOCAL = 7,
    STATE_RELEASING_LOCAL = 8,
    STATE_PUSH_AWAY = 9,
    WARNING_NOT_IN_PLACE = 10,
    ERROR_BOTH_SWITCH_ON = 100,
    ERROR_RELEASE_SWITCH_ON = 101,
    ERROR_BRAKE_SWITCH_OFF = 102,
    ERROR_BRAKE_SWITCH_ON = 103,
    ERROR_RELEASE_SWITCH_OFF = 104,
    ERROR_BRAKE_TIMEOUT = 110,
    ERROR_RELEASE_TIMEOUT = 111
    ERROR_NOT_UNIFIED_RELEASE = 120,
    ERROR_NOT_UNIFIED_BRAKE = 121,


anti_slip_state_map = {
    AntiSlipState.STATE_INIT: "正在初始化",
    AntiSlipState.STATE_STOP_AT_BRAKE_REMOTE: "制动到位（远程）",
    AntiSlipState.STATE_STOP_AT_RELEASE_REMOTE: "缓解到位（远程）",
    AntiSlipState.STATE_STOP_LOCAL: "处于现场（检修）状态",
    AntiSlipState.STATE_BRAKING_REMOTE: "制动中（远程）",
    AntiSlipState.STATE_RELEASING_REMOTE: "缓解中（远程）",
    AntiSlipState.STATE_BRAKING_LOCAL: "制动中（检修）",
    AntiSlipState.STATE_RELEASING_LOCAL: "缓解中（检修）",
    AntiSlipState.STATE_PUSH_AWAY: "主鞋推走",
    AntiSlipState.WARNING_NOT_IN_PLACE: "进入远程控制时无表示",
    AntiSlipState.ERROR_BOTH_SWITCH_ON: "出现双表示故障",
    AntiSlipState.ERROR_RELEASE_SWITCH_ON: "故障：错误出现缓解表示",
    AntiSlipState.ERROR_BRAKE_SWITCH_OFF: "故障：错误消失制动表示",
    AntiSlipState.ERROR_BRAKE_SWITCH_ON: "故障：错误出现制动表示",
    AntiSlipState.ERROR_RELEASE_SWITCH_OFF: "故障：错误消失缓解表示",
    AntiSlipState.ERROR_BRAKE_TIMEOUT: "制动超时",
    AntiSlipState.ERROR_RELEASE_TIMEOUT: "缓解超时",
    AntiSlipState.ERROR_NOT_UNIFIED_RELEASE: "故障：鞋位与电机位缓解表示不一致",
    AntiSlipState.ERROR_NOT_UNIFIED_BRAKE: "故障：鞋位与电机位制动表示不一致"
}


class BrakeControlSystemGUI(QMainWindow, Ui_Form):
    def __init__(self, machine_id):
        super(BrakeControlSystemGUI, self).__init__()
        self.setupUi(self)
        self.showFullScreen()

        # 设置设备ID
        self.machine_id = machine_id
        self.update_machine_id()

        # 双机热备模块
        self.local_role = None
        self.local_status = None
        self.remote_role = None
        self.remote_status = None
        self.hot_standby = HotStandby()
        self.hot_standby.status_updated.connect(self.update_hot_standby_status)

        # 日志模块
        self.logger = Logger()
        self.BTN_search.clicked.connect(self.show_log_window)
        
        self.selected_track = 0

        self.log(f"{self.machine_id}机启动")

        self.downlink_host = "192.168.1.253"

        self.update_datetime()
        self.time_update_timer = QTimer(self)
        self.time_update_timer.timeout.connect(self.update_datetime)
        self.time_update_timer.start(1000)

        # 设置设备状态
        self.track_statuses = {}
        self.tcp_clients = {}
        self.command_fault_status = {}
        
        self.lock_status = {track_id: False for track_id in range(2, 2 + 23)}

        # 新增KVM发送用客户端
        self.command_sender = TcpClient("192.168.1.253", 1030)

        # 新增KVM定时器，每秒检查一次
        self.master_command_timer = QTimer(self)
        self.master_command_timer.timeout.connect(self.send_master_command)
        self.master_command_timer.start(1000)

        #SAM模块
        self.sam_A = SamTcpClient("192.168.1.150", 1032)
        self.sam_B = SamTcpClient("192.168.1.150", 1033)
        self.sam_A.sam_event.connect(self.create_sam_event_handler("A"))
        self.sam_B.sam_event.connect(self.create_sam_event_handler("B"))
        self.sam_A.set_sdi_data_callback(lambda _: self.sam_A.build_sdi_data(self.track_statuses, self.lock_status))
        self.sam_B.set_sdi_data_callback(lambda _: self.sam_B.build_sdi_data(self.track_statuses, self.lock_status))

        # SAM状态
        self.sam_A_is_master = False
        self.sam_B_is_master = False

        # 设置控制状态，初始化为场控
        self.is_central_control = False

        self._initialize_track_statuses()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.broadcast_query_command)
        self.timer.start(1000)

        self.selected_devices = set()
        self.selection_timers = {}  # 存储活跃的计时器 {(track, function, device): timer}

        self.last_report_time = {}
        self._initialize_last_report_time()
        self.timeout_threshold = 12
        self.timeout_timer = QTimer(self)
        self.timeout_timer.timeout.connect(self.check_report_timeout)
        self.timeout_timer.start(1000)

        # 引用UI中的QFrame
        self.frame = self.findChild(QFrame, "frame")  # "frame"是你QFrame的objectName
        self.frame.hide()  # 初始时隐藏

        # 设置鼠标追踪
        self.setMouseTracking(True)
        self.frame.setMouseTracking(True)

        self.BTN_remote.clicked.connect(self.show_manual_control_confirm)
        self.BTN_sam.clicked.connect(self.show_auto_control_confirm)
        self.sam_A.control_mode_signal.connect(self.create_sam_master_handle("A"))
        self.sam_B.control_mode_signal.connect(self.create_sam_master_handle("B"))

        #语音播报
        self.voice_alert_player = VoiceAlertPlayer()
        
        #初始化上一条指令状态，以及增加最后一条指令状态比较的定时器
        self.last_command = {}
        self.resend_status = {}
        self.init_last_command()
        
        self.command_compare_timer = QTimer(self)
        self.command_compare_timer.timeout.connect(self.compare_last_command)
        # 每隔3s比较一次指令
        self.command_compare_timer.start(3000)
            
        # 增加控制指令发送队列, 以及定时100ms处理该发送队列
        self.command_queue = queue.Queue()
        
        self.command_send_timer = QTimer(self)
        self.command_send_timer.timeout.connect(self.process_command_queue)
        self.command_send_timer.start(100) 
        
        
    
    def reset_track_fatal_error(self, track_id):
        """复位指定股道的所有设备指令下发故障状态"""
        for function in ["STOPPER", "ANTI_SLIP"]:
            device_ids = [1, 2, 3] if function == "STOPPER" else [1]
            for device_id in device_ids:
                key = (track_id, function, device_id)
                if self.command_fault_status.get(key, False):
                    self.command_fault_status[key] = False
                    # 同步重置last_command，避免继续重发
                    if function == "STOPPER":
                        self.last_command[track_id][function][device_id] = StopperState.STATE_INIT
                    else:
                        self.last_command[track_id][function][device_id] = AntiSlipState.STATE_INIT
                    self.update_device_button(track_id, function, device_id)
        self.log(f"{track_id}道所有指令下发故障已复位")
    
    def init_last_command(self):
        # 初始化last_command和resend_status
        for track_id in range(2, 2 + 23):  # 2~24道
            self.last_command[track_id] = {}
            for fun in ["STOPPER", "ANTI_SLIP"]:
                self.last_command[track_id][fun] = {}
                if fun == "STOPPER":
                    for device_id in range(1, 4):  # 1~3号停车器
                        self.last_command[track_id][fun][device_id] = StopperState.STATE_INIT
                else:  # ANTI_SLIP
                    self.last_command[track_id][fun][1] = AntiSlipState.STATE_INIT
        
        for track_id in range(2, 2 + 23):
            for function in ["STOPPER", "ANTI_SLIP"]:
                device_ids = [1, 2, 3] if function == "STOPPER" else [1]
                for device_id in device_ids:
                    self.resend_status[(track_id, function, device_id)] = {"round": 0}
                    
        for track_id in range(2, 2 + 23):
            for function in ["STOPPER", "ANTI_SLIP"]:
                device_ids = [1, 2, 3] if function == "STOPPER" else [1]
                for device_id in device_ids:
                    self.command_fault_status[(track_id, function, device_id)] = False  # False=无故障，True=故障

        
    def compare_last_command(self):
        """比较指令与状态，并处理重发逻辑"""
        now = datetime.datetime.now()
        for track_id in range(2, 25):
            for function in ["STOPPER", "ANTI_SLIP"]:
                device_ids = [1, 2, 3] if function == "STOPPER" else [1]
                for device_id in device_ids:
                    # 跳过已故障的设备
                    if self.command_fault_status.get((track_id, function, device_id), False):
                        continue

                    last_cmd = self.last_command[track_id][function][device_id]
                    state = self.track_statuses[track_id][function][device_id]["STATE"]
                    resend_info = self.resend_status[(track_id, function, device_id)]

                    # 判断状态
                    if function == "STOPPER":
                        is_brake = (state == StopperState.STATE_STOP_AT_BRAKE)
                        is_release = (state == StopperState.STATE_STOP_AT_RELEASE)
                    else:
                        is_brake = (state == AntiSlipState.STATE_STOP_AT_BRAKE_REMOTE)
                        is_release = (state == AntiSlipState.STATE_STOP_AT_RELEASE_REMOTE)

                    # 需要重发的情况
                    need_resend = (last_cmd == "BRAKE" and is_release) or (last_cmd == "RELEASE" and is_brake)
                    if need_resend:
                        # 每3秒重发一次，每次3条
                        command = {
                            "FUN": function,
                            "MODE": "REMOTE_CONTROL",
                            "DEVICE": device_id,
                            "TRACK": track_id,
                            "CMD": last_cmd
                        }
                        for _ in range(3):
                            self.command_queue.put(command)
                        resend_info["round"] = resend_info.get("round", 0) + 1
                        self.log(f"将重发{track_id}道{('第'+str(device_id)+'台停车器' if function=='STOPPER' else '防溜器')}{'制动' if last_cmd=='BRAKE' else '缓解'}指令，第{resend_info['round']}轮")

                        if resend_info["round"] >= 3:
                            self.log(f"故障：{track_id}道{('第'+str(device_id)+'台停车器' if function=='STOPPER' else '防溜器')}多次重发指令无响应")
                            self.command_fault_status[(track_id, function, device_id)] = True
                            # 关键：重置last_command，避免继续重发
                            if function == "STOPPER":
                                self.last_command[track_id][function][device_id] = StopperState.STATE_INIT
                                self.track_statuses[track_id][function][device_id]["STATE"] = StopperState.STATE_INIT
                            else:
                                self.last_command[track_id][function][device_id] = AntiSlipState.STATE_INIT
                                self.track_statuses[track_id][function][device_id]["STATE"] = AntiSlipState.STATE_INIT
                            self.update_device_button(track_id, function, device_id)
                    else:
                        # 状态已匹配或已经在执行状态，重置重发状态
                        if function == "STOPPER":
                            self.last_command[track_id][function][device_id] = StopperState.STATE_INIT
                        else:
                            self.last_command[track_id][function][device_id] = AntiSlipState.STATE_INIT
                        resend_info["round"] = 0

    
        # KVM切换发送函数
    def send_master_command(self):
        if self.local_role != MachineRole.MASTER:
            return

        if self.machine_id == "A":
            print("[定时发送] A机主用 -> 发送0x0A")
            self.command_sender.send_data(b'\x0A')
        elif self.machine_id == "B":
            print("[定时发送] B机主用 -> 发送0x0B")
            self.command_sender.send_data(b'\x0B')

    def create_sam_master_handle(self, sam_id):
        def update_control_mode_label(mode):
            if getattr(self, f"sam_{sam_id}_is_master"):
                if mode == 0x55:
                    text = "集控"
                    self.lock_all_buttons()
                else:
                    text = "场控"
                    self.unlock_all_buttons()
                self.label_control_method.setText(text)
                self.label_control_method.setStyleSheet(
                    f"font-size: 12;"
                    f"font-family: 'Microsoft YaHei';"
                    f"font-weight: bold;"
                    f"color: rgb(0, 255, 0);"  # 绿色
                    f"background-color: rgb(0, 0, 0);"  # 黑色背景
                )

        return update_control_mode_label

    def show_manual_control_confirm(self):
        dialog = ManualControlConfirmDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.log("用户确认切换为场控模式")
            # 仅保留 is_master 状态，不改动
            self.sam_A.set_control_mode(0xAA)
            self.sam_A.post_command_signal.emit("SEND_RSR", {})
            self.sam_B.set_control_mode(0xAA)
            self.sam_B.post_command_signal.emit("SEND_RSR", {})
            print("按下场控按钮，发送RSR")
        else:
            # 用户点击了取消
            self.log("用户取消了场控模式切换")

    def show_auto_control_confirm(self):
        dialog = AutoControlConfirmDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            if self.sam_A_is_master:
                self.sam_A.post_command_signal.emit("REQUEST_CENTRAL_CONTROL", {})
            if self.sam_B_is_master:
                self.sam_B.post_command_signal.emit("REQUEST_CENTRAL_CONTROL", {})
            self.log("用户确认切换为集控模式，已发送 ACQ 指令")
        else:
            self.log("用户取消了集控模式切换")

    def create_sam_event_handler(self, sam_id):
        def handle_sam_event(data):
            """
            接收SAM下发的BCC帧，转换为控制命令发给下位机，并生成整洁日志。"""
            if data.get("type") == "rsr":
                print(f"{sam_id} rsr begin")
                self.handle_sam_event_rsr(data, sam_id)
                print(f"{sam_id} rsr end")
            if data.get("type") == "bcc":
                self.handle_sam_event_bcc(data)

        return handle_sam_event

    def handle_sam_event_rsr(self, data, sam_id):
        is_master = data["data"]["sam_master_backup"] == 0x55
        control_mode = data["data"]["sam_allow_central_control"]
        self.is_central_control = True if control_mode == 0x55 else False
        if sam_id == "A":
            self.sam_A_is_master = is_master
            self.sam_B_is_master = not is_master
            self.label_SAMA_state.setText(
                f"<html><head/><body><p align=\"center\"><span style=\" font-size:12pt; font-weight:600;\">"
                f"{'主用' if self.sam_A_is_master else '备用'}"
                f"</span></p></body></html>"
            )
            self.label_SAMB_state.setText(
                f"<html><head/><body><p align=\"center\"><span style=\" font-size:12pt; font-weight:600;\">"
                f"{'主用' if self.sam_B_is_master else '备用'}"
                f"</span></p></body></html>"
            )
        elif sam_id == "B":
            self.sam_B_is_master = is_master
            self.sam_A_is_master = not is_master
            self.label_SAMA_state.setText(
                f"<html><head/><body><p align=\"center\"><span style=\" font-size:12pt; font-weight:600;\">"
                f"{'主用' if self.sam_A_is_master else '备用'}"
                f"</span></p></body></html>"
            )
            self.label_SAMB_state.setText(
                f"<html><head/><body><p align=\"center\"><span style=\" font-size:12pt; font-weight:600;\">"
                f"{'主用' if self.sam_B_is_master else '备用'}"
                f"</span></p></body></html>"
            )


    def handle_sam_event_bcc(self, data):
        # 获取对应的控制指令
        bcc_data = data.get("data", {})
        command_type = bcc_data.get("command_type")
        # 获取指令对应的股道列表
        tracks = bcc_data.get("tracks", [])

        bcc_mapping = {
            0x05: ("BRAKE", ["STOPPER", "ANTI_SLIP"]),
            0x75: ("BRAKE", ["STOPPER", "ANTI_SLIP"]),
            0x45: ("RELEASE", ["ANTI_SLIP"]),
            0x4A: ("RELEASE", ["ANTI_SLIP"]),
            0x0A: ("RELEASE", ["STOPPER", "ANTI_SLIP"]),
            0x7A: ("RELEASE", ["STOPPER", "ANTI_SLIP"]),
            0x15: ("BRAKE", ["STOPPER"]),
            0x1A: ("RELEASE", ["STOPPER"]),
            0x85: ("LOCK", ["ANTI_SLIP"]),
            0x8A: ("UNLOCK", ["ANTI_SLIP"]),
            0x25: ("BRAKE", ["ANTI_SLIP"]),
            0x2A: ("RELEASE", ["ANTI_SLIP"]),
        }

        if command_type not in bcc_mapping:
            self.log(f"[BCC] 未识别的命令类型: 0x{command_type:02X}")
            return

        cmd, target_functions = bcc_mapping[command_type]
        cmd_cn = {
            "BRAKE": "制动",
            "RELEASE": "缓解",
            "LOCK": "锁闭",
            "UNLOCK": "解锁"
        }

        # 记录哪些功能控制了哪些股道
        func_track_map = {func: set() for func in ["STOPPER", "ANTI_SLIP"]}

        active_sam = self.sam_A if self.sam_A_is_master else self.sam_B
        if active_sam.my_control_mode == 0x55:
            for raw_track_id in tracks:
                track_id = raw_track_id + 1
                if track_id not in self.tcp_clients:
                    continue
                if cmd in ["LOCK", "UNLOCK"]:
                    # 锁闭或解锁时，仅修改股道锁闭或解锁状态，不向下位机发送消息
                    if cmd == "LOCK":
                        self.lock_status[track_id] = True
                        self.lock_specific_track_buttons(track_id)
                    else:
                        self.lock_status[track_id] = False
                        self.unlock_specific_track_buttons(track_id)

                    self.track_buttons_lock_display(track_id)

                else:    # 其余状态发送控制命令到下位机
                    for function in target_functions:
                        device_ids = [1, 2, 3] if function == "STOPPER" else [1]
                        for device_id in device_ids:
                            command = {
                                "FUN": function,
                                "MODE": "REMOTE_CONTROL",
                                "DEVICE": device_id,
                                "TRACK": track_id,
                                "CMD": cmd
                            }
                            if not self.lock_status[track_id]:
                                # self.tcp_clients[track_id].send_downlink_command.emit(command)
                                self.last_command[track_id][function][device_id] = cmd
                                for _ in range(3):
                                    self.command_queue.put(command)
                            func_track_map[function].add(track_id)

            # 分析是否同时控制两个功能
            common_tracks = func_track_map["STOPPER"] & func_track_map["ANTI_SLIP"]
            only_stopper = func_track_map["STOPPER"] - common_tracks
            only_anti_slip = func_track_map["ANTI_SLIP"] - common_tracks

            if common_tracks:
                self.log(f"SAM控制（{', '.join(f'{t}道' for t in sorted(common_tracks))}）"
                         f"停车器和防溜器 {cmd_cn[cmd]}")
            if only_stopper:
                self.log(f"SAM控制（{', '.join(f'{t}道' for t in sorted(only_stopper))}）"
                         f"停车器 {cmd_cn[cmd]}")
            if only_anti_slip:
                self.log(f"SAM控制（{', '.join(f'{t}道' for t in sorted(only_anti_slip))}）"
                         f"防溜器 {cmd_cn[cmd]}")

    def update_datetime(self):
        """更新日期时间显示"""
        current_time = datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        self.label_5.setText(
            f"<html><head/><body><p><span style='font-size:16pt; font-weight:600;'>{current_time}</span></p></body></html>")

    def check_report_timeout(self):
        """超时检测核心方法"""
        now = datetime.datetime.now()

        for track_id in range(2, 2 + 23):
            for function, device_id in zip(["STOPPER", "STOPPER", "STOPPER", "ANTI_SLIP"], [1, 2, 3, 1]):
                key = (track_id, function, device_id)
                last_time = self.last_report_time.get(key, datetime.datetime.min)

                # 计算时间差
                time_diff = (now - last_time).total_seconds()

                if time_diff > self.timeout_threshold:
                    # 只有当设备当前不是error状态时才更新
                    if self.track_statuses[track_id][function][device_id]["STATE"] != 200:
                        self.track_statuses[track_id][function][device_id]["STATE"] = 200

                        if function == 'STOPPER':
                            self.log(f"{track_id}道第{device_id}台停车器通信超时")
                            self.voice_alert_player.add_alert_to_queue(f"{track_id}道停车器通信故障")
                        else:
                            self.log(f"{track_id}道防溜器通信超时")
                            self.voice_alert_player.add_alert_to_queue(f"{track_id}道防溜器通信故障")
                self.update_device_button(track_id, function, device_id)

    def broadcast_query_command(self):
        if self.local_role == MachineRole.BACKUP:
            return
        for track_id in range(2, 2 + 23):
            query_command = {
                "FUN": "ALL_TYPES",
                "MODE": "REMOTE_CONTROL",
                "DEVICE": 0,
                "TRACK": 0,
                "CMD": "QUERY"
            }
            self.tcp_clients[track_id].send_downlink_command.emit(query_command)


    def _initialize_last_report_time(self):
        for track_id in range(2, 2 + 23):
            for device_id in range(1, 1 + 3):
                self.last_report_time[(track_id, "STOPPER", device_id)] = datetime.datetime.now()
            self.last_report_time[(track_id, "ANTI_SLIP", 1)] = datetime.datetime.now()

    def _initialize_track_statuses(self):
        """Initializes the device status dictionary with default values."""
        for track_id, port in zip(range(2, 2 + 23), range(1031, 1031 + 23)):
            self.track_statuses[track_id] = {
                "STOPPER": {
                    1: {
                        "MODE": None,
                        "STATE": StopperState.STATE_INIT,
                        "IO_16_9": 0xFF,
                        "IO_8_1": 0xFF
                    },
                    2: {
                        "MODE": None,
                        "STATE": StopperState.STATE_INIT,
                        "IO_16_9": 0xFF,
                        "IO_8_1": 0xFF
                    },
                    3: {
                        "MODE": None,
                        "STATE": StopperState.STATE_INIT,
                        "IO_16_9": 0xFF,
                        "IO_8_1": 0xFF
                    }
                },
                "ANTI_SLIP": {
                    1: {
                        "MODE": None,
                        "STATE": AntiSlipState.STATE_INIT,
                        "IO_16_9": 0xFF,
                        "IO_8_1": 0xFF
                    }
                }
            }
            self.tcp_clients[track_id] = DownlinkTcpClient(self.downlink_host, port)
            for device_id in range(1, 1 + 3):
                self.update_device_button(track_id, "STOPPER", device_id)
                button = getattr(self, f"BTN{track_id}_{device_id}")
                button.clicked.connect(self.create_device_handler(track_id, "STOPPER", device_id))
            self.update_device_button(track_id, "ANTI_SLIP", 1)
            button = getattr(self, f"BTN{track_id}_{4}")
            button.clicked.connect(self.create_device_handler(track_id, "ANTI_SLIP", 1))
            button = getattr(self, f"BTN{track_id}_{5}")
            button.clicked.connect(self.create_track_handler(track_id))
            button = getattr(self, f"BTN{track_id}_{6}")
            button.clicked.connect(self.create_lock_handler(track_id))
            button = getattr(self, f"BTN{track_id}_7")
            button.clicked.connect(self.create_track_reset_handler(track_id))
            self.tcp_clients[track_id].parsed_uplink_packet.connect(self._update_device_status)

            self.BTN_brake.clicked.connect(self.send_brake_command)
            self.BTN_release.clicked.connect(self.send_release_command)

    def send_brake_command(self):
        self.send_control_command("BRAKE")

    def send_release_command(self):
        self.send_control_command("RELEASE")

    def send_control_command(self, cmd):
        """发送控制命令"""
        if not self.selected_devices:
            return

        try:
            for circle in range(3):
                for (track_id, function, device_id) in self.selected_devices:
                    command = {
                        "FUN": function,
                        "MODE": "REMOTE_CONTROL",
                        "DEVICE": device_id,
                        "TRACK": track_id,
                        "CMD": cmd
                    }
                    # 将新指令入队
                    self.command_queue.put(command)
                    # self.tcp_clients[track_id].send_downlink_command.emit(command) 
                    if circle == 0:
                        msg = (
                            f"上位机发送{'制动' if cmd == 'BRAKE' else '缓解'}指令"
                            f"到{track_id}道"
                        )
                        if function == 'STOPPER':
                            msg += f"第{device_id}台停车器"
                        else:
                            msg += "防溜器"
                        self.log(msg)
                        self.last_command[track_id][function][device_id] = cmd
                        
        finally:
            self.deselect_all_devices()

    def process_command_queue(self):
        """处理控制指令发送队列"""
        if not self.command_queue.empty():
            command = self.command_queue.get()
            track_id = command["TRACK"]
            if track_id in self.tcp_clients:
                self.tcp_clients[track_id].send_downlink_command.emit(command)
    
    def deselect_all_devices(self):
        """取消所有设备选择"""
        # 先取消所有计时器
        self.cancel_all_timers()

        # 清除设备选择状态
        for track_id in range(2, 2 + 23):
            # 处理单个设备按钮
            for device_id in range(1, 1 + 4):
                button = getattr(self, f"BTN{track_id}_{device_id}")
                if button.isChecked():
                    button.setChecked(False)

        # 清空选中集合
        self.selected_devices.clear()
        self.selected_track = 0

    def cancel_all_timers(self):
        """取消所有激活的计时器"""
        # 取消设备级计时器
        for timer in self.selection_timers.values():
            timer.stop()
        self.selection_timers.clear()

    def create_track_handler(self, track_id):
        def handler():
            checked = 0
            enabled = 0
            for device_id in range(1, 1 + 4):
                button = getattr(self, f"BTN{track_id}_{device_id}")
                if button.isChecked():
                    checked += 1
                if button.isEnabled():
                    enabled += 1
            for device_id in range(1, 1 + 4):
                button = getattr(self, f"BTN{track_id}_{device_id}")
                if checked != enabled and button.isEnabled():
                    self.select_device(track_id, "ANTI_SLIP" if device_id == 4 else "STOPPER",
                                       1 if device_id == 4 else device_id)
                else:
                    self.deselect_device(track_id, "ANTI_SLIP" if device_id == 4 else "STOPPER",
                                         1 if device_id == 4 else device_id)
            if self.selected_track == 0:
                self.selected_track = track_id

        return handler

    def create_device_handler(self, track_id, function, device_id):
        def handler():
            button = getattr(self, f"BTN{track_id}_{device_id if function == 'STOPPER' else 4}")
            if button.isChecked():
                self.select_device(track_id, function, device_id)
            else:
                self.deselect_device(track_id, function, device_id)
                  
            if self.selected_track == 0:
                self.selected_track = track_id

        return handler

    def create_lock_handler(self, track_id):
        def handler():
            button = getattr(self, f"BTN{track_id}_6")
            # 反转 lock_status
            self.lock_status[track_id] = not self.lock_status[track_id]
            self.track_buttons_lock_display(track_id)
            if self.lock_status[track_id]:
                self.lock_specific_track_buttons(track_id)
            else:
                self.unlock_specific_track_buttons(track_id)

        return handler

    def create_track_reset_handler(self, track_id):
        def handler():
            self.reset_track_fatal_error(track_id)
        return handler


    def select_device(self, track_id, function, device_id):
        """选择单个设备"""
        self.set_device_selection(track_id, function, device_id, True)

        # 取消旧计时器（如果存在）
        self.cancel_device_timer(track_id, function, device_id)

        # 启动新计时器
        timer = QTimer()
        timer.setSingleShot(True)
        
        timer.timeout.connect(lambda: self.auto_deselect_device(track_id, function, device_id))
        timer.start(10000)
        self.selection_timers[(track_id, function, device_id)] = timer
    
    def deselect_device(self, track_id, function, device_id):
        """主动取消设备选择"""
        self.cancel_device_timer(track_id, function, device_id)
        self.set_device_selection(track_id, function, device_id, False)
        # 检查该股道所有设备是否都未被选中
        if not any(
            (track_id, f, d) in self.selected_devices
            for f, ds in [("STOPPER", [1, 2, 3]), ("ANTI_SLIP", [1])]
            for d in ds
        ):
            self.selected_track = 0

    def cancel_device_timer(self, track_id, function, device_id):
        """取消设备计时器"""
        key = (track_id, function, device_id)
        if key in self.selection_timers:
            self.selection_timers[key].stop()
            del self.selection_timers[key]

    def set_device_selection(self, track_id, function, device_id, selected):
        """统一更新设备选择状态"""
        button = getattr(self, f"BTN{track_id}_{device_id if function == 'STOPPER' else 4}")
        button.setChecked(selected)

        # 同步选中集合
        if selected:
            self.selected_devices.add((track_id, function, device_id))
        else:
            self.selected_devices.discard((track_id, function, device_id))

    def auto_deselect_device(self, track_id, function, device_id):
        """自动取消设备选择"""
        self.set_device_selection(track_id, function, device_id, False)
        del self.selection_timers[(track_id, function, device_id)]
        
        # 检查该股道所有设备是否都未被选中
        if not any(
            (track_id, f, d) in self.selected_devices
            for f, ds in [("STOPPER", [1, 2, 3]), ("ANTI_SLIP", [1])]
            for d in ds
        ):
            self.selected_track = 0

    def log(self, message):
        if self.local_role == MachineRole.MASTER:
            self.logger.log_signal.emit(message)

    @pyqtSlot(dict)
    def _update_device_status(self, parsed_data):
        track_id = parsed_data["TRACK"]
        function = parsed_data["FUN"]
        device_id = parsed_data["DEVICE"]

        if track_id not in VALID_TRACKS:
            self.log(f"[警告] 收到非法股道号：{track_id}")
            return

        if function not in VALID_FUNCTIONS:
            self.log(f"[警告] 收到非法设备类型：{function}")
            return

        if device_id not in VALID_DEVICE_IDS.get(function, set()):
            self.log(f"[警告] 收到非法设备编号：{device_id}（功能：{function}）")
            return

        if track_id not in self.track_statuses or \
                function not in self.track_statuses[track_id] or \
                device_id not in self.track_statuses[track_id][function]:
            self.log(f"[警告] 非法设备索引：{track_id}道 {function} 第{device_id}台")
            return

        self.last_report_time[(track_id, function, device_id)] = datetime.datetime.now()

        # 跳过已故障的设备
        if self.command_fault_status.get((track_id, function, device_id), False):
            if parsed_data["FUN"] == "STOPPER":
                self.track_statuses[track_id][function][device_id]["STATE"] = StopperState.STATE_INIT
            elif parsed_data["FUN"] == "ANTI_SLIP":
                self.track_statuses[track_id][function][device_id]["STATE"] = AntiSlipState.STATE_INIT
            return

        if self.track_statuses[track_id][function][device_id]["MODE"] != parsed_data["MODE"]:
            self.track_statuses[track_id][function][device_id]["MODE"] = parsed_data["MODE"]
            if parsed_data["FUN"] == "STOPPER":
                self.log(
                    f"{parsed_data['TRACK']}道"
                    f"第{parsed_data['DEVICE']}台停车器"
                    f"进入{'运行' if parsed_data['MODE'] == 'REMOTE_CONTROL' else '检修'}模式"
                )
            else:
                self.log(
                    f"{parsed_data['TRACK']}道防溜器"
                    f"进入{'运行' if parsed_data['MODE'] == 'REMOTE_CONTROL' else '检修'}模式"
                )

        if self.track_statuses[track_id][function][device_id]["STATE"] != parsed_data["STATE"]:
            self.track_statuses[track_id][function][device_id]["STATE"] = parsed_data["STATE"]
            # 功能是停车器
            if function == "STOPPER":
                state = parsed_data["STATE"]
                if state > StopperState.ERROR_VALVE_FAULT:
                    # 111–141，电磁阀故障位图
                    errors = state - StopperState.ERROR_VALVE_FAULT
                    faulty_valves = []
                    for i in range(5):
                        if errors & (1 << i):
                            faulty_valves.append(str(i + 1))
                    if faulty_valves:
                        self.log(
                            f"{parsed_data['TRACK']}道"
                            f"第{parsed_data['DEVICE']}台停车器"
                            f"第{'、'.join(faulty_valves)}个电磁阀故障"
                        )
                else:
                    # 其他所有状态（包括 100–106 的错误和正常状态 1–4）都能查字典
                    self.log(
                        f"{parsed_data['TRACK']}道"
                        f"第{parsed_data['DEVICE']}台停车器"
                        f"{stopper_state_map.get(state, '未知状态')}"
                    )
                if state >= StopperState.ERROR_VALVE_ANOMALY:
                    self.voice_alert_player.add_alert_to_queue(f"{track_id}道停车器故障")
            # 功能是防溜器
            else:
                self.log(
                    f"{parsed_data['TRACK']}道防溜器"
                    f"{anti_slip_state_map[parsed_data['STATE']]}"
                )
                if parsed_data["STATE"] == AntiSlipState.STATE_PUSH_AWAY:
                    self.voice_alert_player.add_alert_to_queue(f"{track_id}道主铁鞋推走")
                if parsed_data["STATE"] >= AntiSlipState.WARNING_NOT_IN_PLACE:
                    self.voice_alert_player.add_alert_to_queue(f"{track_id}道主铁鞋故障")

        # 额外IO口，未使用
        if self.track_statuses[track_id][function][device_id]["IO_16_9"] != parsed_data["IO_16_9"]:
            self.track_statuses[track_id][function][device_id]["IO_16_9"] = parsed_data["IO_16_9"]

        # 判断副鞋是否走鞋
        if self.track_statuses[track_id][function][device_id]["IO_8_1"] != parsed_data["IO_8_1"]:
            if function == "ANTI_SLIP":
                io_state_low = self.track_statuses[track_id][function][device_id]["IO_8_1"]
                if (io_state_low & 0b00001000) != (parsed_data["IO_8_1"] & 0b00001000):
                    self.log(
                        f"{parsed_data['TRACK']}道防溜器"
                        f"副鞋1{'走鞋' if (parsed_data['IO_8_1'] & 0b00001000) == 0 else '缓解'}"
                    )
                if (io_state_low & 0b00010000) != (parsed_data["IO_8_1"] & 0b00010000):
                    self.log(
                        f"{parsed_data['TRACK']}道防溜器"
                        f"副鞋2{'走鞋' if (parsed_data['IO_8_1'] & 0b00010000) == 0 else '缓解'}"
                    )
                if (parsed_data['IO_8_1'] & 0b00001000) == 0 or (parsed_data['IO_8_1'] & 0b00010000) == 0:
                    self.voice_alert_player.add_alert_to_queue(f"{track_id}道副铁鞋推走")

            self.track_statuses[track_id][function][device_id]["IO_8_1"] = parsed_data["IO_8_1"]

        self.update_device_button(track_id, function, device_id)

    def update_device_button(self, track_id, function, device_id):
        button = getattr(self, f"BTN{track_id}_{device_id if function == 'STOPPER' else 4}")
        state = self.track_statuses[track_id][function][device_id]["STATE"]
        mode = self.track_statuses[track_id][function][device_id]["MODE"]
        active_sam = self.sam_A if self.sam_A_is_master else self.sam_B
        # 检查是否需要封锁：备机状态、离线状态封锁，集控模式封锁，单股道按钮设置为封锁
        if self.local_role == MachineRole.BACKUP or self.local_status == HeartbeatStatus.OFFLINE:
            UNLOCK_STATUS = False
        elif active_sam.my_control_mode == 0x55:
            UNLOCK_STATUS = False
        elif self.lock_status[track_id] == True:
            UNLOCK_STATUS = False
        elif self.selected_track != 0 and self.selected_track != track_id:
            UNLOCK_STATUS = False
        else:
            UNLOCK_STATUS = True

        if self.command_fault_status.get((track_id, function, device_id), False):
            if function == "STOPPER":
                button.setProperty("state", "error")
                button.setCheckable(False)
                button.setEnabled(False)
            elif function == "ANTI_SLIP":
                label = getattr(self, f"label_anti_slip_{track_id}")
                button.setProperty("state", "error")
                button.setCheckable(False)
                button.setEnabled(False)
                label.setProperty("state", "error")
            return
           
        if function == "STOPPER":
            if state > StopperState.ERROR_VALVE_ANOMALY or state == StopperState.STATE_INIT:
                button.setProperty("state", "error")
                button.setCheckable(False)
                button.setEnabled(False)
            elif mode == "LOCAL_CONTROL":
                button.setProperty("state", "maintain")
                button.setCheckable(False)
                button.setEnabled(False)
            elif state == StopperState.STATE_STOP_AT_BRAKE:
                button.setProperty("state", "brake")
                button.setCheckable(True)
                button.setEnabled(UNLOCK_STATUS)
            elif state == StopperState.STATE_STOP_AT_RELEASE:
                button.setProperty("state", "release")
                button.setCheckable(True)
                button.setEnabled(UNLOCK_STATUS)
            button.style().unpolish(button)
            button.style().polish(button)
        else:
            label = getattr(self, f"label_anti_slip_{track_id}")
            io_state_low = self.track_statuses[track_id][function][device_id]["IO_8_1"]
            push_away_deputy1 = (io_state_low & 0b00001000) == 0
            push_away_deputy2 = (io_state_low & 0b00010000) == 0
            if state >= AntiSlipState.WARNING_NOT_IN_PLACE or state in [AntiSlipState.STATE_INIT,
                                                                        AntiSlipState.STATE_PUSH_AWAY] or push_away_deputy1 or push_away_deputy2:
                button.setProperty("state", "error")
                button.setCheckable(False)
                button.setEnabled(False)
                label.setProperty("state", "error")
            elif mode == "LOCAL_CONTROL":
                button.setProperty("state", "maintain")
                button.setCheckable(False)
                button.setEnabled(False)
                label.setProperty("state", "maintain")
            elif state == AntiSlipState.STATE_BRAKING_REMOTE:
                button.setProperty("state", "braking")
                button.setCheckable(False)
                button.setEnabled(False)
                label.setProperty("state", "release")
            elif state == AntiSlipState.STATE_RELEASING_REMOTE:
                button.setProperty("state", "releasing")
                button.setCheckable(False)
                button.setEnabled(False)
                label.setProperty("state", "release")
            elif state == AntiSlipState.STATE_STOP_AT_BRAKE_REMOTE:
                button.setProperty("state", "brake")
                button.setCheckable(True)
                button.setEnabled(UNLOCK_STATUS)
                label.setProperty("state", "release")
            elif state == AntiSlipState.STATE_STOP_AT_RELEASE_REMOTE:
                button.setProperty("state", "release")
                button.setCheckable(True)
                button.setEnabled(UNLOCK_STATUS)
                label.setProperty("state", "release")
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
            label.style().unpolish(label)
            label.style().polish(label)

    @pyqtSlot()
    def show_log_window(self):
        self.logger.show()

    @pyqtSlot()
    def close_log_window(self):
        self.logger.close()

    def update_machine_id(self):
        """更新设备ID"""
        label_server = self.label_serverA if self.machine_id == "A" else self.label_serverB
        label_server.setStyleSheet(
            "background-color: rgb(44, 197, 190);"
            "color: rgb(255, 255, 255);"
            "border: 2px solid gray;"
        )

    def update_hot_standby_status(self, status_data):
        """更新双机热备状态"""

        def set_label_style(label, text, is_online):
            """设置标签样式"""
            color = "rgb(0, 255, 0)" if is_online else "rgb(255, 0, 0)"
            label.setText(text)
            label.setStyleSheet(
                f"font-size: 12;"
                f"font-family: 'Microsoft YaHei';"
                f"font-weight: bold;"
                f"background-color: rgb(0, 0, 0);"
                f"color: {color};"
                f"border: 2px solid gray;"
            )

        if self.local_role != status_data["local_role"]:
            self.local_role = status_data["local_role"]
            #新增与SAM中的主备机状态保持一致，状态改变发送RSR.
            control_mode = self.sam_A.my_control_mode == 0x55
            self.sam_A.set_own_status(my_is_master=(self.local_role == MachineRole.MASTER),
                                      is_central_control=control_mode)
            self.sam_A.post_command_signal.emit("SEND_RSR", {})
            control_mode = self.sam_B.my_control_mode == 0x55
            self.sam_B.set_own_status(my_is_master=(self.local_role == MachineRole.MASTER),
                                      is_central_control=control_mode)
            self.sam_B.post_command_signal.emit("SEND_RSR", {})
            self.log(f"{self.machine_id}机进入{self.local_role.value}状态")

        if self.local_status != status_data["local_status"]:
            self.local_status = status_data["local_status"]
            self.log(f"{self.machine_id}机{self.local_status.value}")

        if self.remote_role != status_data["remote_role"]:
            self.remote_role = status_data["remote_role"]
            self.log(f"{'B' if self.machine_id == 'A' else 'A'}机进入{self.remote_role.value}状态")

        if self.remote_status != status_data["remote_status"]:
            self.remote_status = status_data["remote_status"]
            self.log(f"{'B' if self.machine_id == 'A' else 'A'}机{self.remote_status.value}")

        # # 锁定/解锁按钮
        # if self.local_role == MachineRole.BACKUP or self.local_status == HeartbeatStatus.OFFLINE:
        #     self.lock_all_buttons()

        # 离线状态，心跳信号在线则为False，否则为True
        OFFLINE_STATUS = False if self.remote_status == HeartbeatStatus.ONLINE else True

        if self.machine_id == "A":
            set_label_style(self.label_serverA_state, self.local_role.value, True)
            remote_text = self.remote_status.value if OFFLINE_STATUS else self.remote_role.value
            set_label_style(self.label_serverB_state, remote_text, not OFFLINE_STATUS)
        else:
            remote_text = self.remote_status.value if OFFLINE_STATUS else self.remote_role.value
            set_label_style(self.label_serverA_state, remote_text, not OFFLINE_STATUS)
            set_label_style(self.label_serverB_state, self.local_role.value, True)

    def lock_all_buttons(self):
        """禁用所有按钮"""
        # 禁用 BTN2_1 到 BTN24_5
        for x in range(2, 2 + 23):  # x = 2 到 24
            for i in range(1, 1 + 6):  # i = 1 到 6
                button = getattr(self, f"BTN{x}_{i}")
                button.setEnabled(False)

        # 禁用 BTN_brake 和 BTN_release
        for name in ["BTN_brake", "BTN_release"]:
            button = getattr(self, name)
            button.setEnabled(False)

    def unlock_all_buttons(self):
        """启用所有按钮"""
        # 启用 BTN2_1 到 BTN24_5
        for x in range(2, 2 + 23):  # x = 2 到 24
            for i in range(1, 1 + 6):  # i = 1 到 6
                button = getattr(self, f"BTN{x}_{i}")
                button.setEnabled(True)

        # 启用 BTN_brake 和 BTN_release
        for name in ["BTN_brake", "BTN_release"]:
            button = getattr(self, name)
            button.setEnabled(True)

    def lock_specific_track_buttons(self, track_id):
        """禁用特定股道的按钮"""
        # 禁用特定股道的 BTN{track_id}_1 到 BTN{track_id}_5
        for i in range(1, 1 + 5):  # i = 1 到 5
            button = getattr(self, f"BTN{track_id}_{i}")
            button.setEnabled(False)

    def unlock_specific_track_buttons(self, track_id):
        """启用特定股道的按钮"""
        # 启用特定股道的 BTN{track_id}_1 到 BTN{track_id}_5
        for i in range(1, 1 + 5):  # i = 1 到 5
            button = getattr(self, f"BTN{track_id}_{i}")
            button.setEnabled(True)

    def track_buttons_lock_display(self, track_id):
        button = getattr(self, f"BTN{track_id}_6")
        if self.lock_status[track_id]:
            # 封锁状态：加粗边框，白字“解锁”
            button.setText("解锁")
            button.setStyleSheet(
                "color: white;"
                "border: 3px solid white;"
                "font-weight: bold;"
                "background-color: rgb(242, 150, 37);"
                "border-radius: 8px;"
            )
        else:
            # 解锁状态：正常边框，白字“封锁”
            button.setText("封锁")
            button.setStyleSheet(
                "color: white;"
                "font-weight: bold;"
                "background-color: rgb(242, 150, 37);"
                "border-radius: 8px;"
            )
    
    def closeEvent(self, event):
        """程序退出事件"""
        self.logger.close()
        self.hot_standby.stop_service()

        # 删除窗口资源
        self.logger.window.deleteLater()
        self.logger.deleteLater()

        super().closeEvent(event)

    def mouseMoveEvent(self, event):

        # 鼠标移动时检测是否靠近QFrame

        # 获取QFrame的位置和大小
        frame_geo = self.frame.geometry()

        # 定义一个"靠近"的区域（这里设置为QFrame周围20像素）
        expanded_rect = frame_geo.adjusted(-20, -20, 20, 20)

        # 检查鼠标是否在扩展区域内
        if expanded_rect.contains(event.pos()):
            self.frame.show()
        else:
            self.frame.hide()

        super().mouseMoveEvent(event)

    def eventFilter(self, obj, event):
        """处理QFrame的事件"""
        if obj == self.frame:
            if event.type() == event.Enter:
                self.frame.show()
            elif event.type() == event.Leave:
                self.frame.hide()
        return super().eventFilter(obj, event)