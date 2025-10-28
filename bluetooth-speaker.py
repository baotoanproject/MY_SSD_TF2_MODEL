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

            # Reset và clear cache trước khi scan
            subprocess.run(['bluetoothctl', 'power', 'off'], capture_output=True)
            time.sleep(1)
            subprocess.run(['bluetoothctl', 'power', 'on'], capture_output=True)
            time.sleep(2)

            # Setup agent
            subprocess.run(['bluetoothctl', 'agent', 'on'], capture_output=True)
            subprocess.run(['bluetoothctl', 'default-agent'], capture_output=True)
            subprocess.run(['bluetoothctl', 'discoverable', 'on'], capture_output=True)
            subprocess.run(['bluetoothctl', 'pairable', 'on'], capture_output=True)

            # Remove devices cũ khỏi cache (optional)
            old_devices = subprocess.run(
                ['bluetoothctl', 'devices'],
                capture_output=True,
                text=True
            )
            for line in old_devices.stdout.split('\n'):
                if line.strip() and 'Device' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        mac = parts[1]
                        subprocess.run(['bluetoothctl', 'remove', mac], capture_output=True)

            # Bắt đầu scan
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

                        # Kiểm tra xem có phải audio device không
                        is_audio = 'Audio Sink' in info_result.stdout or \
                                  'Audio Source' in info_result.stdout or \
                                  'Headset' in info_result.stdout or \
                                  'Speaker' in info_result.stdout or \
                                  'A2DP' in info_result.stdout or \
                                  '0000110b' in info_result.stdout.lower() or \
                                  '0000110a' in info_result.stdout.lower()

                        # Debug: Log tất cả devices để kiểm tra
                        logger.info(f"Device: {name} ({mac})")
                        logger.info(f"Info: {info_result.stdout[:200]}...")
                        logger.info(f"Is audio: {is_audio}")

                        # Tạm thời hiển thị TẤT CẢ devices để debug
                        device_info = {
                            'mac': mac,
                            'name': name,
                            'type': 'audio' if is_audio else 'unknown'
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

            # Lấy danh sách paired devices
            result = subprocess.run(
                ['bluetoothctl', 'paired-devices'],
                capture_output=True,
                text=True
            )

            for line in result.stdout.split('\n'):
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

                        is_connected = 'Connected: yes' in info_result.stdout
                        is_audio = 'Audio Sink' in info_result.stdout or \
                                  'Audio Source' in info_result.stdout or \
                                  'Headset' in info_result.stdout or \
                                  'A2DP' in info_result.stdout

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
                            'type': 'audio' if is_audio else 'other',
                            'battery': battery_level,
                            'trusted': 'Trusted: yes' in info_result.stdout,
                            'paired': True
                        }

                        # Thêm vào danh sách tương ứng
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

            response = {
                'action': 'connected_speakers',
                'connected_devices': connected_devices,
                'all_paired_devices': all_paired_devices,
                'current_audio_sink': current_sink,
                'total_connected': len(connected_devices),
                'total_paired': len(all_paired_devices)
            }

            self.send_response(client_socket, response)
            logger.info(f"Found {len(connected_devices)} connected, {len(all_paired_devices)} paired devices")

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

    def start_server(self):
        """Start TCP server"""
        # Setup mDNS advertisement
        self.setup_mdns_advertisement()

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
