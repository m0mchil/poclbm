from Queue import Queue
from log import *
from sha256 import *
import log

class Transport(object):
	def __init__(self, miner):
		self.miner = miner
		self.config = miner.options
		self.result_queue = Queue()

		self.backup_server_index = 1
		self.errors = 0
		self.failback_getwork_count = 0
		self.failback_attempt_count = 0
		self.server = None
		self.user_agent = 'poclbm/' + miner.version

		self.servers = []
		for server in self.config.servers:
			try:
				temp = server.split('://', 1)
				if len(temp) == 1:
					proto = ''; temp = temp[0]
				else: proto = temp[0]; temp = temp[1]
				user, temp = temp.split(':', 1)
				pwd, host = temp.split('@')
				if host.find('#') != -1:
					host, name = host.split('#')
				else: name = host
				self.servers.append((proto, user, pwd, host, name))
			except ValueError:
				say_line("Ignored invalid server entry: '%s'", server)
				continue
		if not self.servers:
			self.failure('At least one server is required')
		else:
			self.set_server(self.servers[0])
			self.user_servers = list(self.servers)

	def loop(self):
		raise NotImplementedError

	def stop(self):
		raise NotImplementedError

	def send_internal(self, result):
		raise NotImplementedError

	def queue(self, result):
		self.result_queue.put(result)

	def send_result(self, result):
		for i in xrange(self.miner.output_size):
			if result.nonce[i]:
				h = hash(result.state, result.merkle_end, result.time, result.difficulty, result.nonce[i])
				if h[7] != 0:
					say_line('Verification failed, check hardware!')
					self.miner.stop()
				else:
					self.miner.diff1_found(bytereverse(h[6]), result.target[6])
					if belowOrEquals(h[:7], result.target[:7]):
						accepted = self.send_internal(result, result.nonce[i])
						if accepted != None:
							hashid = pack('I', long(h[6])).encode('hex')
							self.miner.block_found(hashid, accepted)

	def set_server(self, server):
		self.server = server
		proto, user, pwd, host, name = server
		self.proto = proto
		self.host = host
		#self.say_line('Setting server %s (%s @ %s)', (name, user, host))
		say_line('Setting server (%s @ %s)', (user, name))
		log.server = name + ' '

	def add_servers(self, hosts):
		self.servers = list(self.user_servers)
		for host in hosts[::-1]:
			server = self.server
			server = (server[0], server[1], server[2], ''.join([host['host'], ':', str(host['port'])]), server[4])
			self.servers.insert(self.backup_server_index, server)