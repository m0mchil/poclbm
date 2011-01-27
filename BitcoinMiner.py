import sys
import socket
import traceback
import numpy as np
import pyopencl as cl

from struct import *
from Queue import Queue
from Queue import Empty
from threading import Thread
from time import sleep, time
from datetime import datetime
from jsonrpc import ServiceProxy
from jsonrpc.proxy import JSONRPCException
from jsonrpc.json import JSONDecodeException

K = np.array(
	[0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
	0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
	0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
	0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
	0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
	0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
	0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
	0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2], np.uint32)

work = np.zeros(64, np.uint32)

def uint32(x):
	return x & 0xffffffffL

def bytereverse(x):
	return uint32(( ((x) << 24) | (((x) << 8) & 0x00ff0000) | (((x) >> 8) & 0x0000ff00) | ((x) >> 24) ))

def rotr(x, y):
	return (x>>y | x<<(32-y))

def rot(x, y):
	return (x<<y | x>>(32-y))

def R(x2, x7, x15, x16):
	return uint32((rot(x2,15)^rot(x2,13)^((x2)>>10)) + x7 + (rot(x15,25)^rot(x15,14)^((x15)>>3)) + x16)

def sharound(a,b,c,d,e,f,g,h,x,K):
	t1=h+(rot(e, 26)^rot(e, 21)^rot(e, 7))+(g^(e&(f^g)))+K+x
	t2=(rot(a, 30)^rot(a, 19)^rot(a, 10))+((a&b)|(c&(a|b)))
	return (uint32(d + t1), uint32(t1+t2))

def hash(midstate, data0, data1, data2, nonce):
	work[0]=data0
	work[1]=data1
	work[2]=data2
	work[3]=nonce
	work[4]=0x80000000
	work[5]=0x00000000
	work[6]=0x00000000
	work[7]=0x00000000
	work[8]=0x00000000
	work[9]=0x00000000
	work[10]=0x00000000
	work[11]=0x00000000
	work[12]=0x00000000
	work[13]=0x00000000
	work[14]=0x00000000
	work[4]=0x80000000
	work[15]=0x00000280
	state = np.copy(midstate)

	for i in xrange(64):
		if i > 15:
			work[i] = R(work[i-2], work[i-7], work[i-15], work[i-16])
		(state[~(i-4)&7], state[~(i-8)&7]) = sharound(state[(~(i-1)&7)],state[~(i-2)&7],state[~(i-3)&7],state[~(i-4)&7],state[~(i-5)&7],state[~(i-6)&7],state[~(i-7)&7],state[~(i-8)&7],work[i],K[i])

	work[0]=midstate[0]+state[0]
	work[1]=midstate[1]+state[1]
	work[2]=midstate[2]+state[2]
	work[3]=midstate[3]+state[3]
	work[4]=midstate[4]+state[4]
	work[5]=midstate[5]+state[5]
	work[6]=midstate[6]+state[6]
	work[7]=midstate[7]+state[7]
	work[8]=0x80000000
	work[9]=0x00000000
	work[10]=0x00000000
	work[11]=0x00000000
	work[12]=0x00000000
	work[13]=0x00000000
	work[14]=0x00000000
	work[15]=0x00000100

	state[0]=0x6a09e667
	state[1]=0xbb67ae85
	state[2]=0x3c6ef372
	state[3]=0xa54ff53a
	state[4]=0x510e527f
	state[5]=0x9b05688c
	state[6]=0x1f83d9ab
	state[7]=0x5be0cd19

	for i in xrange(62):
		if i > 15:
			work[i] = R(work[i-2], work[i-7], work[i-15], work[i-16])
		(state[~(i-4)&7], state[~(i-8)&7]) = sharound(state[(~(i-1)&7)],state[~(i-2)&7],state[~(i-3)&7],state[~(i-4)&7],state[~(i-5)&7],state[~(i-6)&7],state[~(i-7)&7],state[~(i-8)&7],work[i],K[i])

	return (uint32(state[6] + 0x1f83d9ab), uint32(state[7] + 0x5be0cd19))

def if_else(condition, trueVal, falseVal):
	if condition:
		return trueVal
	else:
		return falseVal

