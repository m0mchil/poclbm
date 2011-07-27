from Transport import Transport
from base64 import b64encode
from json import dumps, loads
from log import *
from sha256 import *
from threading import Thread
from time import sleep, time
from urlparse import urlsplit
from util import *
import httplib
import traceback


class NotAuthorized(Exception): pass
class RPCError(Exception): pass

class HttpTransport(Transport):
	def __init__(self, miner):
		self.connection = self.lp_connection = None
		super(HttpTransport, self).__init__(miner)
		self.timeout = 5
		self.long_poll_timeout = 3600
		self.long_poll_max_askrate = 60 - self.timeout
		self.max_redirects = 3

		self.postdata = {'method': 'getwork', 'id': 'json'}

		self.long_poll_active = False
		self.long_poll_url = ''

	def loop(self):
		self.should_stop = False
		thread = Thread(target=self.long_poll_thread)
		thread.daemon = True
		thread.start()

		while True:
			if self.should_stop: return
			try:
				with self.lock:
					update = self.update = (self.update or (time() - self.last_work) > if_else(self.long_poll_active, self.long_poll_max_askrate, self.config.askrate))
				if update:
					work = self.getwork()
					if self.update:
						self.queue_work(work)

				while not self.result_queue.empty():
					result = self.result_queue.get(False)
					with self.lock:
						rv = self.send(result)
				sleep(1)
			except Exception:
				say_line("Unexpected error:")
				traceback.print_exc()

	def connect(self, proto, host, timeout):
		if proto == 'https': connector = httplib.HTTPSConnection
		else: connector = httplib.HTTPConnection
		return connector(host, strict=True, timeout=timeout)

	def request(self, connection, url, headers, data=None):
		result = response = None
		try:
			if data: connection.request('POST', url, data, headers)
			else: connection.request('GET', url, headers=headers)
			response = connection.getresponse()
			if response.status == httplib.UNAUTHORIZED: raise NotAuthorized()
			r = self.max_redirects
			while response.status == httplib.TEMPORARY_REDIRECT:
				response.read()
				url = response.getheader('Location', '')
				if r == 0 or url == '': raise HTTPException('Too much or bad redirects')
				connection.request('GET', url, headers=headers)
				response = connection.getresponse();
				r -= 1
			self.long_poll_url = response.getheader('X-Long-Polling', '')
			self.miner.update_time = bool(response.getheader('X-Roll-NTime', ''))
			hostList = response.getheader('X-Host-List', '')
			if (not self.config.nsf) and hostList: self.add_servers(loads(hostList))
			result = loads(response.read())
			if result['error']:	raise RPCError(result['error']['message'])
			return (connection, result)
		finally:
			if not result or not response or (response.version == 10 and response.getheader('connection', '') != 'keep-alive') or response.getheader('connection', '') == 'close':
				connection.close()
				connection = None

	def getwork(self, data=None):
		save_server = None
		try:
			if self.server != self.servers[0] and self.config.failback > 0:
				if self.failback_getwork_count >= self.config.failback:
					save_server = self.server
					say_line("Attempting to fail back to primary server")
					self.set_server(self.servers[0])
				self.failback_getwork_count += 1
			if not self.connection:
				self.connection = self.connect(self.proto, self.host, self.timeout)
			self.postdata['params'] = if_else(data, [data], [])
			(self.connection, result) = self.request(self.connection, '/', self.headers, dumps(self.postdata))
			self.errors = 0
			if self.server == self.servers[0]:
				self.backup_server_index = 1
				self.failback_getwork_count = 0
				self.failback_attempt_count = 0
			return result['result']
		except NotAuthorized:
			self.failure('Wrong username or password')
		except RPCError as e:
			say('%s', e)
		except (IOError, httplib.HTTPException, ValueError):
			if save_server:
				self.failback_attempt_count += 1
				self.set_server(save_server)
				say_line('Still unable to reconnect to primary server (attempt %s), failing over', self.failback_attempt_count)
				self.failback_getwork_count = 0
				return
			say('Problems communicating with bitcoin RPC %s %s', (self.errors, self.config.tolerance))
			self.errors += 1
			if self.errors > self.config.tolerance + 1:
				self.errors = 0
				if self.backup_server_index >= len(self.servers):
					say_line("No more backup pools left. Using primary and starting over.")
					pool = self.servers[0]
					self.backup_server_index = 1
				else:
					pool = self.servers[self.backup_server_index]
					self.backup_server_index += 1
				self.set_server(pool)

	def send_internal(self, result, nonce):
		data = ''.join([result.header.encode('hex'), pack('III', long(result.time), long(result.difficulty), long(nonce)).encode('hex'), '000000800000000000000000000000000000000000000000000000000000000000000000000000000000000080020000'])
		accepted = self.getwork(data)
		if accepted != None:
			self.report(nonce, accepted)

	def long_poll_thread(self):
		last_host = None
		while True:
			sleep(1)
			url = self.long_poll_url
			if url != '':
				proto = self.proto
				host = self.host
				parsedUrl = urlsplit(url)
				if parsedUrl.scheme != '':
					proto = parsedUrl.scheme
				if parsedUrl.netloc != '':
					host = parsedUrl.netloc
					url = url[url.find(host) + len(host):]
					if url == '': url = '/'
				try:
					if host != last_host: self.close_lp_connection()
					if not self.lp_connection:
						self.lp_connection = self.connect(proto, host, self.long_poll_timeout)
						say_line("LP connected to %s", self.server[4])
						last_host = host
					
					self.long_poll_active = True
					(self.lp_connection, result) = self.request(self.lp_connection, url, self.headers)
					self.long_poll_active = False
					if self.should_stop:
						return
					self.queue_work(result['result'])
					if self.config.verbose:
						say_line('long poll: new block %s%s', (result['result']['data'][56:64], result['result']['data'][48:56]))
				except NotAuthorized:
					say_line('long poll: Wrong username or password')
				except RPCError as e:
					say_line('long poll: %s', e)
				except (IOError, httplib.HTTPException, ValueError):
					say_line('long poll: IO error')
					#traceback.print_exc()
					self.close_lp_connection()

	def stop(self):
		self.should_stop = True
		self.close_lp_connection()

	def set_server(self, server):
		super(HttpTransport, self).set_server(server)
		user, pwd = server[1:3]
		self.headers = {"User-Agent": self.user_agent, "Authorization": 'Basic ' + b64encode('%s:%s' % (user, pwd))}
		self.long_poll_url = ''
		if self.connection:
			self.connection.close()
			self.connection = None
		self.close_lp_connection()

	def close_lp_connection(self):
		if self.lp_connection:
			self.lp_connection.close()
			self.lp_connection = None

	def decode(self, work):
		if work:
			job = Object()

			if not 'target' in work:
				work['target'] = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffff00000000'

			binary_data = work['data'].decode('hex')
			data0 = np.zeros(64, np.uint32)
			data0 = np.insert(data0, [0] * 16, unpack('IIIIIIIIIIIIIIII', binary_data[:64]))

			job.target     = np.array(unpack('IIIIIIII', work['target'].decode('hex')), dtype=np.uint32)
			job.header     = binary_data[:68]
			job.merkle_end = np.uint32(unpack('I', binary_data[64:68])[0])
			job.time       = np.uint32(unpack('I', binary_data[68:72])[0])
			job.difficulty = np.uint32(unpack('I', binary_data[72:76])[0])
			job.state      = sha256(STATE, data0)
			job.f          = np.zeros(8, np.uint32)
			job.state2     = partial(job.state, job.merkle_end, job.time, job.difficulty, job.f)
			job.targetQ    = 2**256 / int(''.join(list(chunks(work['target'], 2))[::-1]), 16)

			calculateF(job.state, job.merkle_end, job.time, job.difficulty, job.f, job.state2)

			return job