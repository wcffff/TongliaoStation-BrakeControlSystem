import enum
import struct
from collections import deque
from PyQt5.QtCore import pyqtSignal, QTimer, QDateTime, QTime
# 确保tcp_client.py文件位于一个名为modules的文件夹中
# 如果实际路径不同，请在此处修改import语句
from modules.tcp_client import TcpClient
import subprocess

class StopperState(enum.IntEnum):
    STATE_INIT = 1,
    STATE_STOP_AT_BRAKE = 2,
    STATE_STOP_AT_RELEASE = 3,
    STATE_MAINTAIN = 4,
    ERROR_VALVE_ANOMALY = 100,
    ERROR_RELEASE_CONTACT_ERROR_CLOSED = 101
    ERROR_BRAKE_CONTACT_ERROR_OPEN = 102
    ERROR_BRAKE_CONTACT_ERROR_CLOSED = 103
    ERROR_RELEASE_CONTACT_ERROR_OPEN = 104
    ERROR_CONTACTS_BOTH_CLOSED = 105
    ERROR_CONTACTS_BOTH_OPEN = 106
    ERROR_VALVE_FAULT = 111  # 111–141 电磁阀故障范围起点RELEASE_CONTACT_ERROR_CLOSED = 101

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
    ERROR_NOT_UNIFIED_BRAKE = 121

class SamFrameType(enum.IntEnum):
    """协议帧类型枚举"""
    DC2 = 0x12
    DC3 = 0x13
    ACK = 0x06
    NACK = 0x15
    SDI = 0x85
    BCC = 0x95
    TSQ = 0x9a
    TSD = 0xa5
    ACQ = 0x75
    ACA = 0x7a
    RSR = 0xaa


