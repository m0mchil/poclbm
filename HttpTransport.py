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
import socket
import socks
import urlparse


class NotAuthorized(Exception): pass
class RPCError(Exception): pass

class HttpTransport(Transport):
	def __init__(self, servers, server):
		super(HttpTransport, self).__init__(servers, server)
		
		self.connection = self.lp_connection = None
		self.long_poll_timeout = 3600
		self.max_redirects = 3

		self.postdata = {'method': 'getwork', 'id': 'json'}
		self.headers = {"User-Agent": self.servers.user_agent, "Authorization": 'Basic ' + b64encode('%s:%s' % (self.user, self.pwd)), "X-Mining-Extensions": 'hostlist midstate rollntime'}
		self.long_poll_url = ''

		self.long_poll_active = False

	def loop(self):
		super(HttpTransport, self).loop()

		thread = Thread(target=self.long_poll_thread)
		thread.daemon = True
		thread.start()

		while True:
			if self.should_stop: return

			if self.check_failback():
				return True

			try:
				with self.servers.lock:
					miner = self.servers.updatable_miner()
					while miner:
						work = self.getwork()
						self.queue_work(work, miner)
						miner = self.servers.updatable_miner()

				while not self.result_queue.empty():
					result = self.result_queue.get(False)
					with self.servers.lock:
						self.servers.send(result, self.send_internal)
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

		proxy_proto, user, pwd, proxy_host, name = self.options.proxy
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
			if response.status == httplib.UNAUTHORIZED:
				say_line('Wrong username or password for %s', self.servers.server_name())
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
			self.servers.update_time = bool(response.getheader('X-Roll-NTime', ''))
			hostList = response.getheader('X-Host-List', '')
			self.stratum_header = response.getheader('x-stratum', '')
			if (not self.options.nsf) and hostList: self.servers.add_servers(loads(hostList))
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
			return response					
		else:
			return connection.getresponse()

	def getwork(self, data=None):
		try:
			self.connection = self.ensure_connected(self.connection, self.proto, self.host)[0]
			self.postdata['params'] = if_else(data, [data], [])
			(self.connection, result) = self.request(self.connection, '/', self.headers, dumps(self.postdata))

			self.servers.connection_ok()

			return result['result']
		except (IOError, httplib.HTTPException, ValueError, socks.ProxyError, NotAuthorized, RPCError):
			self.stop()

	def send_internal(self, result, nonce):
		data = ''.join([result.header.encode('hex'), pack('III', long(result.time), long(result.difficulty), long(nonce)).encode('hex'), '000000800000000000000000000000000000000000000000000000000000000000000000000000000000000080020000'])
		accepted = self.getwork(data)
		if accepted != None:
			self.servers.report(result.miner, nonce, accepted)

	def long_poll_thread(self):
		last_host = None
		while True:
			if self.should_stop:
				return

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
					self.lp_connection, changed = self.ensure_connected(self.lp_connection, proto, host)
					if changed:
						say_line("LP connected to %s", self.servers.server_name())
						last_host = host

					self.long_poll_active = True
					response = self.request(self.lp_connection, url, self.headers, timeout=self.long_poll_timeout)
					self.long_poll_active = False
					if response:
						(self.lp_connection, result) = response
						self.queue_work(result['result'])
						if self.options.verbose:
							say_line('long poll: new block %s%s', (result['result']['data'][56:64], result['result']['data'][48:56]))
				except Exception:
					say_exception()
				except (IOError, httplib.HTTPException, ValueError, socks.ProxyError, NotAuthorized, RPCError):
					say_exception('long poll IO error')
					self.close_lp_connection()
					sleep(.5)

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

			self.servers.queue_work(self, work['data'], work['target'], miner)

	def detect_stratum(self):
		work = self.getwork()

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
		return self.host