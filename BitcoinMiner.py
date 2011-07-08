import sys
import socket
import httplib
import traceback
import collections

import pyopencl as cl

from sha256 import *
from hashlib import md5
from base64 import b64encode
from decimal import Decimal
from time import sleep, time
from json import dumps, loads
from datetime import datetime
from urlparse import urlsplit
from Queue import Queue, Empty
from struct import pack, unpack, error
from threading import Thread, RLock

# Socket wrapper to enable socket.TCP_NODELAY and KEEPALIVE
realsocket = socket.socket
def socketwrap(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
	sockobj = realsocket(family, type, proto)
	sockobj.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
	sockobj.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
	return sockobj
socket.socket = socketwrap


VERSION = '2011.b7'

USER_AGENT = 'poclbm/' + VERSION

TIME_FORMAT = '%d/%m/%Y %H:%M:%S'

TIMEOUT = 5

LONG_POLL_TIMEOUT = 3600

LONG_POLL_MAX_ASKRATE = 60 - TIMEOUT

MAX_REDIRECTS = 3

OUTPUT_SIZE = 0x100


def belowOrEquals(hash, target):
	for i in range(len(hash) - 1, -1, -1):
		reversed = bytereverse(hash[i])
		if reversed < target[i]:
			return True
		elif reversed > target[i]:
			return False
	return True

def if_else(condition, trueVal, falseVal):
	if condition:
		return trueVal
	else:
		return falseVal

def chunks(l, n):
	for i in xrange(0, len(l), n):
		yield l[i:i+n]

def patch(data):
	pos = data.find('\x7fELF', 1)
	if pos != -1 and data.find('\x7fELF', pos+1) == -1:
		data2 = data[pos:]
		try:
			(id, a, b, c, d, e, f, offset, g, h, i, j, entrySize, count, index) = unpack('QQHHIIIIIHHHHHH', data2[:52])
			if id == 0x64010101464c457f and offset != 0:
				(a, b, c, d, nameTableOffset, size, e, f, g, h) = unpack('IIIIIIIIII', data2[offset+index * entrySize : offset+(index+1) * entrySize])
				header = data2[offset : offset+count * entrySize]
				firstText = True
				for i in xrange(count):
					entry = header[i * entrySize : (i+1) * entrySize]
					(nameIndex, a, b, c, offset, size, d, e, f, g) = unpack('IIIIIIIIII', entry)
					nameOffset = nameTableOffset + nameIndex
					name = data2[nameOffset : data2.find('\x00', nameOffset)]
					if name == '.text':
						if firstText: firstText = False
						else:
							data2 = data2[offset : offset + size]
							patched = ''
							for i in xrange(len(data2) / 8):
								instruction, = unpack('Q', data2[i * 8 : i * 8 + 8])
								if (instruction&0x9003f00002001000) == 0x0001a00000000000:
									instruction ^= (0x0001a00000000000 ^ 0x0000c00000000000)
								patched += pack('Q', instruction)
							return ''.join([data[:pos+offset], patched, data[pos + offset + size:]])
		except error:
			pass
	return data

class NotAuthorized(Exception): pass
class RPCError(Exception): pass

class BitcoinMiner():
	def __init__(self, device, options):
		self.options = options
		(self.defines, self.rateDivisor, self.hashspace) = if_else(self.options.vectors, ('-DVECTORS', 500, 0x7FFFFFFF), ('', 1000, 0xFFFFFFFF))
		self.defines += (' -DOUTPUT_SIZE=' + str(OUTPUT_SIZE))
		self.defines += (' -DOUTPUT_MASK=' + str(OUTPUT_SIZE - 1))

		self.device = device
		self.options.rate = max(self.options.rate, 0.1)
		self.options.askrate = max(self.options.askrate, 1)
		self.options.askrate = min(self.options.askrate, 10)
		self.options.frames = max(self.options.frames, 3)
		self.longPollActive = self.stop = False
		self.update = True
		self.lock = RLock()
		self.outputLock = RLock()
		self.lastWork = 0
		self.lastBlock = self.updateTime = self.longPollURL = ''

		self.shareCount = [0, 0]

		self.workQueue = Queue()
		self.resultQueue = Queue()

		self.backup_pool_index = 1
		self.errors = 0
		self.failback_getwork_count = 0
		self.failback_attempt_count = 0
		self.pool = None

		self.postdata = {'method': 'getwork', 'id': 'json'}
		self.connection = None

		self.servers = []
		for pool in self.options.servers.split(','):
			try:
				temp = pool.split('://', 1)
				if len(temp) == 1:
					proto = ''; temp = temp[0]
				else: proto = temp[0]; temp = temp[1]
				user, temp = temp.split(':', 1)
				pwd, host = temp.split('@')
				self.servers.append((proto, user, pwd, host))
			except ValueError:
				self.sayLine("Ignored invalid server entry: '%s'", pool)
				continue
		if not self.servers:
			self.failure('At least one server is required')
		else: self.setpool(self.servers[0])

	def say(self, format, args=(), sayQuiet=False):
		if self.options.quiet and not sayQuiet: return
		with self.outputLock:
			p = format % args
			pool = self.pool[3]+' ' if self.pool else ''
			if self.options.verbose:
				print '%s%s,' % (pool, datetime.now().strftime(TIME_FORMAT)), p
			else:
				sys.stdout.write('\r%s\r%s%s' % (' '*80, pool, p))
			sys.stdout.flush()

	def sayLine(self, format, args=()):
		if not self.options.verbose:
			format = '%s, %s\n' % (datetime.now().strftime(TIME_FORMAT), format)
		self.say(format, args)
		
	def sayQuiet(self, format, args=()):
		self.say(format, args, True)

	def exit(self):
		self.stop = True

	def sayStatus(self, rate, estRate):
		rate = Decimal(rate) / 1000
		estRate = Decimal(estRate) / 1000
		totShares = self.shareCount[1] + self.shareCount[0]
		totSharesE = max(totShares, totShares, 1)
		self.sayQuiet('[%.03f MH/s (~%d MH/s)] [Rej: %d/%d (%d%%)]', (rate, round(estRate), self.shareCount[0], totShares, self.shareCount[0] * 100 / totSharesE))

	def failure(self, message):
		print '\n%s' % message
		self.exit()

	def diff1Found(self, hash, target):
		if self.options.verbose and target < 0xFFFF0000L:
			self.sayLine('checking %s <= %s', (hash, target))

	def blockFound(self, hash, accepted):
		self.sayLine('%s, %s', (hash, if_else(accepted, 'accepted', '_rejected_')))

	def mine(self):
		longPollThread = Thread(target=self.longPollThread)
		longPollThread.daemon = True
		longPollThread.start()
		Thread(target=self.miningThread).start()

		while True:
			if self.stop: return
			try:
				with self.lock:
					update = self.update = (self.update or time() - self.lastWork > if_else(self.longPollActive, LONG_POLL_MAX_ASKRATE, self.options.askrate))
				if update:
					work = self.getwork()
					if self.update:
						self.queueWork(work)

				while not self.resultQueue.empty():
					result = self.resultQueue.get(False)
					with self.lock:
						rv = self.sendResult(result)
				sleep(1)
			except Exception:
				self.sayLine("Unexpected error:")
				traceback.print_exc()

	def prepareWork(self, work):
		if isinstance(work, collections.Iterable):
			p = work['p'] = {}

			if not 'target' in work: work['target'] = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffff00000000'

			data0 = np.zeros(64, np.uint32)
			data0 = np.insert(data0, [0] * 16, unpack('IIIIIIIIIIIIIIII', work['data'][:128].decode('hex')))
			p['data']   =             np.array(unpack('IIIIIIIIIIIIIIII', work['data'][128:].decode('hex')), dtype=np.uint32)
			p['target'] =             np.array(unpack('IIIIIIII',         work['target'].decode('hex')),     dtype=np.uint32)
			p['state']  =             sha256(STATE, data0)

			p['targetQ']= 2**256 / int(''.join(list(chunks(work['target'], 8))[::-1]), 16)
			p['f'] = np.zeros(8, np.uint32)
			p['state2'] = partial(p['state'], p['data'], p['f'])
			calculateF(p['state'], p['data'], p['f'], p['state2'])

	def queueWork(self, work):
		self.prepareWork(work)
		with self.lock:
			self.workQueue.put(work)
			if work:
				self.update = False; self.lastWork = time()
				if self.lastBlock != work['data'][48:56]:
					self.lastBlock = work['data'][48:56]
					while not self.resultQueue.empty():
						self.resultQueue.get(False)

	def sendResult(self, result):
		for i in xrange(OUTPUT_SIZE):
			if result['output'][i]:
				h = hash(result['state'], result['data'][0], result['data'][1], result['data'][2], result['output'][i])
				if h[7] != 0:
					self.failure('Verification failed, check hardware!')
				else:
					self.diff1Found(bytereverse(h[6]), result['target'][6])
					if belowOrEquals(h[:7], result['target'][:7]):
						d = result['work']['data']
						d = ''.join([d[:136], pack('I', long(result['data'][1])).encode('hex'), d[144:152], pack('I', long(result['output'][i])).encode('hex'), d[160:]])
						hashid = pack('I', long(h[6])).encode('hex')
						accepted = self.getwork(d)
						if accepted != None:
							self.blockFound(hashid, accepted)
							self.shareCount[if_else(accepted, 1, 0)] += 1

	def connect(self, proto, host, timeout):
		if proto == 'https': connector = httplib.HTTPSConnection
		else: connector = httplib.HTTPConnection
		return connector(host, strict=True, timeout=timeout)

	def getwork(self, data=None):
		save_pool = None
		try:
			if self.pool != self.servers[0] and self.options.failback > 0:
				if self.failback_getwork_count >= self.options.failback:
					save_pool = self.pool
					self.setpool(self.servers[0])
					self.connection = None
					self.sayLine("Attempting to fail back to primary pool")
				self.failback_getwork_count += 1
			if not self.connection:
				self.connection = self.connect(self.proto, self.host, TIMEOUT)
			self.postdata['params'] = if_else(data, [data], [])
			(self.connection, result) = self.request(self.connection, '/', self.headers, dumps(self.postdata))
			self.errors = 0
			if self.pool == self.servers[0]:
				self.backup_pool_index = 1
				self.failback_getwork_count = 0
				self.failback_attempt_count = 0
			return result['result']
		except NotAuthorized:
			self.failure('Wrong username or password')
		except RPCError as e:
			self.say('%s', e)
		except (IOError, httplib.HTTPException, ValueError):
			if save_pool:
				self.failback_attempt_count += 1
				self.setpool(save_pool)
				self.sayLine('Still unable to reconnect to primary pool (attempt %s), failing over', self.failback_attempt_count)
				self.failback_getwork_count = 0
				return
			self.say('Problems communicating with bitcoin RPC %s %s', (self.errors, self.options.tolerance))
			self.errors += 1
			if self.errors > self.options.tolerance+1:
				self.errors = 0
				if self.backup_pool_index >= len(self.servers):
					self.sayLine("No more backup pools left. Using primary and starting over.")
					pool = self.servers[0]
					self.backup_pool_index = 1
				else:
					pool = self.servers[self.backup_pool_index]
					self.backup_pool_index += 1
				self.setpool(pool)

	def setpool(self, pool):
		self.pool = pool
		proto, user, pwd, host = pool
		self.proto = proto
		self.host = host
		self.sayLine('Setting pool %s @ %s', (user, host))
		self.headers = {"User-Agent": USER_AGENT, "Authorization": 'Basic ' + b64encode('%s:%s' % (user, pwd))}
		self.connection = None

	def request(self, connection, url, headers, data=None):
		result = response = None
		try:
			if data: connection.request('POST', url, data, headers)
			else: connection.request('GET', url, headers=headers)
			response = connection.getresponse()
			if response.status == httplib.UNAUTHORIZED: raise NotAuthorized()
			r = MAX_REDIRECTS
			while response.status == httplib.TEMPORARY_REDIRECT:
				response.read()
				url = response.getheader('Location', '')
				if r == 0 or url == '': raise HTTPException('Too much or bad redirects')
				connection.request('GET', url, headers=headers)
				response = connection.getresponse();
				r -= 1
			self.longPollURL = response.getheader('X-Long-Polling', '')
			self.updateTime = response.getheader('X-Roll-NTime', '')
			result = loads(response.read())
			if result['error']:	raise RPCError(result['error']['message'])
			return (connection, result)
		finally:
			if not result or not response or (response.version == 10 and response.getheader('connection', '') != 'keep-alive') or response.getheader('connection', '') == 'close':
				connection.close()
				connection = None

	def longPollThread(self):
		connection = None
		last_url = None
		while True:
			if self.stop: return
			sleep(1)
			url = self.longPollURL
			if url != '':
				proto = self.proto
				host = self.host
				parsedUrl = urlsplit(url)
				if parsedUrl.scheme != '':
					proto = parsedUrl.scheme
				if parsedUrl.netloc != '':
					host = parsedUrl.netloc
					url = url[url.find(host)+len(host):]
					if url == '': url = '/'
				try:
					if not connection:
						connection = self.connect(proto, host, LONG_POLL_TIMEOUT)
						self.sayLine("LP connected to %s", host)
					self.longPollActive = True
					(connection, result) = self.request(connection, url, self.headers)
					self.longPollActive = False
					self.queueWork(result['result'])
					self.sayLine('long poll: new block %s%s', (result['result']['data'][56:64], result['result']['data'][48:56]))
					last_url = self.longPollURL
				except NotAuthorized:
					self.sayLine('long poll: Wrong username or password')
				except RPCError as e:
					self.sayLine('long poll: %s', e)
				except (IOError, httplib.HTTPException, ValueError):
					self.sayLine('long poll exception:')
					traceback.print_exc()

	def miningThread(self):
		self.loadKernel()
		frame = 1.0 / self.options.frames
		unit = self.options.worksize * 256
		globalThreads = unit * 10
		
		queue = cl.CommandQueue(self.context)

		startTime = lastRatedPace = lastRated = lastNTime = time()
		accepted = base = lastHashRate = threadsRunPace = threadsRun = 0
		acceptHist = []
		output = np.zeros(OUTPUT_SIZE+1, np.uint32)
		output_buf = cl.Buffer(self.context, cl.mem_flags.WRITE_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=output)

		work = None
		while True:
		        sleep(self.options.frameSleep)
			if self.stop: return
			if (not work) or (not self.workQueue.empty()):
				try:
					work = self.workQueue.get(True, 1)
				except Empty: continue
				else:
					if not work: continue

					noncesLeft = self.hashspace

					data = work['p']['data']
					state = work['p']['state']
					state2 = work['p']['state2']
					f = work['p']['f']

			self.miner.search(	queue, (globalThreads, ), (self.options.worksize, ),
								state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
								state2[1], state2[2], state2[3], state2[5], state2[6], state2[7],
								pack('I', base),
								f[0], f[1], f[2], f[3], f[4],# f[5], f[6], f[7],
								output_buf)
			cl.enqueue_read_buffer(queue, output_buf, output)

			noncesLeft -= globalThreads
			threadsRunPace += globalThreads
			threadsRun += globalThreads
			base = uint32(base + globalThreads)

			now = time()
			t = now - lastRatedPace
			if (t > 1):
				rate = (threadsRunPace / t) / self.rateDivisor
				lastRatedPace = now; threadsRunPace = 0
				r = lastHashRate / rate
				if r < 0.9 or r > 1.1:
					globalThreads = max(unit * int((rate * frame * self.rateDivisor) / unit), unit)
					lastHashRate = rate
			t = now - lastRated
			if (t > self.options.rate):
				rate = int((threadsRun / t) / self.rateDivisor)

				if (len(acceptHist)):
					LAH = acceptHist.pop()
					if LAH[1] != self.shareCount[1]:
						acceptHist.append(LAH)
				acceptHist.append( (now, self.shareCount[1]) )
				while (acceptHist[0][0] < now - self.options.estimate):
					acceptHist.pop(0)
				newAccept = self.shareCount[1] - acceptHist[0][1]
				estRate = Decimal(newAccept) * (work['p']['targetQ']) / min(int(now - startTime), self.options.estimate) / 1000

				self.sayStatus(rate, estRate)
				lastRated = now; threadsRun = 0

			queue.finish()

			if output[OUTPUT_SIZE]:
				result = {}
				result['work'] = work
				result['data'] = np.array(data)
				result['state'] = np.array(state)
				result['target'] = work['p']['target']
				result['output'] = np.array(output)
				self.resultQueue.put(result)
				output.fill(0)
				cl.enqueue_write_buffer(queue, output_buf, output)

			if self.updateTime == '':
				if noncesLeft < (TIMEOUT+1) * globalThreads * self.options.frames:
					self.update = True
					noncesLeft += 0xFFFFFFFFFFFF
				elif 0xFFFFFFFFFFF < noncesLeft < 0xFFFFFFFFFFFF:
					self.sayLine('warning: job finished, miner is idle')
					work = None
			elif now - lastNTime > 1:
				data[1] = bytereverse(bytereverse(data[1]) + 1)
				state2 = partial(state, data, f)
				calculateF(state, data, f, state2)
				lastNTime = now

	def loadKernel(self):
		self.context = cl.Context([self.device], None, None)
		if (self.device.extensions.find('cl_amd_media_ops') != -1):
			self.defines += ' -DBITALIGN'
			self.defines += ' -DBFI_INT'

		kernelFile = open('phatk.cl', 'r')
		kernel = kernelFile.read()
		kernelFile.close()
		m = md5(); m.update(''.join([self.device.platform.name, self.device.platform.version, self.device.name, self.defines, kernel]))
		cacheName = '%s.elf' % m.hexdigest()
		binary = None
		try:
			binary = open(cacheName, 'rb')
			self.miner = cl.Program(self.context, [self.device], [binary.read()]).build(self.defines)
		except (IOError, cl.LogicError):
			self.miner = cl.Program(self.context, kernel).build(self.defines)
			if (self.defines.find('-DBITALIGN') != -1):
				patchedBinary = patch(self.miner.binaries[0])
				self.miner = cl.Program(self.context, [self.device], [patchedBinary]).build(self.defines)
			binaryW = open(cacheName, 'wb')
			binaryW.write(self.miner.binaries[0])
			binaryW.close()
		finally:
			if binary: binary.close()

		if (self.options.worksize == -1):
			self.options.worksize = self.miner.search.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, self.device)
