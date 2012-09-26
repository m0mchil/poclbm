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