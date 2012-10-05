from glob import glob
from serial.tools import list_ports

from detect import LINUX, WINDOWS

def find_udev(check, product_id):
	if not LINUX: return []
	try:
		import pyudev
	except ImportError:
		return []

	ports = []
	context = pyudev.Context()
	for device in context.list_devices(subsystem='tty', ID_MODEL=product_id):
		if check(device.device_node):
			ports.append(device.device_node)
	
	return ports

def find_serial_by_id(check, product_id):
	ports = []
	if LINUX:
		for port in glob('/dev/serial/by-id/*' + product_id + '*'):
			if check(port):
				ports.append(port)
	return ports

def find_com_ports(check):
	ports = []
	if WINDOWS:
		com_ports = [p[0] for p in list_ports.comports()].sort()
		for port in com_ports:
			if check(port):
				ports.append(port)
	return ports