class BitcoinMiner(Thread):
	def __init__(self, platform, context, host, user, password, port=8332, frames=30, rate=1, askrate=5, worksize=-1, vectors=False):
		Thread.__init__(self)
		socket.setdefaulttimeout(5)
		(defines, self.rateDivisor) = if_else(vectors, ('-DVECTORS', 500), ('', 1000))

		self.context = context
		self.rate = float(rate)
		self.askrate = max(int(askrate), 1)
		self.askrate = min(self.askrate, 10)
		self.worksize = int(worksize)
		self.frames = max(frames, 1)

		if (self.context.devices[0].extensions.find('cl_amd_media_ops') != -1):
			defines += ' -DBITALIGN'
			
		kernelFile = open('BitcoinMiner.cl', 'r')
		self.miner = cl.Program(self.context, kernelFile.read()).build(defines)
		kernelFile.close()

		if (self.worksize == -1):
			self.worksize = self.miner.search.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, self.context.devices[0])

		self.workQueue = Queue()
		self.resultQueue = Queue()

		self.bitcoin = ServiceProxy('http://%s:%s@%s:%s' % (user, password, host, port))

	def say(self, format, args=()):
		sys.stdout.write('\r                                        \r' + format % args)
		sys.stdout.flush()

	def sayLine(self, format, args=()):
		self.say(format + '\n', args)

	def blockFound(self, hash, accepted):
		# designed to be overridden
		self.sayLine('%s, %s, %s', (datetime.now().strftime("%d/%m/%Y %H:%M"), hash, if_else(accepted, 'accepted', 'invalid or stale')))

	def getwork(self, data=None):
		try:
			if data:
				return self.bitcoin.getwork(data)
			else:
				return self.bitcoin.getwork()
		except JSONRPCException, e:
			self.say('%s', e.error['message'])
		except (JSONDecodeException, IOError):
			self.say('Problems communicating with bitcoin RPC')

	def mine(self):
		self.start()

		lastWork = 0
		work = result = None
		while True:
			try:
				if not work:
					work = self.getwork()

				try:
					result = self.resultQueue.get(True, 1)
				except Empty:
					pass

				if result or (time() - lastWork > self.askrate):
					self.workQueue.put(work)
					lastWork = time()
					work = None
					if result:
						(G, H) = hash(result['state'], result['data'][0], result['data'][1], result['data'][2], result['nonce'])
						if H != 0:
							self.sayLine('verification failed, check hardware!')
						elif bytereverse(G) <= result['target']:
							result['work']['data'] = result['work']['data'][:152] + pack('I', long(result['nonce'])).encode('hex') + result['work']['data'][160:]
							accepted = self.getwork(result['work']['data'])
							if accepted != None:
								self.blockFound(pack('I', long(G)).encode('hex'), accepted)
							else:
								self.resultQueue.put(result)
						result = None
			except KeyboardInterrupt:
				print '\nbye'
				self.workQueue.put('stop')
				sleep(1.1)
				break
			except:
				self.sayLine("Unexpected error:")
				traceback.print_exc()

	def run(self):
		frame = float(1)/float(self.frames)
		window = frame/30
		upper = frame + window
		lower = frame - window

		unit = self.worksize * 256
		globalThreads = unit
		
		queue = cl.CommandQueue(self.context)

		base = lastRate = threadsRun = 0
		f = np.zeros(8, np.uint32)
		output = np.zeros(1, np.uint32)
		output_buf = cl.Buffer(self.context, cl.mem_flags.WRITE_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=output)

		work = None
		while True:
			if (not work) or (not self.workQueue.empty()):
				try:
					work = self.workQueue.get(True, 1)
				except Empty:
					continue
				else:
					if not work:
						continue
					elif work == 'stop':
						return
					try:
						data   = np.array(unpack('IIIIIIIIIIIIIIII', work['data'][128:].decode('hex')), dtype=np.uint32)
						state  = np.array(unpack('IIIIIIII',         work['midstate'].decode('hex')),   dtype=np.uint32)
						target = np.array(unpack('IIIIIIII',         work['target'].decode('hex')),     dtype=np.uint32)
						(target[0], target[1]) = (uint32(0xFFFF0000), 0)
					except Exception as e:
						self.sayLine('Wrong data format from RPC!')
						sys.exit()
					state2 = np.array(state)
					for i in xrange(3):
						(state2[~(i-4)&7], state2[~(i-8)&7]) = sharound(state2[(~(i-1)&7)],state2[~(i-2)&7],state2[~(i-3)&7],state2[~(i-4)&7],state2[~(i-5)&7],state2[~(i-6)&7],state2[~(i-7)&7],state2[~(i-8)&7],data[i],K[i])

					f[0] = uint32(data[0] + (rotr(data[1], 7) ^ rotr(data[1], 18) ^ (data[1] >> 3)))
					f[1] = uint32(data[1] + (rotr(data[2], 7) ^ rotr(data[2], 18) ^ (data[2] >> 3)) + 0x01100000)
					f[2] = uint32(data[2] + (rotr(f[0], 17) ^ rotr(f[0], 19) ^ (f[0] >> 10)))
					f[3] = uint32(0x11002000 + (rotr(f[1], 17) ^ rotr(f[1], 19) ^ (f[1] >> 10)))
					f[4] = uint32(0x00000280 + (rotr(f[0], 7) ^ rotr(f[0], 18) ^ (f[0] >> 3)))
					f[5] = uint32(f[0] + (rotr(f[1], 7) ^ rotr(f[1], 18) ^ (f[1] >> 3)))
					f[6] = uint32(state[4] + (rotr(state2[1], 6) ^ rotr(state2[1], 11) ^ rotr(state2[1], 25)) + (state2[3] ^ (state2[1] & (state2[2] ^ state2[3]))) + 0xe9b5dba5)
					f[7] = uint32((rotr(state2[5], 2) ^ rotr(state2[5], 13) ^ rotr(state2[5], 22)) + ((state2[5] & state2[6]) | (state2[7] & (state2[5] | state2[6]))))

			kernelStart = time()
			self.miner.search(	queue, (globalThreads, ), (self.worksize, ),
								state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
								state2[1], state2[2], state2[3], state2[5], state2[6], state2[7],
								target[0], target[1],
								pack('I', base),
								f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7],
								output_buf)
			cl.enqueue_read_buffer(queue, output_buf, output)

			threadsRun += globalThreads
			base = uint32(base + globalThreads)

			if (time() - lastRate > self.rate):
				self.say('%s khash/s', int((threadsRun / (time() - lastRate)) / self.rateDivisor))
				threadsRun = 0
				lastRate = time()

			queue.finish()
			kernelTime = time() - kernelStart

			if output[0]:
				result = {}
				result['work'] = work
				result['data'] = data
				result['state'] = state
				result['target'] = target[6]
				result['nonce'] = output[0]
				self.resultQueue.put(result)
				output[0] = 0
				cl.enqueue_write_buffer(queue, output_buf, output)

			if (kernelTime < lower):
				globalThreads += unit
			elif (kernelTime > upper and globalThreads > unit):
				globalThreads -= unit