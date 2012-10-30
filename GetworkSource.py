from Source import Source
from base64 import b64encode
from httplib import HTTPException
from json import dumps, loads
from log import say_exception, say_line
from struct import pack
from threading import Thread
from time import sleep, time
from urlparse import urlsplit
from util import if_else
import httplib
import socket
import socks





class NotAuthorized(Exception): pass
class RPCError(Exception): pass

class GetworkSource(Source):
	def __init__(self, switch):
		super(GetworkSource, self).__init__(switch)

		self.connection = self.lp_connection = None
		self.long_poll_timeout = 3600
		self.max_redirects = 3

		self.postdata = {'method': 'getwork', 'id': 'json'}
		self.headers = {"User-Agent": self.switch.user_agent, "Authorization": 'Basic ' + b64encode('%s:%s' % (self.server().user, self.server().pwd)), "X-Mining-Extensions": 'hostlist midstate rollntime'}
		self.long_poll_url = ''

		self.long_poll_active = False

		self.authorization_failed = False

	def loop(self):
		if self.authorization_failed: return
		super(GetworkSource, self).loop()

		thread = Thread(target=self.long_poll_thread)
		thread.daemon = True
		thread.start()

		while True:
			if self.should_stop: return

			if self.check_failback():
				return True

			try:
				with self.switch.lock:
					miner = self.switch.updatable_miner()
					while miner:
						work = self.getwork()
						self.queue_work(work, miner)
						miner = self.switch.updatable_miner()

				self.process_result_queue()
				sleep(1)
			except Exception:
				say_exception("Unexpected error:")
				break

	def ensure_connected(self, connection, proto, host):
		if connection != None and connection.sock != None:
			return connection, False

		if proto == 'https': connector = httplib.HTTPSConnection
		else: connector = httplib.HTTPConnection

		if not self.options.proxy:
			return connector(host, strict=True), True

		host, port = host.split(':')

		proxy_proto, user, pwd, proxy_host = self.options.proxy[:4]
		proxy_port = 9050
		proxy_host = proxy_host.split(':')
		if len(proxy_host) > 1:
			proxy_port = int(proxy_host[1]); proxy_host = proxy_host[0]

		connection = connector(host, strict=True)
		connection.sock = socks.socksocket()

		proxy_type = socks.PROXY_TYPE_SOCKS5
		if proxy_proto == 'http':
			proxy_type = socks.PROXY_TYPE_HTTP
		elif proxy_proto == 'socks4':
			proxy_type = socks.PROXY_TYPE_SOCKS4

		connection.sock.setproxy(proxy_type, proxy_host, proxy_port, True, user, pwd)
		try:
			connection.sock.connect((host, int(port)))
		except socks.Socks5AuthError:
			say_exception('Proxy error:')
			self.stop()
		return connection, True

	def request(self, connection, url, headers, data=None, timeout=0):
		result = response = None
		try:
			if data: connection.request('POST', url, data, headers)
			else: connection.request('GET', url, headers=headers)
			response = self.timeout_response(connection, timeout)
			if not response:
				return None
			if response.status == httplib.UNAUTHORIZED:
				say_line('Wrong username or password for %s', self.server().name)
				self.authorization_failed = True
				raise NotAuthorized()
			r = self.max_redirects
			while response.status == httplib.TEMPORARY_REDIRECT:
				response.read()
				url = response.getheader('Location', '')
				if r == 0 or url == '': raise HTTPException('Too much or bad redirects')
				connection.request('GET', url, headers=headers)
				response = self.timeout_response(connection, timeout)
				r -= 1
			self.long_poll_url = response.getheader('X-Long-Polling', '')
			self.switch.update_time = bool(response.getheader('X-Roll-NTime', ''))
			hostList = response.getheader('X-Host-List', '')
			self.stratum_header = response.getheader('x-stratum', '')
			if (not self.options.nsf) and hostList: self.switch.add_servers(loads(hostList))
			result = loads(response.read())
			if result['error']:
				say_line('server error: %s', result['error']['message'])
				raise RPCError(result['error']['message'])
			return (connection, result)
		finally:
			if not result or not response or (response.version == 10 and response.getheader('connection', '') != 'keep-alive') or response.getheader('connection', '') == 'close':
				connection.close()
				connection = None

	def timeout_response(self, connection, timeout):
		if timeout:
			start = time()
			connection.sock.settimeout(5)
			response = None
			while not response:
				if self.should_stop or time() - start > timeout: return
				try:
					response = connection.getresponse()
				except socket.timeout:
					pass
			connection.sock.settimeout(timeout)
			return response
		else:
			return connection.getresponse()

	def getwork(self, data=None):
		try:
			self.connection = self.ensure_connected(self.connection, self.server().proto, self.server().host)[0]
			self.postdata['params'] = if_else(data, [data], [])
			(self.connection, result) = self.request(self.connection, '/', self.headers, dumps(self.postdata))

			self.switch.connection_ok()

			return result['result']
		except (IOError, httplib.HTTPException, ValueError, socks.ProxyError, NotAuthorized, RPCError):
			self.stop()
		except Exception:
			say_exception()

	def send_internal(self, result, nonce):
		data = ''.join([result.header.encode('hex'), pack('III', long(result.time), long(result.difficulty), long(nonce)).encode('hex'), '000000800000000000000000000000000000000000000000000000000000000000000000000000000000000080020000'])
		accepted = self.getwork(data)
		if accepted != None:
			self.switch.report(result.miner, nonce, accepted)
			return True

	def long_poll_thread(self):
		last_host = None
		while True:
			if self.should_stop or self.authorization_failed:
				return

			url = self.long_poll_url
			if url != '':
				proto = self.server().proto
				host = self.server().host
				parsedUrl = urlsplit(url)
				if parsedUrl.scheme != '':
					proto = parsedUrl.scheme
				if parsedUrl.netloc != '':
					host = parsedUrl.netloc
					url = url[url.find(host) + len(host):]
					if url == '': url = '/'
				try:
					if host != last_host: self.close_lp_connection()
					self.lp_connection, changed = self.ensure_connected(self.lp_connection, proto, host)
					if changed:
						say_line("LP connected to %s", self.server().name)
						last_host = host

					self.long_poll_active = True
					response = self.request(self.lp_connection, url, self.headers, timeout=self.long_poll_timeout)
					self.long_poll_active = False
					if response:
						(self.lp_connection, result) = response
						self.queue_work(result['result'])
						if self.options.verbose:
							say_line('long poll: new block %s%s', (result['result']['data'][56:64], result['result']['data'][48:56]))
				except (IOError, httplib.HTTPException, ValueError, socks.ProxyError, NotAuthorized, RPCError):
					say_exception('long poll IO error')
					self.close_lp_connection()
					sleep(.5)
				except Exception:
					say_exception()

	def stop(self):
		self.should_stop = True
		self.close_lp_connection()
		self.close_connection()

	def close_connection(self):
		if self.connection:
			self.connection.close()
			self.connection = None

	def close_lp_connection(self):
		if self.lp_connection:
			self.lp_connection.close()
			self.lp_connection = None

	def queue_work(self, work, miner=None):
		if work:
			if not 'target' in work:
				work['target'] = '0000000000000000000000000000000000000000000000000000ffff00000000'

			self.switch.queue_work(self, work['data'], work['target'], miner=miner)

	def detect_stratum(self):
		work = self.getwork()
		if self.authorization_failed:
			return False

		if work:
			if self.stratum_header:
				host = self.stratum_header
				proto = host.find('://')
				if proto != -1:
					host = self.stratum_header[proto+3:]
				#this doesn't work in windows/python 2.6
				#host = urlparse.urlparse(self.stratum_header).netloc
				say_line('diverted to stratum on %s', host)
				return host
			else:
				say_line('using JSON-RPC (no stratum header)')
				self.queue_work(work)
				return False

		say_line('no response to getwork, using as stratum')
		return self.server().host