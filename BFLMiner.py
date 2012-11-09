from Miner import Miner
from Queue import Empty
from binascii import unhexlify
from ioutil import find_udev, find_serial_by_id, find_com_ports
from log import say_line, say_exception
from serial.serialutil import SerialException
from sys import maxint
from time import time, sleep
from util import Object
import numpy as np
import serial

CHECK_INTERVAL = 0.01


def open_device(port):
	return serial.Serial(port, 115200, serial.EIGHTBITS, serial.PARITY_NONE, serial.STOPBITS_ONE, 1, False, False, 5, False, None)

def is_good_init(response):
	return response and response[:31] == b'>>>ID: BitFORCE SHA256 Version ' and response[-4:] == b'>>>\n'

def init_device(device):
	return request(device, b'ZGX')

def request(device, message):
	if device:
		device.flushInput()
		device.write(message)
		return device.readline()

def check(port, likely=True):
	result = False
	try:
		device = open_device(port)
		response = init_device(device)
		device.close()
		result = is_good_init(response)
	except SerialException:
		if likely:
			say_exception()
	if not likely and result:
		say_line('Found BitFORCE on %s', port)
	elif likely and not result:
		say_line('No valid response from BitFORCE on %s', port)
	return result

def initialize(options):
	ports = find_udev(check, 'BitFORCE*SHA256') or find_serial_by_id(check, 'BitFORCE_SHA256') or find_com_ports(check)

	if not options.device and ports:
		print '\nBFL devices on ports:\n'
		for i in xrange(len(ports)):
			print '[%d]\t%s' % (i, ports[i])

	miners = [
		BFLMiner(i, ports[i], options)
		for i in xrange(len(ports))
		if (
			(not options.device) or
			(i in options.device)
		)
	]

	for i in xrange(len(miners)):
		miners[i].cutoff_temp = options.cutoff_temp[min(i, len(options.cutoff_temp) - 1)]
		miners[i].cutoff_interval = options.cutoff_interval[min(i, len(options.cutoff_interval) - 1)]
	return miners

class BFLMiner(Miner):
	def __init__(self, device_index, port, options):
		super(BFLMiner, self).__init__(device_index, options)
		self.port = port
		self.device_name = 'BFL:'+str(self.device_index)

		self.check_interval = CHECK_INTERVAL
		self.last_job = None
		self.min_interval = maxint

	def id(self):
		return self.device_name

	def is_ok(self, response):
		return response and response == b'OK\n'

	def put_job(self):
		if self.busy: return

		temperature = self.get_temperature()
		if temperature < self.cutoff_temp:
			response = request(self.device, b'ZDX')
			if self.is_ok(response):
				if self.switch.update_time:
					self.job.time = (np.uint32(time()) - self.job.time_delta).byteswap()
				data = b''.join([self.job.state.tostring(), self.job.merkle_end.tostring(), self.job.time.tostring(), self.job.difficulty.tostring()])
				response = request(self.device, b''.join([b'>>>>>>>>', data, b'>>>>>>>>']))
				if self.is_ok(response):
					self.busy = True
					self.job_started = time()

					self.last_job = Object()
					self.last_job.header = self.job.header
					self.last_job.merkle_end = self.job.merkle_end
					self.last_job.time = self.job.time
					self.last_job.difficulty = self.job.difficulty
					self.last_job.target = self.job.target
					self.last_job.state = self.job.state
					self.last_job.job_id = self.job.job_id
					self.last_job.extranonce2 = self.job.extranonce2
					self.last_job.server = self.job.server
					self.last_job.miner = self

					self.check_interval = CHECK_INTERVAL
					if not self.switch.update_time or self.job.time.byteswap() - self.job.original_time.byteswap() > 55:
						self.update = True
						self.job = None
				else:
					say_line('%s: bad response when sending block data: %s', (self.id(), response))
			else:
				say_line('%s: bad response when submitting job (ZDX): %s', (self.id(), response))
		else:
			say_line('%s: temperature exceeds cutoff, waiting...', self.id())

	def get_temperature(self):
		response = request(self.device, b'ZLX')
		if response[0] != b'T' or len(response) < 23 or response[-1:] != b'\n':
			say_line('%s: bad response for temperature: %s', (self.id(), response))
			return 0
		return float(response[23:-1])

	def check_result(self):
		response = request(self.device, b'ZFX')
		if response[0] == b'B': return False
		if response == b'NO-NONCE\n': return response
		if response[:12] != 'NONCE-FOUND:' or response[-1:] != '\n':
			say_line('%s: bad response checking result: %s', (self.id(), response))
			return None
		return response[12:-1]

	def nonce_generator(self, nonces):
		for nonce in nonces.split(b','):
			if len(nonce) != 8: continue
			try:
				yield np.fromstring(unhexlify(nonce)[::-1], dtype=np.uint32, count=1)[0]
			except TypeError:
				pass

	def mining_thread(self):
		say_line('started miner on %s', (self.id()))

		while not self.should_stop:
			try:
				self.device = open_device(self.port)
				response = init_device(self.device)
				if not is_good_init(response):
					say_line('Failed to initialize %s (response: %s), retrying...', (self.id(), response))
					self.device.close()
					self.device = None
					sleep(1)
					continue

				last_rated = time()
				iterations = 0
		
				self.job = None
				self.busy = False
				while not self.should_stop:
					if (not self.job) or (not self.work_queue.empty()):
						try:
							self.job = self.work_queue.get(True, 1)
						except Empty:
							if not self.busy:
								continue
						else:
							if not self.job and not self.busy:
								continue
							targetQ = self.job.targetQ
							self.job.original_time = self.job.time
							self.job.time_delta = np.uint32(time()) - self.job.time.byteswap()
		
					if not self.busy:
						self.put_job()
					else:
						result = self.check_result()
						if result:
							now = time()
							
							self.busy = False
							r = self.last_job
							job_duration = now - self.job_started
							self.put_job()
	
							self.min_interval = min(self.min_interval, job_duration)
	
							iterations += 4294967296
							t = now - last_rated
							if t > self.options.rate:
								self.update_rate(now, iterations, t, targetQ)
								last_rated = now; iterations = 0

							if result != b'NO-NONCE\n':
								r.nonces = result
								self.switch.put(r)
	
							sleep(self.min_interval - (CHECK_INTERVAL * 2))
						else:
							if result is None:
								self.check_interval = min(self.check_interval * 2, 1)
	
					sleep(self.check_interval)
			except Exception:
				say_exception()
				if self.device:
					self.device.close()
					self.device = None
				sleep(1)