class SamTcpClient(TcpClient):
    """
    负责与SAM系统进行TCP通信的客户端。
    实现了带ACK/NACK确认、超时重传和网络复位的可靠传输机制。
    采用统一的信号和命令接口。
    """
    # --- 统一的事件接收信号 (出口) ---
    sam_event = pyqtSignal(dict)

    # --- 统一的命令发送信号 (入口) ---
    post_command_signal = pyqtSignal(str, dict)

    control_mode_signal = pyqtSignal(int)

    # --- 协议常量 ---
    RETRANSMISSION_TIMEOUT = 2500
    MAX_RETRIES = 2
    MAX_CONSECUTIVE_CRC_ERRORS = 5
    ACA_RESPONSE_TIMEOUT = 5000

    def __init__(self, host: str, port: int):
        super().__init__(host, port)

        self._buffer = bytearray()
        self.data_received.connect(self._on_sam_data_received)
        self.socket.connected.connect(lambda: self.on_connection_status_changed(True))
        self.socket.disconnected.connect(lambda: self.on_connection_status_changed(False))
        self.post_command_signal.connect(self._queue_command)

        # --- 状态和序号变量 ---
        self.handshake_complete = False
        self.send_sequence = 0
        self.ack_sequence = 0
        self.my_master_backup_status = 0x55
        self.my_control_mode = 0xaa

        # --- 指令队列 ---
        self._command_queue = deque()

        # --- 用于可靠传输的变量 ---
        self._in_flight_frame = None
        self._retry_count = 0
        self._consecutive_crc_errors = 0
        self.sdi_data_callback = None

        self._retransmission_timer = QTimer(self)
        self._retransmission_timer.setSingleShot(True)
        self._retransmission_timer.timeout.connect(self._on_retransmission_timeout)

        # --- 用于ACQ/ACA流程的变量 ---
        self._is_waiting_for_aca = False
        self._aca_timeout_timer = QTimer(self)
        self._aca_timeout_timer.setSingleShot(True)
        self._aca_timeout_timer.timeout.connect(self._on_aca_timeout)

        # --- 用于TSQ/TSD流程的变量 ---
        self._daily_tsq_timer = QTimer(self)
        self._daily_tsq_timer.setSingleShot(True)
        self._daily_tsq_timer.timeout.connect(self._on_daily_tsq_trigger)

        # 周期性报告定时器
        self.set_sdi_data_callback(self.build_sdi_data)
        self._waiting_ack_for_sdi = False

        #建立连接标志位
        self.connection_established = False

        #建立插队机制：ACQ和TSQ发送标志位
        self.tsq_pending = False
        self.acq_pending = False
        self.rsr_pending = False

        print(f"SamTcpClient: Initialized as CLIENT for SAM Server at {host}:{port}.")

    def set_control_mode(self, mode):
        if self.my_control_mode != mode:
            self.my_control_mode = mode
            self.control_mode_signal.emit(mode)

    def set_own_status(self, is_master: bool, is_central_control: bool):
        self.my_master_backup_status = 0x55 if is_master else 0xaa
        self.set_control_mode(0x55) if is_central_control else self.set_control_mode(0xaa)

    def build_sdi_data(self, track_statuses: dict, lock_status: dict) -> bytes:
        """
        构建SDI数据帧内容。
        :param track_statuses: 股道状态字典，格式为 {track_id: {device_type: {state: value}}}
        :return: 构建好的SDI数据内容尝试发送SDI
        """
        from struct import pack
        def encode_stopper_data(stoppers: dict) -> int:
            IS_MAINTAIN = any(stopper.get("STATE") == StopperState.STATE_MAINTAIN for stopper in stoppers.values())
            bytes = 0b10000000 if IS_MAINTAIN else 0b00000000

            def state_translator(state):
                # state 2: 制动, 3: 缓解, 4：检修，其他：故障
                if state == 2:
                    return 0b01
                elif state == 3:
                    return 0b10
                else:
                    return 0b11

            dev1_state = state_translator(stoppers.get(1, {}).get("STATE", 1))
            dev2_state = state_translator(stoppers.get(2, {}).get("STATE", 1))
            dev3_state = state_translator(stoppers.get(3, {}).get("STATE", 1))
            bytes = bytes | (dev1_state << 4) | (dev2_state << 2) | dev3_state
            return bytes

        def encode_antislip_data(anti_slips: dict, lock_state: int) -> int:
            IS_MAINTAIN = any(
                anti_slip.get("STATE") in (
                    AntiSlipState.STATE_BRAKING_LOCAL,
                    AntiSlipState.STATE_RELEASING_LOCAL,
                    AntiSlipState.STATE_STOP_LOCAL
                )
                for anti_slip in anti_slips.values())
            bytes = 0b10000000 if IS_MAINTAIN else 0b00000000

            io_state_low = anti_slips[1]["IO_8_1"]
            dev_state = anti_slips[1]["STATE"]
            push_away_deputy1 = (io_state_low & 0b00001000) == 0
            push_away_deputy2 = (io_state_low & 0b00010000) == 0

            if dev_state >= AntiSlipState.WARNING_NOT_IN_PLACE or dev_state == AntiSlipState.STATE_INIT:
                bytes = bytes | 0b00011111
            else:
                second_shoe_state = 0b10 if (push_away_deputy1 or push_away_deputy2) else 0b01
                if dev_state in [AntiSlipState.STATE_BRAKING_REMOTE, AntiSlipState.STATE_STOP_AT_BRAKE_REMOTE]:
                    main_shoe_state = 0b100
                elif dev_state in [AntiSlipState.STATE_RELEASING_REMOTE, AntiSlipState.STATE_STOP_AT_RELEASE_REMOTE]:
                    main_shoe_state = 0b010
                elif dev_state == AntiSlipState.STATE_PUSH_AWAY:
                    main_shoe_state = 0b001
                else:
                    main_shoe_state = 0b111
                bytes = bytes | (second_shoe_state << 3) | main_shoe_state
                
            # 锁定状态
            if lock_state == True:
                bytes |= 0b01000000
            
            return bytes

        sdi_payload = bytearray()
        sorted_tracks = sorted(track_statuses.keys())
        for track_id in sorted_tracks:
            devs = track_statuses[track_id]
            slip_byte = encode_antislip_data(devs.get("ANTI_SLIP", {}), lock_status.get(track_id, 0))
            stopper_byte = encode_stopper_data(devs.get("STOPPER", {}))
            sdi_payload.extend([slip_byte, stopper_byte])

        total_len = len(sorted_tracks) * 2 + 2
        result = bytearray()
        result.extend(pack('<H', total_len))  # 长度字段，小端

        # 场控状态字段（低位在前）
        if self.my_control_mode == 0x55:
            result.extend([0x01, 0x00])  # 集中控制
        else:
            result.extend([0x00, 0x00])  # 场控

        result.extend(sdi_payload)
        return bytes(result)


    def set_sdi_data_callback(self, callback):
        """设置一个回调函数，用于在需要时获取SDI帧的数据内容。"""
        if callable(callback):
            self.sdi_data_callback = callback
            print("  [Callback] SDI data callback has been set.")
        else:
            print("  [Error] Provided SDI data callback is not callable.")

    def _queue_command(self, command: str, data: dict = None):
        if command == "REQUEST_CENTRAL_CONTROL":
            self.acq_pending = True
            print("[队列] 设置 acq_pending = True")
            self._process_command_queue()
            return

        if command == "SEND_RSR":
            if not self.handshake_complete:
                print("[RSR] 忽略发送：尚未建立连接。")
                return
            self.rsr_pending = True
            print("[队列] 设置 rsr_pending = True")
            self._process_command_queue()
            return

        if command == "REQUEST_TIME_SYNC":
            self.tsq_pending = True
            print("[队列] 设置 tsq_pending = True")
            self._process_command_queue()
            return

        # 普通命令去重后排队
        if any(cmd == command for cmd, _ in self._command_queue):
            print(f"[队列] 跳过重复命令 {command}")
            return

        self._command_queue.append((command, data))
        self._process_command_queue()

    def _process_command_queue(self):
        if self._in_flight_frame is not None:
            return

        # 优先执行 acq_pending
        if self.acq_pending:
            print("[调度] 发现 acq_pending 为 True，立即发送 ACQ 指令")
            self._handle_acq_request()
            self.acq_pending = False
            return

        # 其次执行 rsr_pending
        if self.rsr_pending:
            print("[调度] 发现 rsr_pending 为 True，立即发送 RSR 指令")
            self._handle_rsr_request()
            self.rsr_pending = False
            return

        # 最后执行 tsq_pending
        if self.tsq_pending:
            print("[调度] 发现 tsq_pending 为 True，立即发送 TSQ 指令")
            self._handle_tsq_request()
            self.tsq_pending = False
            return

        if not self._command_queue:
            return

        command, data = self._command_queue.popleft()
        self._execute_command(command, data)

    def _execute_command(self, command: str, data: dict = None):
        """实际执行指令的内部方法"""
        if command == 'REQUEST_CENTRAL_CONTROL':
            self._handle_acq_request()
        elif command == 'REQUEST_TIME_SYNC':
            self._handle_tsq_request()
        elif command == "SEND_RSR":
            self._handle_rsr_request()

        elif command == 'SEND_SDI':
            if self.sdi_data_callback:
                sdi_data_content = self.sdi_data_callback(data)
                print("尝试发送SDI")
                if isinstance(sdi_data_content, bytes):
                    self._send_data_frame(SamFrameType.SDI, sdi_data_content)
                else:
                    print("  [Error] SDI data callback did not return bytes.")
                    self._process_command_queue()
            else:
                print("  [Warning] SDI data callback not set. Cannot send SDI.")
                self._process_command_queue()
        else:
            print(f"  [Warning] Unknown command '{command}' executed.")

    def on_connection_status_changed(self, is_connected: bool):
        if is_connected:
            self.sam_event.emit({'type': 'connection', 'data': {'status': 'connected'}})
        else:
            self._reset_protocol_layer()

    def _reset_protocol_layer(self):
        was_connected = self.handshake_complete
        self.connection_established = False
        self.handshake_complete = False
        self.send_sequence = 0
        self.ack_sequence = 0
        self._retransmission_timer.stop()
        self._aca_timeout_timer.stop()
        self._daily_tsq_timer.stop()
        self._in_flight_frame = None
        self._is_waiting_for_aca = False
        self._retry_count = 0
        self._consecutive_crc_errors = 0
        self._command_queue.clear()
        if was_connected:
            self.sam_event.emit({'type': 'connection', 'data': {'status': 'lost'}})

    def _on_sam_data_received(self, data: bytes):
        self._buffer.extend(data)
        while True:
            start_index = self._buffer.find(0x7D)
            if start_index == -1: return
            if start_index > 0: self._buffer = self._buffer[start_index:]
            end_index = self._buffer.find(0x7E, 1)
            if end_index == -1: return
            raw_frame_with_escape = self._buffer[:end_index + 1]
            self._buffer = self._buffer[end_index + 1:]
            self._process_frame(raw_frame_with_escape)

    def _process_frame(self, raw_frame_with_escape: bytes):
        try:
            payload_with_escape = raw_frame_with_escape[1:-1]
            unescaped_payload = self._deescape_payload(payload_with_escape)
            data_to_check = unescaped_payload[:-2]
            received_crc = struct.unpack('<H', unescaped_payload[-2:])[0]
            calculated_crc = self._calculate_crc(data_to_check)
            if received_crc != calculated_crc:
                self._consecutive_crc_errors += 1
                if self._consecutive_crc_errors >= self.MAX_CONSECUTIVE_CRC_ERRORS:
                    self._reset_protocol_layer()
                else:
                    self._send_nack_frame()
                return
            self._consecutive_crc_errors = 0
            self._parse_and_dispatch(data_to_check)
        except Exception as e:
            print(f"  [Error] Frame processing failed: {e}")

    def _parse_and_dispatch(self, payload: bytearray):
        send_seq, ack_seq, frame_type_val = payload[2], payload[3], payload[4]
        try:
            frame_type = SamFrameType(frame_type_val)

            if self.handshake_complete and frame_type not in [SamFrameType.DC2, SamFrameType.DC3]:
                # 丢帧检查
                if self.ack_sequence != 0 and send_seq != self.ack_sequence and send_seq >= self.ack_sequence + 2:
                    print(
                        f"  [Error] 帧丢失! 期望序号: {self.ack_sequence + 1}, 收到序号: {send_seq}. 正在重新初始化通讯...")
                    self._reset_protocol_layer()
                    return

                self.ack_sequence = send_seq

            handler_map = {
                SamFrameType.DC2: lambda: self._handle_dc2(send_seq, ack_seq),
                SamFrameType.DC3: self._handle_dc3,
                SamFrameType.ACK: lambda: self._handle_ack(ack_seq, send_seq),
                SamFrameType.NACK: self._handle_nack,
                SamFrameType.RSR: lambda: self._handle_rsr(payload, send_seq),
                SamFrameType.ACA: lambda: self._handle_aca(payload),
                SamFrameType.TSD: lambda: self._handle_tsd(payload),
                SamFrameType.BCC: lambda: self._handle_bcc(payload),
            }
            if handler := handler_map.get(frame_type):
                handler()
            else:
                self.sam_event.emit({'type': f'unhandled_{frame_type.name.lower()}', 'data': payload[7:]})
        except Exception as e:
            print(f"  [Error] Dispatching failed: {e}")

    def _send_data_frame(self, frame_type: SamFrameType, data_content: bytes = b''):
        frame_to_send = self._build_frame(frame_type, data_content, self.send_sequence, self.ack_sequence)
        self._in_flight_frame = {"frame_bytes": frame_to_send, "send_seq": self.send_sequence, "type": frame_type}
        self._retry_count = 0
        super().send_data(frame_to_send)
        self._retransmission_timer.start(self.RETRANSMISSION_TIMEOUT)

    def _send_nack_frame(self):
        frame_to_send = self._build_frame(SamFrameType.NACK, b'', self.send_sequence, self.ack_sequence)
        super().send_data(frame_to_send)

    def _handle_dc2(self, send_seq: int, ack_seq: int):
        if send_seq == 0 and ack_seq == 0:
            self._reset_protocol_layer()
            self._send_dc3_frame()

    def _send_dc3_frame(self):
        frame_to_send = self._build_frame(SamFrameType.DC3, b'', 0, 0)
        super().send_data(frame_to_send)
        self.handshake_complete = True
        self.send_sequence = 1
        self.ack_sequence = 0
        self.sam_event.emit({'type': 'handshake', 'data': {'status': 'success'}})
        self._schedule_daily_tsq()

    def _handle_dc3(self):
        pass

    def _send_ack(self):
        frame = self._build_frame(SamFrameType.ACK, b'', self.send_sequence, self.ack_sequence)
        super().send_data(frame)

    def _handle_ack(self, received_ack_seq: int, received_send_seq: int):
        # 建立连接（仅第一次收到ACK时）
        if not self.connection_established:
            self.connection_established = True
            self._in_flight_frame = None
            self.ack_sequence = received_send_seq
            self.send_sequence = (self.send_sequence % 255) + 1 if self.send_sequence != 0 else 1
            print(f"[Handshake] 已成功建立连接！ACK序号={received_ack_seq}，设置发送序号={self.send_sequence}")
            self._queue_command('REQUEST_TIME_SYNC')
        else:
            # 已连接：判断是否可以发送SDI
            self._in_flight_frame = None
            if not (self.rsr_pending or self.acq_pending or self.tsq_pending):
                print("[ACK] 已连接，且无高优先任务，尝试发送SDI")
                self._queue_command('SEND_SDI')
            else:
                print("[ACK] 当前存在高优先任务（RSR/ACQ/TSQ），跳过SDI发送")

        self._process_command_queue()

    def _handle_nack(self):
        if self._in_flight_frame:
            self._retransmission_timer.stop()
            self._on_retransmission_timeout(is_nack=True)

    def _handle_rsr_request(self):

        rsr_data = bytes([self.my_master_backup_status, self.my_control_mode])
        self._send_data_frame(SamFrameType.RSR, rsr_data)
        print(f"[RSR] 已主动发送 RSR 帧: {rsr_data.hex()}")

    def _handle_rsr(self, payload: bytes, received_send_seq: int):
        data_content = payload[7:]
        if len(data_content) != 2:
            print("  [RSR] 数据长度错误，忽略。")
            return

        sam_mb, sam_ac = data_content[0], data_content[1]
        status_dict = {
            'sam_master_backup': sam_mb,
            'sam_allow_central_control': sam_ac
        }
        self.sam_event.emit({'type': 'rsr', 'data': status_dict})

        if not self.connection_established:
            # 未连接：直接回 RSR
            self._queue_command('SEND_RSR')
        else:
            # 已连接：更新序号 + 发送 SDI
            self._in_flight_frame = None
            self.ack_sequence = received_send_seq
            self.send_sequence = (self.send_sequence % 255) + 1 if self.send_sequence != 0 else 1
            if not (self.rsr_pending or self.acq_pending or self.tsq_pending):
                print("[RSR] 已连接，且无高优先任务，尝试发送SDI")
                self._queue_command('SEND_SDI')
            else:
                print("[RSR] 当前存在高优先任务（RSR/ACQ/TSQ），跳过SDI发送")

        self._process_command_queue()

    def _handle_bcc(self, payload: bytes):
        """新增：处理并解析BCC指令"""
        print("  -> Handling BCC (Button and Control Command)...")
        data_content = payload[7:]
        if not data_content:
            print("  [Error] BCC frame has no data content.")
            return

        command_type = data_content[0]
        track_numbers = list(data_content[1:])  # 将剩余字节转换为股道号列表

        bcc_data = {
            'command_type': command_type,
            'tracks': track_numbers
        }

        self.sam_event.emit({'type': 'bcc', 'data': bcc_data})
        print(f"  [BCC Received] Parsed command: {bcc_data}")
        # BCC作为数据帧，其接收也应该触发一次SDI捎带确认，通过队列处理即可
        if not (self.rsr_pending or self.acq_pending or self.tsq_pending):
            print("[BCC] 无高优先任务，发送SDI")
            self._queue_command('SEND_SDI')
        else:
            print("[BCC] 当前存在高优先任务（RSR/ACQ/TSQ），跳过SDI发送")

        self._process_command_queue()

    def _handle_acq_request(self):
        self._send_data_frame(SamFrameType.ACQ, b'')
        self._is_waiting_for_aca = True
        # self.acq_pending = False
        self._aca_timeout_timer.start(self.ACA_RESPONSE_TIMEOUT)

    def _handle_aca(self, payload: bytes):
        if not (self._is_waiting_for_aca and self._in_flight_frame and self._in_flight_frame[
            'type'] == SamFrameType.ACQ):
            return

        self._aca_timeout_timer.stop()
        self._retransmission_timer.stop()
        self._in_flight_frame = None
        self._is_waiting_for_aca = False
        received_send_seq = payload[2]
        self.ack_sequence = received_send_seq
        self.send_sequence = (self.send_sequence % 255) + 1 if self.send_sequence != 0 else 1

        data_content = payload[7:]
        if len(data_content) == 1:
            code = data_content[0]
            if code == 0x55:
                self.set_control_mode(0x55)
                self.sam_event.emit({'type': 'aca', 'data': {'success': True, 'message': '切换到集中控制模式成功'}})
            else:
                self.sam_event.emit({'type': 'aca', 'data': {'success': False, 'message': '请求被拒绝'}})
        else:
            self.sam_event.emit({'type': 'aca', 'data': {'success': False, 'message': 'ACA帧格式错误'}})

        if not (self.rsr_pending or self.acq_pending or self.tsq_pending):
            print("[ACA] 已连接，且无高优先任务，尝试发送SDI")
            self._queue_command('SEND_SDI')
        else:
            print("[ACA] 当前存在高优先任务（RSR/ACQ/TSQ），跳过SDI发送")

        self._process_command_queue()

    def _handle_tsq_request(self):
        self._send_data_frame(SamFrameType.TSQ, b'')

    def _bcd_to_int(self, bcd_byte: int) -> int:
        return ((bcd_byte & 0xF0) >> 4) * 10 + (bcd_byte & 0x0F)

    def _handle_tsd(self, payload: bytes):
        if not (self._in_flight_frame and self._in_flight_frame['type'] == SamFrameType.TSQ):
            return

        self._retransmission_timer.stop()
        self._in_flight_frame = None
        received_send_seq = payload[2]
        self.ack_sequence = received_send_seq
        self.send_sequence = (self.send_sequence % 255) + 1 if self.send_sequence != 0 else 1

        data_content = payload[7:]
        if len(data_content) == 7:
            try:
                year_century = self._bcd_to_int(data_content[0])
                year_decade = self._bcd_to_int(data_content[1])
                year = year_century * 100 + year_decade
                month, day, hour, minute, second = map(self._bcd_to_int, data_content[2:])
                time_data = {
                    'year': year, 'month': month, 'day': day,
                    'hour': hour, 'minute': minute, 'second': second
                }
                self.sam_event.emit({'type': 'time_data', 'data': time_data})

            except Exception as e:
                print(f"  [Error] Parsing TSD data failed: {e}")

            if not (self.rsr_pending or self.acq_pending or self.tsq_pending):
                print("[TSD] 已连接，且无高优先任务，尝试发送SDI")
                self._queue_command('SEND_SDI')
            else:
                print("[TSD] 当前存在高优先任务（RSR/ACQ/TSQ），跳过SDI发送")

        self._process_command_queue()

    def _on_retransmission_timeout(self, is_nack=False):
        if not self._in_flight_frame: return
        if not is_nack: self._retry_count += 1
        if self._retry_count > self.MAX_RETRIES:
            self._in_flight_frame = None
            self._reset_protocol_layer()
            self._process_command_queue()
            return
        super().send_data(self._in_flight_frame['frame_bytes'])
        self._retransmission_timer.start(self.RETRANSMISSION_TIMEOUT)

    def _on_aca_timeout(self):
        if not self._is_waiting_for_aca: return
        self._is_waiting_for_aca = False
        self._in_flight_frame = None
        self._process_command_queue()

    def _schedule_daily_tsq(self):
        now = QDateTime.currentDateTime()
        target_time = QTime(18, 0, 0)
        next_sync_dt = QDateTime(now.date(), target_time)
        if now.time() >= target_time:
            next_sync_dt = next_sync_dt.addDays(1)
        msecs_to_next_sync = now.msecsTo(next_sync_dt)
        self._daily_tsq_timer.start(msecs_to_next_sync)

    def _on_daily_tsq_trigger(self):
        self._queue_command('REQUEST_TIME_SYNC')
        self._schedule_daily_tsq()

    def _calculate_crc(self, data: bytes) -> int:
        crc, poly = 0x0000, 0x1021
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if (crc & 0x8000):
                    crc = (crc << 1) ^ poly
                else:
                    crc <<= 1
            crc &= 0xFFFF
        return crc

    def _deescape_payload(self, payload_with_escape: bytes) -> bytearray:
        data, i = bytearray(), 0
        while i < len(payload_with_escape):
            if payload_with_escape[i] == 0x7F:
                i += 1
                if i >= len(payload_with_escape): raise ValueError("Invalid escape sequence")
                if payload_with_escape[i] == 0xFD:
                    data.append(0x7D)
                elif payload_with_escape[i] == 0xFE:
                    data.append(0x7E)
                elif payload_with_escape[i] == 0xFF:
                    data.append(0x7F)
                else:
                    raise ValueError("Invalid escape sequence")
            else:
                data.append(payload_with_escape[i])
            i += 1
        return data

    def _build_frame(self, frame_type: SamFrameType, data_content: bytes, send_seq: int, ack_seq: int) -> bytes:
        is_data_frame = frame_type.value >= 0x20 and frame_type.value != 0x85
        header_content = struct.pack('BBBB', 0x10, send_seq, ack_seq, frame_type.value)
        crc_data = bytearray([0x04]) + header_content
        if is_data_frame: crc_data.extend(struct.pack('<H', len(data_content)))
        crc_data.extend(data_content)
        crc = self._calculate_crc(crc_data)
        unescaped_payload = crc_data + struct.pack('<H', crc)
        escaped_frame = bytearray([0x7D])
        for byte_val in unescaped_payload:
            if byte_val == 0x7D:
                escaped_frame.extend(b'\x7F\xFD')
            elif byte_val == 0x7E:
                escaped_frame.extend(b'\x7F\xFE')
            elif byte_val == 0x7F:
                escaped_frame.extend(b'\x7F\xFF')
            else:
                escaped_frame.append(byte_val)
        escaped_frame.append(0x7E)
        return bytes(escaped_frame)
