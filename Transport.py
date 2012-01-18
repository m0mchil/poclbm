from Queue import Queue
from log import *
from sha256 import *
from time import time
from util import if_else
import log

class Transport(object):
	def __init__(self, miner):
		self.lock = RLock()
		self.result_queue = Queue()
		self.miner = miner
		self.config = miner.options
		self.update = True
		self.last_work = 0

		self.backup_server_index = 1
		self.errors = 0
		self.failback_getwork_count = 0
		self.failback_attempt_count = 0
		self.server = None
		self.user_agent = 'poclbm/' + miner.version

		self.difficulty = 0
		self.true_target = None
		self.last_block = ''

		self.sent = {}

		if self.config.proxy:
			self.config.proxy = self.parse_server(self.config.proxy, False)

		self.servers = []
		for server in self.config.servers:
			try:
				self.servers.append(self.parse_server(server))
			except ValueError:
				say_line("Ignored invalid server entry: '%s'", server)
				continue

	def parse_server(self, server, mailAsUser=True):
		temp = server.split('://', 1)
		if len(temp) == 1:
			proto = ''; temp = temp[0]
		else: proto = temp[0]; temp = temp[1]
		if mailAsUser:
			user, temp = temp.split(':', 1)
			pwd, host = temp.split('@')
		else:
			temp = temp.split('@', 1)
			if len(temp) == 1:
				user = ''
				pwd = ''
				host = temp[0]
			else:
				if temp[0].find(':') <> -1:
					user, pwd = temp[0].split(':')
				else:
					user = temp[0]
					pwd = ''
				host = temp[1]

		if host.find('#') != -1:
			host, name = host.split('#')
		else: name = host

		return (proto, user, pwd, host, name)

	def loop(self):
		if not self.servers:
			print '\nAt least one server is required'
			return
		else:
			self.set_server(self.servers[0])
			self.user_servers = list(self.servers)
		self.loop_internal()

	def loop_internal(self):
		raise NotImplementedError

	def stop(self):
		raise NotImplementedError

	def decode(self, work):
		raise NotImplementedError

	def send_internal(self, result):
		raise NotImplementedError

	def set_difficulty(self, difficulty):
		self.difficulty = difficulty
		bits = hex(difficulty)
		bits = bits[2:len(bits) - 1]
		bits += ('0' * (8 - len(bits)))
		bits = ''.join(list(chunks(bits, 2))[::-1])
		true_target = '%064x' % (int(bits[2:], 16) * 2 ** (8 * (int(bits[:2], 16) - 3)),)
		true_target = ''.join(list(chunks(true_target, 2))[::-1])
		self.true_target = np.array(unpack('IIIIIIII', true_target.decode('hex')), dtype=np.uint32)

	def process(self, work):
		if work:
			if work.difficulty != self.difficulty:
				self.set_difficulty(work.difficulty)

	def send(self, result):
		for i in xrange(self.miner.output_size):
			if result.nonce[i]:
				h = hash(result.state, result.merkle_end, result.time, result.difficulty, result.nonce[i])
				if h[7] != 0:
					say_line('Verification failed, check hardware!')
					self.miner.stop()
				else:
					self.miner.diff1_found(bytereverse(h[6]), result.target[6])
					if belowOrEquals(h[:7], result.target[:7]):
						is_block = belowOrEquals(h[:7], self.true_target[:7])
						hash6 = pack('I', long(h[6])).encode('hex')
						hash5 = pack('I', long(h[5])).encode('hex')
						self.sent[result.nonce[i]] = (is_block, hash6, hash5)
						self.send_internal(result, result.nonce[i])

	def report(self, nonce, accepted):
		is_block, hash6, hash5 = self.sent[nonce]
		self.miner.share_found(if_else(is_block, hash6 + hash5, hash6), accepted, is_block)
		del self.sent[nonce]

	def set_server(self, server):
		self.server = server
		proto, user, pwd, host, name = server
		self.proto = proto
		self.host = host
		#say_line('Setting server %s (%s @ %s)', (name, user, host))
		say_line('Setting server (%s @ %s)', (user, name))
		log.server = name + ' '

	def add_servers(self, hosts):
		self.servers = list(self.user_servers)
		for host in hosts[::-1]:
			server = self.server
			server = (server[0], server[1], server[2], ''.join([host['host'], ':', str(host['port'])]), server[4])
			self.servers.insert(self.backup_server_index, server)

	def queue_work(self, work):
		work = self.decode(work)
		self.process(work)
		with self.lock:
			self.miner.work_queue.put(work)
			if work:
				self.update = False; self.last_work = time()
				if self.last_block != work.header[25:29]:
					self.last_block = work.header[25:29]
					self.clear_result_queue()

	def clear_result_queue(self):
		while not self.result_queue.empty():
			self.result_queue.get(False)
