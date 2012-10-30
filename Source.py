from Queue import Queue
from time import time


class Source(object):
	def __init__(self, switch):
		self.switch = switch
		self.result_queue = Queue()
		self.options = switch.options

	def server(self):
		return self.switch.server()

	def loop(self):
		self.should_stop = False
		self.last_failback = time()

	def check_failback(self):
		if self.switch.server_index != 0 and time() - self.last_failback > self.options.failback:
			self.stop()
			return True

	def process_result_queue(self):
		while not self.result_queue.empty():
			result = self.result_queue.get(False)
			with self.switch.lock:
				if not self.switch.send(result, self.send_internal):
					self.result_queue.put(result)
					self.stop()
					break