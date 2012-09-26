from Queue import Queue, Empty
from Transport import Transport
from binascii import hexlify, unhexlify
from hashlib import sha256
from json import dumps, loads
from log import *
from threading import Thread, Lock
from time import sleep, time
from util import *
import asynchat
import asyncore
import socket
import socks
#import ssl


BASE_DIFFICULTY = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


class StratumTransport(Transport):
	def __init__(self, servers, server):
		super(StratumTransport, self).__init__(servers, server)
		self.handler = None
		self.socket = None
		self.channel_map = {}
		self.subscribed = False
		self.authorized = None
		self.submits = {}
		self.last_submits_cleanup = time()
		self.pool_difficulty = BASE_DIFFICULTY
		self.jobs = {}
		self.current_job = None
		self.extranonce = ''
		self.extranonce2_size = 4
		self.send_lock = Lock()

	def loop(self):
		super(StratumTransport, self).loop()

		self.servers.update_time = True

		while True:
			if self.should_stop: return

			if self.current_job:
				miner = self.servers.updatable_miner()
				while miner:
					self.current_job = self.refresh_job(self.current_job)
					self.queue_work(self.current_job, miner)
					miner = self.servers.updatable_miner()

			if self.check_failback():
				return True

			if not self.handler:
				try:
					#socket = ssl.wrap_socket(socket)
					host = self.server[3]
					address, port = host.split(':', 1)


					if not self.options.proxy:
						self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
						self.socket.connect((address, int(port)))
					else:
						proxy_proto, user, pwd, proxy_host, name = self.options.proxy
						proxy_port = 9050
						proxy_host = proxy_host.split(':')
						if len(proxy_host) > 1:
							proxy_port = int(proxy_host[1]); proxy_host = proxy_host[0]

						self.socket = socks.socksocket()
				
						proxy_type = socks.PROXY_TYPE_SOCKS5
						if proxy_proto == 'http':
							proxy_type = socks.PROXY_TYPE_HTTP
						elif proxy_proto == 'socks4':
							proxy_type = socks.PROXY_TYPE_SOCKS4
				
						self.socket.setproxy(proxy_type, proxy_host, proxy_port, True, user, pwd)
						try:
							self.socket.connect((address, int(port)))
						except socks.Socks5AuthError:
							say_exception('Proxy error:')
							self.stop()

					self.handler = Handler(self.socket, self.channel_map, self)
					thread = Thread(target=self.asyncore_thread)
					thread.daemon = True
					thread.start()

					if not self.subscribe():
						say_line('Failed to subscribe')
						self.stop()
					elif not self.authorize():
						self.stop()

				except socket.error:
					say_exception()
					self.stop()
					continue

			with self.send_lock:
				while not self.result_queue.empty():
					result = self.result_queue.get(False)
					#if not self.send(result):
					if not self.servers.send(result, self.send_internal):
						self.result_queue.put(result)
						self.stop()
						break
			sleep(1)

	def asyncore_thread(self):
		asyncore.loop(map=self.channel_map)

	def stop(self):
		self.should_stop = True
		if self.handler:
			self.handler.close()

	def refresh_job(self, j):
		j.extranonce2 = self.increment_nonce(j.extranonce2)
		coinbase = j.coinbase1 + self.extranonce + j.extranonce2 + j.coinbase2
		coinbase_hash = sha256(sha256(unhexlify(coinbase)).digest()).digest()

		merkle_root = coinbase_hash
		for hash in j.merkle_branch:
			merkle_root = sha256(sha256(merkle_root + unhexlify(hash)).digest()).digest()
		merkle_root_reversed = ''
		for word in chunks(merkle_root, 4):
			merkle_root_reversed += word[::-1]
		merkle_root = hexlify(merkle_root_reversed)

		j.block_header = ''.join([j.version, j.prevhash, merkle_root, j.ntime, j.nbits])
		j.time = time()
		return j
		

	def increment_nonce(self, nonce):
		next_nonce = long(nonce, 16) + 1
		if len('%x' % next_nonce) > (self.extranonce2_size * 2):
			return '00' * self.extranonce2_size
		return ('%0' + str(self.extranonce2_size * 2) +'x') % next_nonce

	def handle_message(self, message):

		#Miner API
		if 'method' in message:

			#mining.notify
			if message['method'] == 'mining.notify':
				params = message['params']

				j = Object()

				j.job_id = params[0]
				j.prevhash = params[1]
				j.coinbase1 = params[2]
				j.coinbase2 = params[3]
				j.merkle_branch = params[4]
				j.version = params[5]
				j.nbits = params[6]
				j.ntime = params[7]
				clear_jobs = params[8]
				if clear_jobs:
					self.jobs.clear()
				j.extranonce2 = self.extranonce2_size * '00'

				j = self.refresh_job(j)

				self.jobs[j.job_id] = j
				self.current_job = j

				self.queue_work(j)
				self.servers.connection_ok()

			#mining.get_version
			if message['method'] == 'mining.get_version':
				with self.send_lock:
					self.send_message({"error": None, "id": message['id'], "result": self.user_agent})

			#mining.set_difficulty
			elif message['method'] == 'mining.set_difficulty':
				say_line("Setting new difficulty: %s", message['params'][0])
				self.pool_difficulty = BASE_DIFFICULTY / message['params'][0]
	
			#client.reconnect
			elif message['method'] == 'client.reconnect':
				(hostname, port) = message['params'][:2]
				server = self.servers[self.server_index]
				say_line(server[4] + " asked us to reconnect to %s:%d", (hostname, port))
				server[3] = hostname + ':' + str(port)
				self.server = server
				self.servers[self.server_index] = server
				self.handler.close()

		#responses to server API requests
		elif 'result' in message:

			#response to mining.subscribe
			#store extranonce and extranonce2_size
			if message['id'] == 's':
				self.extranonce = message['result'][1]
				self.extranonce2_size = message['result'][2]
				self.subscribed = True

			#check if this is submit confirmation (message id should be in submits dictionary)
			#cleanup if necessary
			elif message['id'] in self.submits:
				miner, nonce, t = self.submits[message['id']]
				accepted = message['result']
				self.servers.report(miner, nonce, accepted)
				del self.submits[message['id']]
				if time() - self.last_submits_cleanup > 3600:
					now = time()
					for key, value in self.submits.items():
						if now - value[2] > 3600:
							del self.submits[key]
					self.last_submits_cleanup = now

			#response to mining.authorize
			elif message['id'] == self.server[1]:
				if not message['result']:
					say_line('authorization failed with %s:%s@%s', (self.server[1:4]))
					self.authorized = False
				else:
					self.authorized = True

	def subscribe(self):
		self.send_message({'id': 's', 'method': 'mining.subscribe', 'params': []})
		for i in xrange(10):
			sleep(1)
			if self.subscribed: break
		return self.subscribed

	def authorize(self):
		self.send_message({'id': self.user, 'method': 'mining.authorize', 'params': [self.user, self.pwd]})
		for i in xrange(10):
			sleep(1)
			if self.authorized != None: break
		return self.authorized

	def send_internal(self, result, nonce):
		job_id = result.job_id
		if not job_id in self.jobs:
			return True
		user = self.server[1]
		extranonce2 = result.extranonce2
		ntime = pack('I', long(result.time)).encode('hex')
		hex_nonce = pack('I', long(nonce)).encode('hex')
		id = job_id + hex_nonce
		self.submits[id] = (result.miner, nonce, time())
		return self.send_message({'params': [user, job_id, extranonce2, ntime, hex_nonce], 'id': id, 'method': u'mining.submit'})

	def send_message(self, message):
		data = dumps(message) + '\n'
		try:
			#self.handler.push(data)

			#there is some bug with asyncore's send mechanism
			#so we send data 'manually'
			#note that this is not thread safe
			if not self.handler:
				return False
			while data:
				sent = self.handler.send(data)
				data = data[sent:]
			return True
		except AttributeError:
			self.stop()
		except Exception:
			say_exception()
			self.stop()

	def queue_work(self, work, miner=None):
		target = ''.join(list(chunks('%064x' % self.pool_difficulty, 2))[::-1])
		self.servers.queue_work(self, work.block_header, target, work.job_id, work.extranonce2, miner)

class Handler(asynchat.async_chat):
	def __init__(self, socket, map, parent):
		asynchat.async_chat.__init__(self, socket, map)
		self.parent = parent
		self.data = ''
		self.set_terminator('\n')

	def handle_close(self):
		self.close()
		self.parent.handler = None
		self.parent.socket = None

	def handle_error(self):
		type, value, trace = sys.exc_info()
		say_exception()
		self.parent.stop()

	def collect_incoming_data(self, data):
		self.data += data

	def found_terminator(self):
		message = loads(self.data)
		self.parent.handle_message(message)
		self.data = ''
