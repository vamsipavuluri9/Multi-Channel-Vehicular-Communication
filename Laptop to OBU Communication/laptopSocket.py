import socket

# IP of OBU 008
UDP_IP = "192.168.52.80"
UDP_PORT = 12345
MESSAGE = b"Hello from Laptop!"

# Create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Send message to OBU
sock.sendto(MESSAGE, (UDP_IP, UDP_PORT))

print("Packet sent to OBU 008!")
