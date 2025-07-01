import datetime
import ipaddress
import json
import socket
import threading
import time
from enum import Enum

from PyQt5.QtCore import QObject, pyqtSignal


class MachineRole(Enum):
    MASTER = "主用"
    BACKUP = "备用"


class HeartbeatStatus(Enum):
    ONLINE = "在线"
    OFFLINE = "离线"


class HotStandby(QObject):
    # 定义状态更新信号
    status_updated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        # Removed machine_id as it's no longer needed for IP determination

        self.local_ip = self.get_local_ip()  # Automatically detect local IP
        self.remote_ip = None  # Will be discovered dynamically
        self.heartbeat_port = 8888
        self.heartbeat_interval = 0.2  # Faster heartbeat interval
        self.timeout_threshold = 0.6  # Faster timeout threshold (e.g., 3 * heartbeat_interval)
        self.discovery_interval = 1.0 # How often to scan for other machines

        # State variables
        self.local_role = MachineRole.BACKUP
        self.local_status = HeartbeatStatus.OFFLINE
        self.remote_role = MachineRole.BACKUP
        self.remote_status = HeartbeatStatus.OFFLINE
        self.last_heartbeat_time = None
        self.heartbeat_received = False
        self.dual_master_check_time = None
        self.dual_master_resolve_delay = 0.5  # Faster dual-master resolution

        # Update device status
        self.update_status()

        # Network components
        self.udp_socket = None
        self.heartbeat_timer = None
        self.monitor_timer = None
        self.discovery_timer = None # New timer for IP discovery
        self.running = False
        self.listen_thread = None
        self.stop_event = threading.Event()

        self.start_service()

    @staticmethod
    def get_local_ip():
        """
        Automatically detects the local IP address within the 192.168.1.x range.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connect to a dummy address to get the local IP
            s.connect(('192.168.1.1', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1' # Fallback to loopback if no network is available
        finally:
            s.close()
        print(f"Detected Local IP: {IP}")
        return IP

    def update_status(self):
        """Updates device status and emits the signal."""
        status_data = {
            'local_role': self.local_role,
            'local_status': self.local_status,
            'remote_role': self.remote_role,
            'remote_status': self.remote_status,
            'local_ip': self.local_ip,
            'remote_ip': self.remote_ip
        }
        self.status_updated.emit(status_data)

    def start_service(self):
        """Starts the heartbeat service."""
        try:
            # Create UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) # Enable broadcast for discovery
            self.udp_socket.bind(('', self.heartbeat_port))
            self.udp_socket.settimeout(0.1) # Shorter timeout for faster listening

            self.running = True
            self.stop_event.clear()

            # Start listening thread
            self.listen_thread = threading.Thread(target=self.listen_heartbeat, daemon=True)
            self.listen_thread.start()

            self.local_status = HeartbeatStatus.ONLINE

            print(f"服务已启动，本机IP: {self.local_ip}, 端口: {self.heartbeat_port}")

            # Start heartbeat timer
            self.start_heartbeat_timer()
            # Start status monitor timer
            self.start_monitor_timer()
            # Start IP discovery timer
            self.start_discovery_timer()

        except Exception as e:
            print(f"错误：启动服务失败: {str(e)}")
            self.stop_service()

    def stop_service(self):
        """Stops the heartbeat service."""
        self.running = False
        self.stop_event.set()

        # Cancel timers
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
            self.heartbeat_timer = None

        if self.monitor_timer:
            self.monitor_timer.cancel()
            self.monitor_timer = None

        if self.discovery_timer:
            self.discovery_timer.cancel()
            self.discovery_timer = None

        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None

        # Reset state
        self.local_role = MachineRole.BACKUP
        self.local_status = HeartbeatStatus.OFFLINE
        self.remote_role = MachineRole.BACKUP
        self.remote_status = HeartbeatStatus.OFFLINE
        self.last_heartbeat_time = None
        self.remote_ip = None # Reset remote IP
        self.dual_master_check_time = None

        self.update_status()
        print("服务已停止")

    def start_heartbeat_timer(self):
        """Starts the heartbeat timer."""
        if not self.running:
            return
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
        self.heartbeat_timer = threading.Timer(self.heartbeat_interval, self.send_heartbeat_task)
        self.heartbeat_timer.daemon = True
        self.heartbeat_timer.start()

    def start_monitor_timer(self):
        """Starts the status monitoring timer."""
        if not self.running:
            return
        if self.monitor_timer:
            self.monitor_timer.cancel()
        self.monitor_timer = threading.Timer(0.1, self.monitor_task) # Faster monitor task for quick updates
        self.monitor_timer.daemon = True
        self.monitor_timer.start()

    def start_discovery_timer(self):
        """Starts the IP discovery timer."""
        if not self.running:
            return
        if self.discovery_timer:
            self.discovery_timer.cancel()
        self.discovery_timer = threading.Timer(self.discovery_interval, self.discover_remote_ip_task)
        self.discovery_timer.daemon = True
        self.discovery_timer.start()

    def send_heartbeat_task(self):
        """Sends heartbeat task."""
        if not self.running:
            return

        try:
            heartbeat_data = {
                'type': 'heartbeat',
                'role': self.local_role.name,
                'timestamp': time.time(),
                'ip': self.local_ip
            }
            data = json.dumps(heartbeat_data).encode('utf-8')

            # Send heartbeat to the currently known remote IP, or broadcast if none
            if self.remote_ip:
                self.udp_socket.sendto(data, (self.remote_ip, self.heartbeat_port))
            else:
                # If remote_ip is unknown, send to broadcast address (e.g., 192.168.1.255)
                # This assumes a /24 subnet for 192.168.1.x
                broadcast_ip = str(ipaddress.IPv4Network(f'{self.local_ip}/24', strict=False).broadcast_address)
                self.udp_socket.sendto(data, (broadcast_ip, self.heartbeat_port))

        except Exception as e:
            if self.running:
                print(f"发送心跳失败: {str(e)}")

        self.start_heartbeat_timer() # Restart timer

    def monitor_task(self):
        """Monitors status task."""
        if not self.running:
            return

        try:
            # Check for heartbeat timeout
            if self.remote_ip and self.last_heartbeat_time:
                time_diff = (datetime.datetime.now() - self.last_heartbeat_time).total_seconds()
                if time_diff > self.timeout_threshold:
                    if self.remote_status != HeartbeatStatus.OFFLINE:
                        self.remote_status = HeartbeatStatus.OFFLINE
                        self.remote_role = MachineRole.BACKUP
                        print("对方心跳超时，标记为离线")

                        # If local is backup and remote is offline, promote to master
                        if self.local_role == MachineRole.BACKUP:
                            self.local_role = MachineRole.MASTER
                            print("检测到对方离线，本机自动升级为主机")
            elif self.remote_ip is None: # If no remote IP is known, assume local is master
                if self.local_role == MachineRole.BACKUP:
                    self.local_role = MachineRole.MASTER
                    print("未检测到对方机器，本机自动成为主机")

        except Exception as e:
            if self.running:
                print(f"状态监控错误: {str(e)}")

        self.start_monitor_timer() # Restart timer
        self.update_status()

    def determine_initial_role(self):
        """
        Determines the initial role based on whether a remote machine is detected
        and then by IP comparison. This runs very quickly after discovering the remote.
        """
        if not self.running:
            return

        if self.remote_status == HeartbeatStatus.OFFLINE or self.remote_ip is None:
            # If no remote machine is detected, or it's offline, this machine becomes master
            self.local_role = MachineRole.MASTER
            self.remote_role = MachineRole.BACKUP
            print("未检测到对方机器或对方离线，本机自动成为主机")
        else:
            # If a remote machine is online, compare IPs
            try:
                local_ip_int = int(ipaddress.ip_address(self.local_ip))
                remote_ip_int = int(ipaddress.ip_address(self.remote_ip))

                if local_ip_int < remote_ip_int:
                    self.local_role = MachineRole.MASTER
                    self.remote_role = MachineRole.BACKUP
                    print(f"IP比较：本机({self.local_ip}) < 对方({self.remote_ip})，本机成为主机")
                else:
                    self.local_role = MachineRole.BACKUP
                    self.remote_role = MachineRole.MASTER
                    print(f"IP比较：本机({self.local_ip}) > 对方({self.remote_ip})，本机成为备机")
            except Exception:
                # Fallback in case of IP comparison error (shouldn't happen with valid IPs)
                self.local_role = MachineRole.BACKUP
                print("IP比较失败，本机默认成为备机")
        self.update_status()

    def listen_heartbeat(self):
        """Listens for heartbeat packets."""
        while self.running and not self.stop_event.is_set():
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                sender_ip = addr[0]

                if sender_ip == self.local_ip: # Ignore own heartbeats
                    continue

                # Only process heartbeats from 192.168.1.x range and not own IP
                if sender_ip.startswith('192.168.1.') and sender_ip != self.local_ip:
                    try:
                        heartbeat_data = json.loads(data.decode('utf-8'))

                        if heartbeat_data.get('type') == 'heartbeat':
                            # If a remote IP is not yet set, or it changed, update it
                            if self.remote_ip is None or self.remote_ip != sender_ip:
                                print(f"发现对方机器IP: {sender_ip}")
                                self.remote_ip = sender_ip
                                # Immediately determine role upon discovering the other machine
                                self.determine_initial_role()

                            self.last_heartbeat_time = datetime.datetime.now()
                            self.heartbeat_received = True
                            self.remote_status = HeartbeatStatus.ONLINE

                            # Update remote role
                            remote_role_name = heartbeat_data.get('role', 'BACKUP')
                            if remote_role_name == 'MASTER':
                                self.remote_role = MachineRole.MASTER
                            elif remote_role_name == 'BACKUP':
                                self.remote_role = MachineRole.BACKUP
                            else:
                                self.remote_role = MachineRole.BACKUP

                            # Check for dual master situation
                            self.check_dual_master()

                        elif heartbeat_data.get('type') == 'demotion_notification':
                            self.handle_demotion_notification(heartbeat_data)

                    except json.JSONDecodeError:
                        pass # Ignore malformed JSON
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"监听心跳失败: {str(e)}")
            self.update_status()

    def discover_remote_ip_task(self):
        """
        Task to actively discover remote IP by sending broadcast heartbeats.
        This helps when a remote machine comes online or changes IP.
        """
        if not self.running:
            return

        if self.remote_ip is None or self.remote_status == HeartbeatStatus.OFFLINE:
            # Send a broadcast heartbeat to try and discover the other machine
            print("正在扫描局域网以发现对方机器...")
            self.send_heartbeat_task() # This function now also handles broadcast

        self.start_discovery_timer() # Reschedule for continuous discovery

    def check_dual_master(self):
        """Checks and resolves dual master situations."""
        if (self.local_role == MachineRole.MASTER and
                self.remote_role == MachineRole.MASTER and
                self.remote_status == HeartbeatStatus.ONLINE):

            # First time dual master is detected
            if self.dual_master_check_time is None:
                self.dual_master_check_time = time.time()
                print("警告：检测到双主机状态！开始解决程序...")
                return

            # Execute resolution after delay
            if time.time() - self.dual_master_check_time >= self.dual_master_resolve_delay:
                self.resolve_dual_master()
        else:
            # Reset dual master check time
            if self.dual_master_check_time is not None:
                self.dual_master_check_time = None
        self.update_status()

    def resolve_dual_master(self):
        """Resolves dual master conflict: higher IP becomes backup."""
        try:
            local_ip_int = int(ipaddress.ip_address(self.local_ip))
            remote_ip_int = int(ipaddress.ip_address(self.remote_ip))

            if local_ip_int > remote_ip_int:
                # Local IP is larger, demote to back up
                self.local_role = MachineRole.BACKUP
                self.remote_role = MachineRole.MASTER
                print(f"双主机冲突解决：本机IP({self.local_ip}) > 对方IP({self.remote_ip})，本机降级为备机")
                self.send_demotion_notification()

            elif local_ip_int < remote_ip_int:
                # Local IP is smaller, remain master, wait for other to demote
                print(f"双主机冲突解决：本机IP({self.local_ip}) < 对方IP({self.remote_ip})，本机保持主机状态")
            else:
                # IPs are the same (should be rare/impossible in a properly configured network)
                print("警告：检测到相同IP地址，使用随机方式解决冲突")
                import random
                if random.choice([True, False]):
                    self.local_role = MachineRole.BACKUP
                    print("随机选择：本机降级为备机")
                    self.send_demotion_notification()

            self.dual_master_check_time = None

        except Exception as e:
            print(f"解决双主机冲突失败: {str(e)}")
            self.dual_master_check_time = None
        self.update_status()

    def send_demotion_notification(self):
        """Sends demotion notification."""
        try:
            notification_data = {
                'type': 'demotion_notification',
                'message': 'dual_master_resolved',
                'timestamp': time.time(),
                'from_ip': self.local_ip
            }
            data = json.dumps(notification_data).encode('utf-8')
            # Send directly to the remote IP if known, otherwise broadcast
            if self.remote_ip:
                self.udp_socket.sendto(data, (self.remote_ip, self.heartbeat_port))
            else:
                broadcast_ip = str(ipaddress.IPv4Network(f'{self.local_ip}/24', strict=False).broadcast_address)
                self.udp_socket.sendto(data, (broadcast_ip, self.heartbeat_port))

        except Exception as e:
            print(f"发送降级通知失败: {str(e)}")

    def handle_demotion_notification(self, notification_data):
        """Handles demotion notification."""
        if notification_data.get('message') == 'dual_master_resolved':
            print("收到对方降级通知，双主机冲突已解决")
            # Reset dual master check time
            self.dual_master_check_time = None
            if self.local_role == MachineRole.MASTER:
                # If we were still master, and they sent a demotion, means they are now backup
                # We should stay master if our IP is smaller, or if their IP is bigger, and they demoted
                # This logic is key to ensure correct state after a resolution.
                if int(ipaddress.ip_address(self.local_ip)) > int(ipaddress.ip_address(notification_data.get('from_ip'))):
                    # Our IP is larger, and they demoted, so we should also demote if we are still master
                    self.local_role = MachineRole.BACKUP
                    print("根据对方降级通知，本机降级为备机")
                else:
                    print("根据对方降级通知，本机保持主机状态")

        self.update_status()