from Transport import Transport
from base64 import b64encode
from json import dumps, loads
from log import *
from sha256 import hash
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

		self.update = True
		self.long_poll_active = False
		self.long_poll_url = ''

	def start(self):
		self.should_stop = False
		long_poll_thread = Thread(target=self.long_poll_thread)
		long_poll_thread.daemon = True
		long_poll_thread.start()

		while True:
			if self.should_stop: return
			try:
				with self.miner.lock:
					update = self.update = (self.update or (time() - self.miner.lastWork) > if_else(self.long_poll_active, self.long_poll_max_askrate, self.miner.options.askrate))
				if update:
					work = self.getwork()
					if self.update:
						self.miner.queue_work(work)

				while not self.result_queue.empty():
					result = self.result_queue.get(False)
					with self.miner.lock:
						rv = self.send_result(result)
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
			if (not self.miner.options.nsf) and hostList: self.add_servers(loads(hostList))
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
			if self.server != self.servers[0] and self.miner.options.failback > 0:
				if self.failback_getwork_count >= self.miner.options.failback:
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
				self.backup_pool_index = 1
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
			say('Problems communicating with bitcoin RPC %s %s', (self.errors, self.miner.options.tolerance))
			self.errors += 1
			if self.errors > self.miner.options.tolerance + 1:
				self.errors = 0
				if self.backup_pool_index >= len(self.servers):
					say_line("No more backup pools left. Using primary and starting over.")
					pool = self.servers[0]
					self.backup_pool_index = 1
				else:
					pool = self.servers[self.backup_pool_index]
					self.backup_pool_index += 1
				self.set_server(pool)

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
						#d = result['work']['data']
						#d = ''.join([d[:136], pack('I', long(result['data'][1])).encode('hex'), d[144:152], pack('I', long(result['output'][i])).encode('hex'), d[160:]])
						data = ''.join([result.header.encode('hex'), pack('III', long(result.time), long(result.difficulty), long(result.nonce[i])).encode('hex'), '000000800000000000000000000000000000000000000000000000000000000000000000000000000000000080020000'])
						hashid = pack('I', long(h[6])).encode('hex')
						accepted = self.getwork(data)
						if accepted != None:
							self.miner.block_found(hashid, accepted)
							self.miner.share_count[if_else(accepted, 1, 0)] += 1

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
					self.miner.queue_work(result['result'])
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
