from Queue import Queue
from decimal import Decimal
from threading import Thread
from time import time


class Miner(object):
	def __init__(self, device_index, options):
		self.device_index = device_index
		self.options = options

		self.update_time_counter = 1
		self.share_count = [0, 0]
		self.work_queue = Queue()

		self.update = True

		self.accept_hist = []
		self.rate = self.estimated_rate = 0

	def start(self):
		self.should_stop = False
		Thread(target=self.mining_thread).start()
		self.start_time = time()

	def stop(self, message = None):
		if message: print '\n%s' % message
		self.should_stop = True

	def update_rate(self, now, iterations, t, targetQ, rate_divisor=1000):
		self.rate = int((iterations / t) / rate_divisor)
		self.rate = Decimal(self.rate) / 1000
		if self.accept_hist:
			LAH = self.accept_hist.pop()
			if LAH[1] != self.share_count[1]:
				self.accept_hist.append(LAH)
		self.accept_hist.append((now, self.share_count[1]))
		while (self.accept_hist[0][0] < now - self.options.estimate):
			self.accept_hist.pop(0)
		new_accept = self.share_count[1] - self.accept_hist[0][1]
		self.estimated_rate = Decimal(new_accept) * (targetQ) / min(int(now - self.start_time), self.options.estimate) / 1000
		self.estimated_rate = Decimal(self.estimated_rate) / 1000

		self.switch.status_updated(self)