#!/usr/bin/env python3
"""
Bluetooth Speaker Service for OrangePi Zero3
Nhận lệnh từ Flutter app qua TCP socket để kết nối/disconnect loa Bluetooth
Sử dụng bluetoothctl và pactl có sẵn trên Debian 12
"""

import json
import subprocess
import socket
import threading
import logging
import time
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# TCP Server configuration
HOST = '0.0.0.0'
PORT = 8765

class BluetoothSpeakerService:
    def __init__(self):
        self.connected_speakers = []
        self.clients = []
        self.server_socket = None

    def handle_client(self, client_socket, client_address):
        """Xử lý kết nối từ client"""
        logger.info(f"Client connected from {client_address}")
        self.clients.append(client_socket)

        try:
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break

                try:
                    command = json.loads(data.decode())
                    logger.info(f"Received command: {command}")

                    if command.get('action') == 'ping':
                        # Respond to ping for device discovery
                        self.send_response(client_socket, {
                            'action': 'pong',
                            'service': 'orangepi-bluetooth-speaker',
                            'version': '1.0'
                        })
                    elif command.get('action') == 'scan_speakers':
                        self.scan_bluetooth_speakers(client_socket)
                    elif command.get('action') == 'connect_speaker':
                        mac_address = command.get('mac_address')
                        self.connect_speaker(mac_address, client_socket)
                    elif command.get('action') == 'disconnect_speaker':
                        mac_address = command.get('mac_address')
                        self.disconnect_speaker(mac_address, client_socket)
                    elif command.get('action') == 'list_speakers':
                        self.list_connected_speakers(client_socket)
                    elif command.get('action') == 'auto_reconnect':
                        # Manual trigger auto-reconnect từ app
                        threading.Thread(target=self.auto_reconnect_paired_devices, daemon=True).start()
                        self.send_response(client_socket, {
                            'action': 'auto_reconnect_started',
                            'message': 'Auto-reconnect process started'
                        })

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                    self.send_response(client_socket, {"error": "Invalid JSON"})
                except Exception as e:
                    logger.error(f"Error handling command: {e}")
                    self.send_response(client_socket, {"error": str(e)})

        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            client_socket.close()
            logger.info(f"Client {client_address} disconnected")

    def send_response(self, client_socket, response):
        """Gửi response về client"""
        try:
            message = json.dumps(response) + "\n"
            client_socket.sendall(message.encode())
        except Exception as e:
            logger.error(f"Error sending response: {e}")

    def broadcast_response(self, response):
        """Gửi response tới tất cả clients"""
        for client in self.clients[:]:
            try:
                self.send_response(client, response)
            except:
                if client in self.clients:
                    self.clients.remove(client)

    def scan_bluetooth_speakers(self, client_socket):
        """Scan và tìm loa Bluetooth"""
        try:
            logger.info("Scanning for Bluetooth speakers...")

            # KHÔNG reset power - chỉ setup agent và scan
            # Đảm bảo Bluetooth đã bật
            subprocess.run(['bluetoothctl', 'power', 'on'], capture_output=True)

            # Setup agent
            subprocess.run(['bluetoothctl', 'agent', 'on'], capture_output=True)
            subprocess.run(['bluetoothctl', 'default-agent'], capture_output=True)
            subprocess.run(['bluetoothctl', 'discoverable', 'on'], capture_output=True)
            subprocess.run(['bluetoothctl', 'pairable', 'on'], capture_output=True)

            # GIỮ NGUYÊN tất cả devices đã kết nối/paired
            logger.info("Starting scan without disconnecting existing devices...")

            # Dừng scan cũ nếu có
            subprocess.run(['bluetoothctl', 'scan', 'off'], capture_output=True)

            # Bắt đầu scan mới
            logger.info("Starting Bluetooth scan...")
            scan_proc = subprocess.Popen(
                ['bluetoothctl', 'scan', 'on'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Đợi scan 15 giây (tăng thời gian)
            time.sleep(15)

            # Dừng scan
            scan_proc.terminate()
            subprocess.run(['bluetoothctl', 'scan', 'off'], capture_output=True)

            # Lấy danh sách devices
            result = subprocess.run(
                ['bluetoothctl', 'devices'],
                capture_output=True,
                text=True
            )

            devices = []
            for line in result.stdout.split('\n'):
                if line.strip() and 'Device' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = ' '.join(parts[2:])

                        # Lấy thêm info của device
                        info_result = subprocess.run(
                            ['bluetoothctl', 'info', mac],
                            capture_output=True,
                            text=True
                        )

                        # KHÔNG FILTER GÌ HẾT - Hiển thị tất cả thiết bị
                        logger.info(f"Found device: {name} ({mac})")

                        # Lấy thông tin cơ bản
                        device_type = 'unknown'
                        if 'Audio Sink' in info_result.stdout or 'Audio Source' in info_result.stdout:
                            device_type = 'audio'
                        elif 'Headset' in info_result.stdout or 'A2DP' in info_result.stdout:
                            device_type = 'headset'
                        elif 'Mouse' in info_result.stdout or 'Keyboard' in info_result.stdout:
                            device_type = 'input'
                        elif 'Phone' in info_result.stdout:
                            device_type = 'phone'

                        device_info = {
                            'mac': mac,
                            'name': name,
                            'type': device_type
                        }
                        devices.append(device_info)

            response = {
                'action': 'scan_result',
                'devices': devices
            }

            self.send_response(client_socket, response)

        except Exception as e:
            logger.error(f"Error scanning speakers: {e}")
            self.send_response(client_socket, {
                'action': 'scan_error',
                'error': str(e)
            })

    def connect_speaker(self, mac_address, client_socket):
        """Kết nối tới loa Bluetooth"""
        try:
            logger.info(f"Connecting to speaker: {mac_address}")

            # Trust device
            subprocess.run(['bluetoothctl', 'trust', mac_address], capture_output=True)

            # Pair device nếu chưa pair
            pair_result = subprocess.run(
                ['bluetoothctl', 'pair', mac_address],
                capture_output=True,
                text=True,
                timeout=30
            )

            # Connect device
            connect_result = subprocess.run(
                ['bluetoothctl', 'connect', mac_address],
                capture_output=True,
                text=True,
                timeout=20
            )

            if 'Connection successful' in connect_result.stdout or connect_result.returncode == 0:
                # Đợi một chút để device kết nối hoàn toàn
                time.sleep(2)

                # Kiểm tra PulseAudio sinks
                pa_result = subprocess.run(
                    ['pactl', 'list', 'short', 'sinks'],
                    capture_output=True,
                    text=True
                )

                # Tìm sink của bluetooth device
                mac_formatted = mac_address.replace(":", "_")
                for line in pa_result.stdout.split('\n'):
                    if mac_formatted in line:
                        sink_name = line.split('\t')[1]
                        # Set as default sink
                        subprocess.run(['pactl', 'set-default-sink', sink_name])
                        logger.info(f"Set {sink_name} as default audio sink")

                if mac_address not in self.connected_speakers:
                    self.connected_speakers.append(mac_address)

                response = {
                    'action': 'connect_result',
                    'status': 'connected',
                    'mac_address': mac_address
                }
                self.send_response(client_socket, response)
                logger.info(f"Successfully connected to {mac_address}")
            else:
                response = {
                    'action': 'connect_result',
                    'status': 'failed',
                    'mac_address': mac_address,
                    'error': connect_result.stderr
                }
                self.send_response(client_socket, response)
                logger.error(f"Failed to connect to {mac_address}")

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout connecting to {mac_address}")
            self.send_response(client_socket, {
                'action': 'connect_result',
                'status': 'timeout',
                'mac_address': mac_address
            })
        except Exception as e:
            logger.error(f"Error connecting speaker: {e}")
            self.send_response(client_socket, {
                'action': 'connect_error',
                'error': str(e),
                'mac_address': mac_address
            })

    def disconnect_speaker(self, mac_address, client_socket):
        """Ngắt kết nối loa Bluetooth"""
        try:
            logger.info(f"Disconnecting speaker: {mac_address}")

            result = subprocess.run(
                ['bluetoothctl', 'disconnect', mac_address],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                if mac_address in self.connected_speakers:
                    self.connected_speakers.remove(mac_address)

                response = {
                    'action': 'disconnect_result',
                    'status': 'disconnected',
                    'mac_address': mac_address
                }
                self.send_response(client_socket, response)
                logger.info(f"Disconnected from {mac_address}")
            else:
                response = {
                    'action': 'disconnect_result',
                    'status': 'failed',
                    'mac_address': mac_address,
                    'error': result.stderr
                }
                self.send_response(client_socket, response)

        except Exception as e:
            logger.error(f"Error disconnecting speaker: {e}")
            self.send_response(client_socket, {
                'action': 'disconnect_error',
                'error': str(e),
                'mac_address': mac_address
            })

    def list_connected_speakers(self, client_socket):
        """Liệt kê loa đã kết nối"""
        try:
            connected_devices = []
            all_paired_devices = []
            all_devices = []

            # Phương pháp 1: Lấy tất cả devices (bao gồm cả đã kết nối)
            all_devices_result = subprocess.run(
                ['bluetoothctl', 'devices'],
                capture_output=True,
                text=True
            )
            logger.info(f"All devices output: {all_devices_result.stdout}")

            # Phương pháp 2: Lấy danh sách paired devices
            paired_result = subprocess.run(
                ['bluetoothctl', 'paired-devices'],
                capture_output=True,
                text=True
            )
            logger.info(f"Paired devices output: {paired_result.stdout}")

            # Xử lý tất cả devices (bao gồm cả connected nhưng chưa paired)
            for line in all_devices_result.stdout.split('\n'):
                if line.strip() and 'Device' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = ' '.join(parts[2:])

                        # Kiểm tra connection status và device info
                        info_result = subprocess.run(
                            ['bluetoothctl', 'info', mac],
                            capture_output=True,
                            text=True
                        )

                        # Debug log chi tiết
                        logger.info(f"=== Device: {name} ({mac}) ===")
                        logger.info(f"Info output: {info_result.stdout}")

                        is_connected = 'Connected: yes' in info_result.stdout
                        is_paired = 'Paired: yes' in info_result.stdout
                        is_trusted = 'Trusted: yes' in info_result.stdout

                        # Detect device type (không filter, chỉ classify)
                        device_type = 'unknown'
                        if 'Audio Sink' in info_result.stdout or 'Audio Source' in info_result.stdout:
                            device_type = 'audio'
                        elif 'Headset' in info_result.stdout or 'A2DP' in info_result.stdout:
                            device_type = 'headset'
                        elif 'Mouse' in info_result.stdout or 'Keyboard' in info_result.stdout:
                            device_type = 'input'
                        elif 'Phone' in info_result.stdout:
                            device_type = 'phone'

                        logger.info(f"Device: {name} - Connected: {is_connected}, Paired: {is_paired}, Type: {device_type}")

                        # Lấy thêm thông tin battery nếu có
                        battery_level = None
                        for info_line in info_result.stdout.split('\n'):
                            if 'Battery Percentage' in info_line:
                                try:
                                    battery_level = int(info_line.split('(')[1].split(')')[0])
                                except:
                                    pass

                        device_info = {
                            'mac': mac,
                            'name': name,
                            'connected': is_connected,
                            'paired': is_paired,
                            'type': device_type,
                            'battery': battery_level,
                            'trusted': is_trusted
                        }

                        # THÊM TẤT CẢ thiết bị không filter
                        all_devices.append(device_info)

                        if is_paired:
                            all_paired_devices.append(device_info)

                        if is_connected:
                            connected_devices.append(device_info)

            # Kiểm tra audio sink hiện tại
            current_sink = None
            sink_result = subprocess.run(
                ['pactl', 'get-default-sink'],
                capture_output=True,
                text=True
            )
            if sink_result.returncode == 0:
                current_sink = sink_result.stdout.strip()

            # Kiểm tra thêm từ PulseAudio
            pa_sinks_result = subprocess.run(
                ['pactl', 'list', 'short', 'sinks'],
                capture_output=True,
                text=True
            )
            logger.info(f"PulseAudio sinks: {pa_sinks_result.stdout}")

            response = {
                'action': 'connected_speakers',
                'connected_devices': connected_devices,
                'all_paired_devices': all_paired_devices,
                'all_devices': all_devices,  # Thêm tất cả devices để debug
                'current_audio_sink': current_sink,
                'pulseaudio_sinks': pa_sinks_result.stdout,  # Debug info
                'total_connected': len(connected_devices),
                'total_paired': len(all_paired_devices),
                'total_all': len(all_devices)
            }

            self.send_response(client_socket, response)
            logger.info(f"Found {len(connected_devices)} connected, {len(all_paired_devices)} paired, {len(all_devices)} total devices")

        except Exception as e:
            logger.error(f"Error listing speakers: {e}")
            self.send_response(client_socket, {
                'action': 'list_error',
                'error': str(e)
            })

    def setup_mdns_advertisement(self):
        """Setup mDNS advertisement để Flutter app có thể tự động tìm thấy"""
        try:
            # Tạo file avahi service
            service_content = f"""<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
    <name replace-wildcards="yes">OrangePi Bluetooth Speaker %h</name>
    <service>
        <type>_orangepi-speaker._tcp</type>
        <port>{PORT}</port>
        <txt-record>version=1.0</txt-record>
        <txt-record>service=bluetooth-speaker</txt-record>
    </service>
</service-group>"""

            # Ghi file service
            service_dir = '/etc/avahi/services'
            service_file = f'{service_dir}/orangepi-speaker.service'

            if os.path.exists(service_dir):
                with open(service_file, 'w') as f:
                    f.write(service_content)
                logger.info("mDNS service advertisement created")

                # Restart avahi để load service mới
                try:
                    subprocess.run(['systemctl', 'restart', 'avahi-daemon'], capture_output=True)
                except:
                    pass
            else:
                logger.warning("Avahi not available, skipping mDNS advertisement")

        except Exception as e:
            logger.warning(f"Could not setup mDNS: {e}")

    def auto_reconnect_paired_devices(self):
        """Tự động kết nối lại thiết bị đã pair sau khi reboot"""
        try:
            logger.info("Auto-reconnecting devices after reboot...")

            # Đảm bảo Bluetooth đã sẵn sàng
            subprocess.run(['bluetoothctl', 'power', 'on'], capture_output=True)
            time.sleep(5)

            # Setup agent
            subprocess.run(['bluetoothctl', 'agent', 'on'], capture_output=True)
            subprocess.run(['bluetoothctl', 'default-agent'], capture_output=True)

            # Lấy TẤT CẢ devices (bao gồm cả cache)
            all_devices_result = subprocess.run(
                ['bluetoothctl', 'devices'],
                capture_output=True,
                text=True
            )

            # Cũng lấy danh sách paired devices
            paired_result = subprocess.run(
                ['bluetoothctl', 'paired-devices'],
                capture_output=True,
                text=True
            )

            logger.info(f"All devices: {all_devices_result.stdout}")
            logger.info(f"Paired devices: {paired_result.stdout}")

            reconnected_count = 0
            attempted_devices = []

            # Xử lý tất cả devices từ cache
            for line in all_devices_result.stdout.split('\n'):
                if line.strip() and 'Device' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        mac = parts[1]
                        name = ' '.join(parts[2:])

                        # Kiểm tra trạng thái hiện tại
                        info_result = subprocess.run(
                            ['bluetoothctl', 'info', mac],
                            capture_output=True,
                            text=True
                        )

                        is_connected = 'Connected: yes' in info_result.stdout
                        is_paired = 'Paired: yes' in info_result.stdout
                        is_trusted = 'Trusted: yes' in info_result.stdout

                        logger.info(f"Device {name} ({mac}): Connected={is_connected}, Paired={is_paired}, Trusted={is_trusted}")

                        # Thử reconnect nếu:
                        # 1. Chưa kết nối
                        # 2. Và (đã paired HOẶC đã trusted - có thể đã kết nối trước đây)
                        if not is_connected and (is_paired or is_trusted):
                            logger.info(f"Attempting to reconnect: {name} ({mac})")
                            attempted_devices.append(name)

                            # Trust device trước khi connect
                            subprocess.run(['bluetoothctl', 'trust', mac], capture_output=True)

                            # Nếu chưa pair, thử pair lại
                            if not is_paired:
                                logger.info(f"Re-pairing {name}...")
                                pair_result = subprocess.run(
                                    ['bluetoothctl', 'pair', mac],
                                    capture_output=True,
                                    text=True,
                                    timeout=20
                                )
                                if pair_result.returncode != 0:
                                    logger.warning(f"Pairing failed for {name}: {pair_result.stderr}")

                            # Thử connect
                            connect_result = subprocess.run(
                                ['bluetoothctl', 'connect', mac],
                                capture_output=True,
                                text=True,
                                timeout=15
                            )

                            if connect_result.returncode == 0 or 'Connection successful' in connect_result.stdout:
                                logger.info(f"✅ Reconnected: {name}")
                                reconnected_count += 1

                                # Chỉ set default sink cho audio devices
                                is_audio_device = 'Audio Sink' in info_result.stdout or \
                                                 'Audio Source' in info_result.stdout or \
                                                 'A2DP' in info_result.stdout or \
                                                 'Headset' in info_result.stdout

                                if is_audio_device:
                                    time.sleep(3)
                                    mac_formatted = mac.replace(":", "_")

                                    # Đợi PulseAudio tạo sink
                                    for retry in range(5):
                                        pa_result = subprocess.run(
                                            ['pactl', 'list', 'short', 'sinks'],
                                            capture_output=True,
                                            text=True
                                        )

                                        if mac_formatted in pa_result.stdout:
                                            # Tìm tên sink chính xác
                                            for sink_line in pa_result.stdout.split('\n'):
                                                if mac_formatted in sink_line:
                                                    sink_name = sink_line.split('\t')[1]
                                                    subprocess.run(['pactl', 'set-default-sink', sink_name], capture_output=True)
                                                    logger.info(f"Set {name} as default audio sink: {sink_name}")
                                                    break
                                            break
                                        else:
                                            logger.info(f"Waiting for PulseAudio sink... (retry {retry+1})")
                                            time.sleep(2)

                            else:
                                logger.warning(f"❌ Failed to reconnect: {name} - {connect_result.stderr}")

                        elif is_connected:
                            logger.info(f"Already connected: {name}")

            logger.info(f"Auto-reconnect completed: {reconnected_count}/{len(attempted_devices)} devices reconnected")
            if attempted_devices:
                logger.info(f"Attempted devices: {', '.join(attempted_devices)}")

        except Exception as e:
            logger.error(f"Error in auto-reconnect: {e}")

    def start_server(self):
        """Start TCP server"""
        # Setup mDNS advertisement
        self.setup_mdns_advertisement()

        # Auto-reconnect paired devices sau khi service khởi động (delay 10s)
        def delayed_reconnect():
            time.sleep(10)  # Đợi 10 giây để system ổn định
            self.auto_reconnect_paired_devices()

        threading.Thread(target=delayed_reconnect, daemon=True).start()

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, PORT))
        self.server_socket.listen(5)

        # Lấy IP thực tế
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        logger.info(f"Bluetooth Speaker Service listening on {HOST}:{PORT}")
        logger.info(f"Local IP: {local_ip}")
        logger.info(f"mDNS name: {hostname}.local")

        try:
            while True:
                client_socket, client_address = self.server_socket.accept()
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            if self.server_socket:
                self.server_socket.close()

def main():
    service = BluetoothSpeakerService()
    service.start_server()

if __name__ == "__main__":
    main()
