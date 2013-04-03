from copy import copy
from log import say_exception, say_line, say_quiet
from sha256 import hash, sha256, STATE
from struct import pack, unpack
from threading import RLock
from time import time, sleep
from util import Object, chunks, bytereverse, belowOrEquals, uint32
import StratumSource
import log
import socks


class Switch(object):
	def __init__(self, options):
		self.lock = RLock()
		self.miners = []
		self.options = options
		self.last_work = 0
		self.update_time = True
		self.max_update_time = options.max_update_time

		self.backup_server_index = 1
		self.errors = 0
		self.failback_attempt_count = 0
		self.server_index = -1
		self.last_server = None
		self.server_map = {}

		self.user_agent = 'poclbm/' + options.version

		self.difficulty = 0
		self.true_target = None
		self.last_block = ''

		self.sent = {}

		if self.options.proxy:
			self.options.proxy = self.parse_server(self.options.proxy, False)
			self.parse_proxy(self.options.proxy)

		self.servers = []
		for server in self.options.servers:
			try:
				self.servers.append(self.parse_server(server))
			except ValueError:
				if self.options.verbose:
					say_exception()
				say_line("Ignored invalid server entry: %s", server)
				continue

	def parse_server(self, server, mailAsUser=True):
		s = Object()
		temp = server.split('://', 1)
		if len(temp) == 1:
			s.proto = ''; temp = temp[0]
		else: s.proto = temp[0]; temp = temp[1]
		if mailAsUser:
			s.user, temp = temp.split(':', 1)
			s.pwd, s.host = temp.split('@')
		else:
			temp = temp.split('@', 1)
			if len(temp) == 1:
				s.user = ''
				s.pwd = ''
				s.host = temp[0]
			else:
				if temp[0].find(':') <> -1:
					s.user, s.pwd = temp[0].split(':')
				else:
					s.user = temp[0]
					s.pwd = ''
				s.host = temp[1]

		if s.host.find('#') != -1:
			s.host, s.name = s.host.split('#')
		else: s.name = s.host

		return s

	def parse_proxy(self, proxy):
		proxy.port = 9050
		proxy.host = proxy.host.split(':')
		if len(proxy.host) > 1:
			proxy.port = int(proxy.host[1]); proxy.host = proxy.host[0]

		proxy.type = socks.PROXY_TYPE_SOCKS5
		if proxy.proto == 'http':
			proxy.type = socks.PROXY_TYPE_HTTP
		elif proxy.proto == 'socks4':
			proxy.type = socks.PROXY_TYPE_SOCKS4

	def add_miner(self, miner):
		self.miners.append(miner)
		miner.switch = self

	def updatable_miner(self):
		for miner in self.miners:
			if miner.update:
				miner.update = False
				return miner

	def loop(self):
		self.should_stop = False
		self.set_server_index(0)

		while True:
			if self.should_stop: return

			failback = self.server_source().loop()

			sleep(1)

			if failback:
				say_line("Attempting to fail back to primary server")
				self.last_server = self.server_index
				self.set_server_index(0)
				continue

			if self.last_server:
				self.failback_attempt_count += 1
				self.set_server_index(self.last_server)
				say_line('Still unable to reconnect to primary server (attempt %s), failing over', self.failback_attempt_count)
				self.last_server = None
				continue

			self.errors += 1
			say_line('IO errors - %s, tolerance %s', (self.errors, self.options.tolerance))

			if self.errors > self.options.tolerance:
				self.errors = 0
				if self.backup_server_index >= len(self.servers):
					say_line("No more backup servers left. Using primary and starting over.")
					new_server_index = 0
					self.backup_server_index = 1
				else:
					new_server_index = self.backup_server_index
					self.backup_server_index += 1
				self.set_server_index(new_server_index)

	def connection_ok(self):
		self.errors = 0
		if self.server_index == 0:
			self.backup_server_index = 1
			self.failback_attempt_count = 0

	def stop(self):
		self.should_stop = True
		if self.server_index != -1:
			self.server_source().stop()

	#callers must provide hex encoded block header and target
	def decode(self, server, block_header, target, job_id = None, extranonce2 = None):
		if block_header:
			job = Object()

			binary_data = block_header.decode('hex')
			data0 = list(unpack('<16I', binary_data[:64])) + ([0] * 48)

			job.target		= unpack('<8I', target.decode('hex'))
			job.header		= binary_data[:68]
			job.merkle_end	= uint32(unpack('<I', binary_data[64:68])[0])
			job.time		= uint32(unpack('<I', binary_data[68:72])[0])
			job.difficulty	= uint32(unpack('<I', binary_data[72:76])[0])
			job.state		= sha256(STATE, data0)
			job.targetQ		= 2**256 / int(''.join(list(chunks(target, 2))[::-1]), 16)
			job.job_id		= job_id
			job.extranonce2	= extranonce2
			job.server		= server

			if job.difficulty != self.difficulty:
				self.set_difficulty(job.difficulty)
	
			return job

	def set_difficulty(self, difficulty):
		self.difficulty = difficulty
		bits = '%08x' % bytereverse(difficulty)
		true_target = '%064x' % (int(bits[2:], 16) * 2 ** (8 * (int(bits[:2], 16) - 3)),)
		true_target = ''.join(list(chunks(true_target, 2))[::-1])
		self.true_target = unpack('<8I', true_target.decode('hex'))

	def send(self, result, send_callback):
		for nonce in result.miner.nonce_generator(result.nonces):
			h = hash(result.state, result.merkle_end, result.time, result.difficulty, nonce)
			if h[7] != 0:
				hash6 = pack('<I', long(h[6])).encode('hex')
				say_line('Verification failed, check hardware! (%s, %s)', (result.miner.id(), hash6))
				return True # consume this particular result
			else:
				self.diff1_found(bytereverse(h[6]), result.target[6])
				if belowOrEquals(h[:7], result.target[:7]):
					is_block = belowOrEquals(h[:7], self.true_target[:7])
					hash6 = pack('<I', long(h[6])).encode('hex')
					hash5 = pack('<I', long(h[5])).encode('hex')
					self.sent[nonce] = (is_block, hash6, hash5)
					if not send_callback(result, nonce):
						return False
		return True

	def diff1_found(self, hash_, target):
		if self.options.verbose and target < 0xFFFF0000L:
			say_line('checking %s <= %s', (hash_, target))

	def status_updated(self, miner):
		verbose = self.options.verbose
		rate = miner.rate if verbose else sum([m.rate for m in self.miners])
		estimated_rate = miner.estimated_rate if verbose else sum([m.estimated_rate for m in self.miners])
		rejected_shares = miner.share_count[0] if verbose else sum([m.share_count[0] for m in self.miners])
		total_shares = rejected_shares + miner.share_count[1] if verbose else sum([m.share_count[1] for m in self.miners])
		total_shares_estimator = max(total_shares, 1)
		say_quiet('%s[%.03f MH/s (~%d MH/s)] [Rej: %d/%d (%.02f%%)]', (miner.id()+' ' if verbose else '', rate, round(estimated_rate), rejected_shares, total_shares, float(rejected_shares) * 100 / total_shares_estimator))

	def report(self, miner, nonce, accepted):
		is_block, hash6, hash5 = self.sent[nonce]
		miner.share_count[1 if accepted else 0] += 1
		hash_ = hash6 + hash5 if is_block else hash6
		if self.options.verbose or is_block:
			say_line('%s %s%s, %s', (miner.id(), 'block ' if is_block else '', hash_, 'accepted' if accepted else '_rejected_'))
		del self.sent[nonce]

	def set_server_index(self, server_index):
		self.server_index = server_index
		user = self.servers[server_index].user
		name = self.servers[server_index].name
		#say_line('Setting server %s (%s @ %s)', (name, user, host))
		say_line('Setting server (%s @ %s)', (user, name))
		log.server = name
		

	def add_servers(self, hosts):
		for host in hosts[::-1]:
			port = str(host['port'])
			if not self.has_server(self.server().user, host['host'], port):
				server = copy(self.server())
				server.host = ''.join([host['host'], ':', port])
				server.source = None
				self.servers.insert(self.backup_server_index, server)

	def has_server(self, user, host, port):
		for server in self.servers:
			server_host, server_port = self.server().host.split(':', 1)
			if server.user == user and server_host == host and server_port == port:
				return True
		return False

	def queue_work(self, server, block_header, target = None, job_id = None, extranonce2 = None, miner=None):
		work = self.decode(server, block_header, target, job_id, extranonce2)
		with self.lock:
			if not miner:
				miner = self.miners[0]
				for i in xrange(1, len(self.miners)):
					self.miners[i].update = True
			miner.work_queue.put(work)
			if work:
				miner.update = False; self.last_work = time()
				if self.last_block != work.header[25:29]:
					self.last_block = work.header[25:29]
					self.clear_result_queue(server)

	def clear_result_queue(self, server):
		while not server.result_queue.empty():
			server.result_queue.get(False)

	def server_source(self):
		if not hasattr(self.server(), 'source'):
			if self.server().proto == 'http':
				import GetworkSource
				getwork_source = GetworkSource.GetworkSource(self)
				say_line('checking for stratum...')

				stratum_host = getwork_source.detect_stratum()
				if stratum_host:
					getwork_source.close_connection()
					self.server().proto = 'stratum'
					self.server().host = stratum_host
					self.add_stratum_source()
				else:
					self.server().source = getwork_source
			else:
				self.add_stratum_source()

		return self.server().source

	def add_stratum_source(self):
		if self.options.stratum_proxies:
			stratum_proxy = StratumSource.detect_stratum_proxy(self.server().host)
			if stratum_proxy:
				original_server = copy(self.server())
				original_server.source = StratumSource.StratumSource(self)
				self.servers.insert(self.backup_server_index, original_server)
				self.server().host = stratum_proxy
				self.server().name += '(p)'
				log.server = self.server().name
			else:
				say_line('No proxy found')
		self.server().source = StratumSource.StratumSource(self)
	
	def server(self):
		return self.servers[self.server_index]

	def put(self, result):
		result.server.result_queue.put(result)
