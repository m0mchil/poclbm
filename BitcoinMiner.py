import sys
import socket
import httplib
import traceback

import pyopencl as cl

from sha256 import *
from hashlib import md5
from base64 import b64encode
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


VERSION = '2011.beta4'

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
	def __init__(self, device, host, user, password, port=8332, frames=30, rate=1, askrate=5, worksize=-1, vectors=False, verbose=False,
	    frameSleep=0):
		(self.defines, self.rateDivisor, self.hashspace) = if_else(vectors, ('-DVECTORS', 500, 0x7FFFFFFF), ('', 1000, 0xFFFFFFFF))
		self.defines += (' -DOUTPUT_SIZE=' + str(OUTPUT_SIZE))
		self.defines += (' -DOUTPUT_MASK=' + str(OUTPUT_SIZE - 1))

		self.device = device
		self.rate = max(float(rate), 0.1)
		self.askrate = max(int(askrate), 1)
		self.askrate = min(self.askrate, 10)
		self.worksize = int(worksize)
		self.frames = max(int(frames), 3)
		self.verbose = verbose
		self.frameSleep = frameSleep
		self.longPollActive = self.stop = False
		self.update = True
		self.lock = RLock()
		self.outputLock = RLock()
		self.lastWork = 0
		self.lastBlock = self.updateTime = self.longPollURL = ''

		self.workQueue = Queue()
		self.resultQueue = Queue()

		self.host = '%s:%s' % (host.replace('http://', ''), port)
		self.postdata = {"method": 'getwork', 'id': 'json'}
		self.headers = {"User-Agent": USER_AGENT, "Authorization": 'Basic ' + b64encode('%s:%s' % (user, password))}
		self.connection = None

	def say(self, format, args=()):
		with self.outputLock:
			if self.verbose:
				print '%s,' % datetime.now().strftime(TIME_FORMAT), format % args
			else:
				sys.stdout.write('\r                                                            \r%s' % (format % args))
			sys.stdout.flush()

	def sayLine(self, format, args=()):
		if not self.verbose:
			format = '%s, %s\n' % (datetime.now().strftime(TIME_FORMAT), format)
		self.say(format, args)

	def exit(self):
		self.stop = True

	def hashrate(self, rate):
		self.say('%s khash/s', rate)

	def failure(self, message):
		print '\n%s' % message
		self.exit()

	def diff1Found(self, hash, target):
		if self.verbose and target < 0xFFFF0000L:
			self.sayLine('checking %s <= %s', (hash, target))

	def blockFound(self, hash, accepted):
		self.sayLine('%s, %s', (hash, if_else(accepted, 'accepted', 'invalid or stale')))

	def mine(self):
		self.stop = False
		longPollThread = Thread(target=self.longPollThread)
		longPollThread.daemon = True
		longPollThread.start()
		Thread(target=self.miningThread).start()

		while True:
			if self.stop: return
			try:
				with self.lock:
					update = self.update = (self.update or time() - self.lastWork > if_else(self.longPollActive, LONG_POLL_MAX_ASKRATE, self.askrate))
				if update:
					work = self.getwork()
					with self.lock:
						if self.update:
							self.queueWork(work)

				with self.lock:
					if not self.resultQueue.empty():
						self.sendResult(self.resultQueue.get(False))
				sleep(1)
			except Exception:
				self.sayLine("Unexpected error:")
				traceback.print_exc()

	def queueWork(self, work):
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
						accepted = self.getwork(d)
						if accepted != None:
							self.blockFound(pack('I', long(h[6])).encode('hex'), accepted)

	def getwork(self, data=None):
		try:
			if not self.connection:
				self.connection = httplib.HTTPConnection(self.host, strict=True, timeout=TIMEOUT)
			self.postdata['params'] = if_else(data, [data], [])
			(self.connection, result) = self.request(self.connection, '/', self.headers, dumps(self.postdata))
			return result['result']
		except NotAuthorized:
			self.failure('Wrong username or password')
		except RPCError as e:
			self.say('%s', e)
		except (IOError, httplib.HTTPException, ValueError):
			self.say('Problems communicating with bitcoin RPC')

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
				connection.request('GET', url, headers=self.headers)
				response = connection.getresponse();
				r -= 1
			self.longPollURL = response.getheader('X-Long-Polling', '')
			self.updateTime = response.getheader('X-Roll-NTime', '')
			result = loads(response.read())
			if result['error']:	raise RPCError(result['error']['message'])
			return (connection, result)
		finally:
			if not result or not response or response.getheader('connection', '') != 'keep-alive':
				connection.close()
				connection = None

	def longPollThread(self):
		connection = None
		while True:
			if self.stop: return
			sleep(1)
			url = self.longPollURL
			if url != '':
				host = self.host
				parsedUrl = urlsplit(url)
				if parsedUrl.netloc != '':
					host = parsedUrl.netloc
					url = url[url.find(host)+len(host):]
					if url == '': url = '/'
				try:
					if not connection:
						connection = httplib.HTTPConnection(host, timeout=LONG_POLL_TIMEOUT)
					self.longPollActive = True
					(connection, result) = self.request(connection, url, self.headers)
					self.longPollActive = False
					self.queueWork(result['result'])
					self.sayLine('long poll: new block %s%s', (result['result']['data'][56:64], result['result']['data'][48:56]))
				except NotAuthorized:
					self.sayLine('long poll: Wrong username or password')
				except RPCError as e:
					self.sayLine('long poll: %s', e)
				except (IOError, httplib.HTTPException, ValueError):
					self.sayLine('long poll exception:')
					traceback.print_exc()

	def miningThread(self):
		self.loadKernel()
		frame = 1.0 / self.frames
		unit = self.worksize * 256
		globalThreads = unit * 10
		
		queue = cl.CommandQueue(self.context)

		lastRatedPace = lastRated = lastNTime = time()
		base = lastHashRate = threadsRunPace = threadsRun = 0
		f = np.zeros(8, np.uint32)
		output = np.zeros(OUTPUT_SIZE+1, np.uint32)
		output_buf = cl.Buffer(self.context, cl.mem_flags.WRITE_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=output)

		work = None
		while True:
		        sleep(self.frameSleep)
			if self.stop: return
			if (not work) or (not self.workQueue.empty()):
				try:
					work = self.workQueue.get(True, 1)
				except Empty: continue
				else:
					if not work: continue

					noncesLeft = self.hashspace
					data   = np.array(unpack('IIIIIIIIIIIIIIII', work['data'][128:].decode('hex')), dtype=np.uint32)
					state  = np.array(unpack('IIIIIIII',         work['midstate'].decode('hex')),   dtype=np.uint32)
					target = np.array(unpack('IIIIIIII',         work['target'].decode('hex')),     dtype=np.uint32)
					state2 = partial(state, data, f)

			self.miner.search(	queue, (globalThreads, ), (self.worksize, ),
								state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
								state2[1], state2[2], state2[3], state2[5], state2[6], state2[7],
								pack('I', base),
								f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7],
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
			if (t > self.rate):
				self.hashrate(int((threadsRun / t) / self.rateDivisor))
				lastRated = now; threadsRun = 0

			if self.updateTime == '':
				if noncesLeft < TIMEOUT * globalThreads * self.frames:
					self.update = True
					noncesLeft += 0xFFFFFFFFFFFF
				elif 0xFFFFFFFFFFF < noncesLeft < 0xFFFFFFFFFFFF:
					self.sayLine('warning: job finished, miner is idle')
					work = None

			queue.finish()

			if output[OUTPUT_SIZE]:
				result = {}
				result['work'] = work
				result['data'] = np.array(data)
				result['state'] = np.array(state)
				result['target'] = target
				result['output'] = np.array(output)
				self.resultQueue.put(result)
				output.fill(0)
				cl.enqueue_write_buffer(queue, output_buf, output)

			if self.updateTime != '' and now - lastNTime > 1:
				data[1] = bytereverse(bytereverse(data[1]) + 1)
				state2 = partial(state, data, f)
				lastNTime = now

	def loadKernel(self):
		self.context = cl.Context([self.device], None, None)
		if (self.device.extensions.find('cl_amd_media_ops') != -1):
			self.defines += ' -DBITALIGN'

		kernelFile = open('BitcoinMiner.cl', 'r')
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

		if (self.worksize == -1):
			self.worksize = self.miner.search.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, self.device)