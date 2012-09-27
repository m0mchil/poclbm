from Queue import Queue
from log import *
from sha256 import *
from time import time

class Transport(object):
	def __init__(self, servers, server):
		self.servers = servers
		self.server = server
		self.proto, self.user, self.pwd, self.host, self.name = server[:5]
		self.result_queue = Queue()
		self.options = servers.options

	def loop(self):
		self.should_stop = False
		self.last_failback = time()

	def check_failback(self):
		if self.servers.server_index != 0 and time() - self.last_failback > self.options.failback:
			self.stop()
			return True

	def process_result_queue(self):
		while not self.result_queue.empty():
			result = self.result_queue.get(False)
			with self.servers.lock:
				if not self.servers.send(result, self.send_internal):
					self.result_queue.put(result)
					self.stop()
					break