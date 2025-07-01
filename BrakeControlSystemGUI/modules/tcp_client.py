import enum
from PyQt5.QtCore import pyqtSignal, QObject, QTimer
from PyQt5.QtNetwork import QAbstractSocket, QTcpSocket


# --- 枚举定义 (保持与协议一致) ---
class CommunicationDirection(enum.IntEnum):
    UPLINK = 0b01  # 下位机 -> 上位机
    DOWNLINK = 0b10  # 上位机 -> 下位机


class FunctionSelection(enum.IntEnum):
    STOPPER = 0b01  # 停车器
    ANTI_SLIP = 0b10  # 防溜器
    ALL_TYPES = 0b00  # 全选两种类型的设备 (主要用于下行命令)


class RunningMode(enum.IntEnum):
    LOCAL_CONTROL = 0b01  # 现场控制 (主要用于上行)
    REMOTE_CONTROL = 0b10  # 远程控制 (上下行皆有)


class Command(enum.IntEnum):
    QUERY = 0x01  # 查询
    BRAKE = 0x02  # 制动
    RELEASE = 0x03  # 缓解


# 解析状态枚举
class ParsingState(enum.Enum):
    WAIT_HEADER = 0
    RECEIVING_BODY = 1


# --- TcpClient 父类 ---
class TcpClient(QObject):
    # 接收信号：当从TCP服务器接收到原始数据时，通过此信号发出
    data_received = pyqtSignal(bytes)

    # 发送信号：外部将要发送的数据（bytes类型）发送到此信号，即可触发数据发送
    _send_data_request = pyqtSignal(bytes)  # 私有命名，表示其内部使用目的

    def __init__(self, host: str, port: int):
        super().__init__()
        self._host = host
        self._port = port
        self.socket = QTcpSocket()

        self._reconnect_interval = 3000  # 重连间隔3秒 (可配置)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._attempt_reconnect)

        # 连接TCP Socket的内部信号到私有槽
        self.socket.connected.connect(self._on_connected)
        self.socket.disconnected.connect(self._on_disconnected)
        self.socket.errorOccurred.connect(self._on_socket_error)
        self.socket.readyRead.connect(self._on_ready_read)

        # 连接外部发送请求信号到内部发送槽
        self._send_data_request.connect(self._do_send_data)

        # 启动连接，使类实例化后即自动运行
        self._connect_to_server()
        print(f"TcpClient: Initializing for {self._host}:{self._port}. Auto-connecting...")

    # --- 内部连接/重连管理 ---
    def _connect_to_server(self):
        """尝试建立与服务器的连接。"""
        if self.socket.state() == QAbstractSocket.UnconnectedState:
            print(f"TcpClient: Attempting to connect to {self._host}:{self._port}...")
            self.socket.connectToHost(self._host, self._port)
        elif self.socket.state() == QAbstractSocket.ConnectingState:
            print(f"TcpClient: Already connecting to {self._host}:{self._port}...")
        # else: 连接中或已连接，不做任何操作

    def _on_connected(self):
        """处理连接成功事件。"""
        print(f"TcpClient: Successfully connected to {self._host}:{self._port}")
        self._reconnect_timer.stop()  # 连接成功，停止重连定时器

    def _on_disconnected(self):
        """处理断开连接事件。"""
        print(f"TcpClient: Disconnected from {self._host}:{self._port}. Scheduling reconnect...")
        self._schedule_reconnect()

    def _on_socket_error(self, error):
        """处理 socket 错误。"""
        if error == QAbstractSocket.RemoteHostClosedError:
            # RemoteHostClosedError 通常会伴随 disconnected 信号，避免重复处理
            return

        error_str = self.socket.errorString()
        print(f"TcpClient: Socket error from {self._host}:{self._port}: {error_str} ({error})")
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        """调度重连尝试。"""
        if not self._reconnect_timer.isActive():
            print(f"TcpClient: Reconnecting in {self._reconnect_interval / 1000} seconds...")
            self._reconnect_timer.start(self._reconnect_interval)

    def _attempt_reconnect(self):
        """由定时器触发的重连尝试。"""
        self._connect_to_server()

    # --- 数据发送 (内部槽) ---
    def _do_send_data(self, data: bytes):
        """
        实际执行数据发送的内部槽函数。
        外部通过 emit self._send_data_request(data) 来调用此方法。
        """
        if self.socket.state() == QAbstractSocket.ConnectedState:
            bytes_written = self.socket.write(data)
            if bytes_written < 0:
                print(f"TcpClient: Error writing data: {self.socket.errorString()}")
            else:
                print(f"TcpClient: Sent {bytes_written} bytes: {data.hex().upper()}")
                # 检查是否完全写入，虽然write()通常会全部写入，但在某些情况下可能不会
                if bytes_written != len(data):
                    print(
                        f"TcpClient: Warning: Only {bytes_written}/{len(data)} bytes written for {data.hex().upper()}")
        else:
            print(f"TcpClient: Failed to send data, not connected. Data: {data.hex().upper()}")

    # --- 数据接收 (内部槽) ---
    def _on_ready_read(self):
        """当 socket 有数据可读时调用，读取并发出原始数据。"""
        while self.socket.bytesAvailable():
            data = self.socket.readAll().data()
            if data:
                print(f"TcpClient: Received {len(data)} bytes: {data.hex().upper()}")
                self.data_received.emit(data)  # 通过公共信号发出接收到的原始数据

    # --- 外部接口 ---
    def send_data(self, data: bytes):
        """
        公共方法：外部调用此方法将数据（bytes）发送给服务器。
        内部会发出 _send_data_request 信号，由内部槽处理。
        """
        self._send_data_request.emit(data)

    def shutdown(self):
        """
        显式关闭客户端并停止重连，用于程序退出时。
        """
        print(f"TcpClient: Shutting down client for {self._host}:{self._port}...")
        self._reconnect_timer.stop()
        if self.socket.state() != QAbstractSocket.UnconnectedState:
            self.socket.disconnectFromHost()
            # self.socket.waitForDisconnected(1000) # 避免阻塞UI线程，通常不需要强制等待
        self.socket.close()
        # 清理信号连接，避免在对象被删除后信号仍然连接到可能已无效的槽
        try:
            self.socket.connected.disconnect(self._on_connected)
            self.socket.disconnected.disconnect(self._on_disconnected)
            self.socket.errorOccurred.disconnect(self._on_socket_error)
            self.socket.readyRead.disconnect(self._on_ready_read)
            self._send_data_request.disconnect(self._do_send_data)
        except TypeError:  # 信号可能已经断开
            pass


