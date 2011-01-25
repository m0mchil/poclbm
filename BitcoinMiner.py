import sys
import socket
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


def uint32(x):
	return x & 0xffffffffL

def rotr(x, y):
	return (x>>y | x<<(32-y))

def rot(x, y):
	return (x<<y | x>>(32-y))
	
def sharound(a,b,c,d,e,f,g,h,x,K):
	t1=h+(rot(e, 26)^rot(e, 21)^rot(e, 7))+(g^(e&(f^g)))+K+x
	t2=(rot(a, 30)^rot(a, 19)^rot(a, 10))+((a&b)|(c&(a|b)))
	return (uint32(d + t1), uint32(t1+t2))

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
						accepted = self.getwork(result['data'])
						if accepted != None:
							self.blockFound(pack('I', long(result['hash'])).encode('hex'), accepted)
						else:
							self.resultQueue.put(result)
						result = None
			except KeyboardInterrupt:
				print '\nbye'
				self.workQueue.put('stop')
				sleep(1.1)
				break
			except:
				self.sayLine("Unexpected error: %s", sys.exc_info()[0])

	def run(self):
		frame = float(1)/float(self.frames)
		window = frame/30
		upper = frame + window
		lower = frame - window

		unit = self.worksize * 256
		globalThreads = unit
		
		queue = cl.CommandQueue(self.context)

		base = lastRate = threadsRun = 0
		f = np.zeros(8, dtype=np.uint32)
		output = np.zeros(2, np.uint32)
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
						self.say('disconnected')
						continue
					elif work == 'stop':
						return
					try:
						data   = np.array(unpack('IIIIIIIIIIIIIIII', work['data'][128:].decode('hex')), dtype=np.uint32)
						state  = np.array(unpack('IIIIIIII',         work['midstate'].decode('hex')),   dtype=np.uint32)
						target = np.array(unpack('IIIIIIII',         work['target'].decode('hex')),     dtype=np.uint32)
					except Exception as e:
						self.sayLine('Wrong data format from RPC!')
						sys.exit()
					state2 = np.array(state)
					(state2[3], state2[7]) = sharound(state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],state2[6],state2[7],data[0],0x428A2F98)
					(state2[2], state2[6]) = sharound(state2[7],state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],state2[6],data[1],0x71374491)
					(state2[1], state2[5]) = sharound(state2[6],state2[7],state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],data[2],0xB5C0FBCF)

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
								target[6], target[7],
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
				result['data'] = work['data'][:152] + pack('I', long(output[1])).encode('hex') + work['data'][160:]
				result['hash'] = output[0]
				self.resultQueue.put(result)
				output[0] = 0
				cl.enqueue_write_buffer(queue, output_buf, output)

			if (kernelTime < lower):
				globalThreads += unit
			elif (kernelTime > upper and globalThreads > unit):
				globalThreads -= unit