# --- DownlinkTcpClient 子类 (与下位机通信) ---
class DownlinkTcpClient(TcpClient):
    # 3. 接收信号：当解析出下位机上传的有效协议数据时，通过此信号发出解析后的字典
    parsed_uplink_packet = pyqtSignal(dict)

    # 4. 发送信号：当需要向tcp server发送数据时，将这个数据发送到这个signal即可实现，传入signal的数据是一个按通信协议组织的dict
    send_downlink_command = pyqtSignal(dict)

    UPLINK_PACKET_LENGTH = 8  # 下位机→上位机协议包长度
    DOWNLINK_PACKET_LENGTH = 8  # 上位机→下位机协议包长度

    def __init__(self, host: str, port: int):
        # 1. 创建类时传入ip和port；2. 外部使用时，创建好这个子类后，类中的功能即自动运行
        super().__init__(host, port)  # 调用父类构造函数，自动开始连接和重连

        # 初始化解析状态机变量
        self.current_packet_buffer = bytearray()
        self.parsing_state = ParsingState.WAIT_HEADER
        self.expected_uplink_length = self.UPLINK_PACKET_LENGTH  # 期望上行数据包长度

        # 连接父类的原始数据接收信号到子类的解析槽
        # 6. 解析数据时要求以状态机的形式实现，每次传入一个byte解析
        self.data_received.connect(self._parse_incoming_data_by_byte)

        # 连接子类的发送命令信号到内部封装和发送槽
        self.send_downlink_command.connect(self._construct_and_send_downlink_packet)

        print(f"DownlinkTcpClient: Initialized for {host}:{port}.")

    def _parse_incoming_data_by_byte(self, raw_data: bytes):
        """
        处理父类发出的原始字节数据，进行逐字节解析。
        由于父类 emit 的 data_received 信号每次可能包含多个字节，
        这里需要循环处理每个字节。
        """
        for byte_val in raw_data:  # 迭代每个字节
            byte = byte_val

            if self.parsing_state == ParsingState.WAIT_HEADER:
                # 期望 0xAA 作为帧头
                if byte == 0xAA:
                    self.current_packet_buffer.append(byte)
                    self.parsing_state = ParsingState.RECEIVING_BODY
                    print(
                        f"Parser: Header 0xAA found. Switching to RECEIVING_BODY. Buffer: {self.current_packet_buffer.hex().upper()}")
                else:
                    # 6. 当接收到错误的byte时，回到状态机初始状态，等待新的一帧数据
                    # 丢弃非帧头字节，并保持在 WAIT_HEADER 状态，或者如果缓冲区有内容，清空
                    if len(self.current_packet_buffer) > 0:
                        print(
                            f"Parser: Discarding non-header byte {byte:02X}. Buffer was {self.current_packet_buffer.hex().upper()}. Resetting.")
                        self.reset_parser_state()  # 严格来说，如果缓冲区已有内容，应该清空并重置
                    else:
                        print(f"Parser: Discarding non-header byte {byte:02X} in WAIT_HEADER state (expected 0xAA).")
                    # 不需要额外重置，因为我们没有进入 RECEIVING_BODY 状态

            elif self.parsing_state == ParsingState.RECEIVING_BODY:
                self.current_packet_buffer.append(byte)

                # 检查是否已接收到完整包长度
                if len(self.current_packet_buffer) == self.expected_uplink_length:
                    if self._validate_and_parse_uplink_packet():
                        print(f"Parser: Valid uplink packet parsed: {self.current_packet_buffer.hex().upper()}")
                    else:
                        # 验证失败时也打印完整缓冲区，并重置
                        print(
                            f"Parser: Invalid uplink packet detected. Resetting parser. Buffer: {self.current_packet_buffer.hex().upper()}")
                    self.reset_parser_state()  # 无论成功失败，都重置状态机，准备接收下一帧
                elif len(self.current_packet_buffer) > self.expected_uplink_length:
                    # 缓冲区溢出，说明可能接收到了错误的包或多个字节粘连
                    print(
                        f"Parser: Buffer overflow ({len(self.current_packet_buffer)} bytes) in RECEIVING_BODY. Expected {self.expected_uplink_length}. Resetting parser. Buffer: {self.current_packet_buffer.hex().upper()}")
                    self.reset_parser_state()  # 发生错误，重置状态机
                else:
                    print(
                        f"Parser: Receiving body. Current length: {len(self.current_packet_buffer)}/{self.expected_uplink_length}. Buffer: {self.current_packet_buffer.hex().upper()}")

    def reset_parser_state(self):
        """重置解析状态机到初始状态。"""
        self.current_packet_buffer = bytearray()
        self.parsing_state = ParsingState.WAIT_HEADER
        print("Parser: State reset to WAIT_HEADER.")

    def _validate_and_parse_uplink_packet(self) -> bool:
        """
        验证接收到的上行数据包并解析其字段。
        如果有效则返回 True，否则返回 False。
        协议参考：通信协议.pdf 中“下位机→上位机”表格和描述
        """
        packet = self.current_packet_buffer

        # 1. 长度校验
        if len(packet) != self.UPLINK_PACKET_LENGTH:
            print(
                f"Parser Validation Error: Incorrect uplink packet length ({len(packet)} vs {self.UPLINK_PACKET_LENGTH}) for {packet.hex().upper()}")
            return False

        # 2. 帧头校验 (0xAA)
        if packet[0] != 0xAA:
            print(
                f"Parser Validation Error: Invalid uplink header byte {packet[0]:02X} (expected 0xAA) for {packet.hex().upper()}")
            return False

        # 3. DIR (通信方向) 校验 (0b01 for uplink)
        dir_val = (packet[1] >> 6) & 0b11
        if dir_val != CommunicationDirection.UPLINK.value:
            print(
                f"Parser Validation Error: Invalid uplink DIR {dir_val:02b} (expected {CommunicationDirection.UPLINK.value:02b}) for {packet.hex().upper()}")
            return False

        # 4. 帧尾校验 (0x55)
        if packet[6] != 0x55:
            print(
                f"Parser Validation Error: Invalid uplink tail byte {packet[6]:02X} (expected 0x55) for {packet.hex().upper()}")
            return False

        # 5. CS (校验位) 校验
        calculated_checksum = 0
        for i in range(self.UPLINK_PACKET_LENGTH - 1):  # 前7个byte的异或结果 (index 0 到 6)
            calculated_checksum ^= packet[i]

        received_checksum = packet[self.UPLINK_PACKET_LENGTH - 1]  # 最后一个字节是CS (index 7)
        if calculated_checksum != received_checksum:
            print(
                f"Parser Validation Error: Uplink checksum mismatch for {packet.hex().upper()}. Calculated: {calculated_checksum:02X}, Received: {received_checksum:02X}")
            return False

        # 如果所有校验通过，则解析字段
        try:
            parsed_data = {
                "DIR": CommunicationDirection((packet[1] >> 6) & 0b11).name,
                "FUN": FunctionSelection((packet[1] >> 4) & 0b11).name,
                "MODE": RunningMode((packet[1] >> 2) & 0b11).name,
                "DEVICE": packet[1] & 0b11,
                "TRACK": packet[2],
                "STATE": packet[3],
                "IO_16_9": packet[4],
                "IO_8_1": packet[5],
            }
            self.parsed_uplink_packet.emit(parsed_data)  # 通过子类的信号发出解析后的数据
            return True
        except ValueError as e:
            print(f"Parser Error: Could not convert enum value - {e}. Packet: {packet.hex().upper()}")
            return False
        except Exception as e:
            print(f"Parser Unexpected Error: {e}. Packet: {packet.hex().upper()}")
            return False

    def _construct_and_send_downlink_packet(self, command_dict: dict):
        """
        内部槽函数，根据传入的字典构建下行协议数据包，并发送。
        协议参考：通信协议.pdf 中“上位机→下位机”表格和描述
        command_dict 期望包含: "FUN" (str), "MODE" (str, 默认为"REMOTE_CONTROL"), "DEVICE" (int), "TRACK" (int), "CMD" (str)
        """
        try:
            packet = bytearray()
            packet.append(0xAA)  # 帧头

            # 组合字节1: DIR (0b10) | FUN (2bit) | MODE (2bit) | DEVICE (2bit)
            dir_val = CommunicationDirection.DOWNLINK.value  # 下行 0b10

            # FUN功能选择
            fun_name = command_dict.get("FUN", "ALL_TYPES")  # 默认为全选
            fun_val = FunctionSelection[fun_name].value if isinstance(fun_name, str) else fun_name

            # MODE运行模式: 远程控制0b10
            mode_name = command_dict.get("MODE", "REMOTE_CONTROL")  # 默认为远程控制
            mode_val = RunningMode[mode_name].value if isinstance(mode_name, str) else mode_name

            device_val = command_dict.get("DEVICE", 0)  # DEVICE设备号: 1~3,0代表全选

            byte1 = (dir_val << 6) | (fun_val << 4) | (mode_val << 2) | (device_val & 0b11)
            packet.append(byte1)

            packet.append(command_dict.get("TRACK", 0))  # TRACK股道号

            # CMD控制指令
            cmd_name = command_dict.get("CMD", "QUERY")  # 默认查询
            cmd_val = Command[cmd_name].value if isinstance(cmd_name, str) else cmd_name
            packet.append(cmd_val)

            packet.append(0x00)  # 预留位1
            packet.append(0x00)  # 预留位2
            packet.append(0x55)  # 帧尾

            # CS检验位: 前面7个byte的异或结果 (index 0到6，即 0xAA到 0x55)
            checksum = 0
            for i in range(self.DOWNLINK_PACKET_LENGTH - 1):  # 0到6，共7个字节
                checksum ^= packet[i]

            packet.append(checksum)  # CS

            if len(packet) != self.DOWNLINK_PACKET_LENGTH:
                print(
                    f"Construct Error: Downlink packet length mismatch! Expected {self.DOWNLINK_PACKET_LENGTH}, got {len(packet)}")
                return

            print(f"DownlinkTcpClient: Constructed downlink packet: {packet.hex().upper()}")
            super().send_data(bytes(packet))  # 调用父类的 send_data 方法来发送字节数据

        except KeyError as e:
            print(f"DownlinkTcpClient Error: Missing or invalid enum key in command_dict: {e}. Dict: {command_dict}")
        except ValueError as e:
            print(
                f"DownlinkTcpClient Error: Invalid value in command_dict (e.g. non-int for TRACK/DEVICE) - {e}. Dict: {command_dict}")
        except Exception as e:
            print(f"DownlinkTcpClient Error constructing downlink packet: {e} for dict: {command_dict}")
