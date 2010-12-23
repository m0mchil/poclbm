import sys
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

def rot(x, y):
	return (x<<y | x>>(32-y))
	
def sharound(a,b,c,d,e,f,g,h,x,K):
	t1=h+(rot(e, 26)^rot(e, 21)^rot(e, 7))+(g^(e&(f^g)))+K+x
	t2=(rot(a, 30)^rot(a, 19)^rot(a, 10))+((a&b)|(c&(a|b)))
	return (uint32(d + t1), uint32(t1+t2))

def partial(state, data):
	partial = np.array(state)
	(partial[3], partial[7]) = sharound(partial[0],partial[1],partial[2],partial[3],partial[4],partial[5],partial[6],partial[7],data[0],0x428A2F98)
	(partial[2], partial[6]) = sharound(partial[7],partial[0],partial[1],partial[2],partial[3],partial[4],partial[5],partial[6],data[1],0x71374491)
	(partial[1], partial[5]) = sharound(partial[6],partial[7],partial[0],partial[1],partial[2],partial[3],partial[4],partial[5],data[2],0xB5C0FBCF)
	return partial

def if_else(condition, trueVal, falseVal):
	if condition:
		return trueVal
	else:
		return falseVal

def bytereverse(x):
	return uint32(( ((x) << 24) | (((x) << 8) & 0x00ff0000) | (((x) >> 8) & 0x0000ff00) | ((x) >> 24) ))

class BitcoinMiner(Thread):
	def __init__(self, platform, context, host, user, password, port=8332, frames=60, rate=1, askrate=5, worksize=-1, vectors=False):
		Thread.__init__(self)
		(defines, self.rateDivisor) = if_else(vectors, ('-DVECTORS', 500), ('', 1000))

		self.context = context
		self.rate = float(rate)
		self.askrate = int(askrate)
		self.worksize = int(worksize)
		self.frames = frames

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

	def mine(self):
		self.start()

		lastWork = 0
		work = result = None
		try:
			while True:
				if not work:
					try:
						work = self.bitcoin.getwork()
					except JSONRPCException, e:
						self.say('%s', e.error['message'])
					except (JSONDecodeException, IOError):
						self.say('Problems communicating with bitcoin RPC')

				try:
					result = self.resultQueue.get(True, 1)
				except Empty:
					pass

				if result or (time() - lastWork > self.askrate):
					self.workQueue.put(work)
					lastWork = time()
					work = None
					if result:
						try:
							accepted = self.bitcoin.getwork(result['data'])
						except (JSONDecodeException, IOError):
							self.say('Problems communicating with bitcoin RPC')
						else:
							self.blockFound(pack('I', long(result['hash'])).encode('hex'), accepted)
						result = None
		except KeyboardInterrupt:
			self.workQueue.put('stop')
			print '\nbye'
			sleep(0.1)

	def run(self):
		frame = float(1)/float(self.frames)
		window = frame/30
		upper = frame + window
		lower = frame - window

		unit = self.worksize * 256
		globalThreads = unit
		
		queue = cl.CommandQueue(self.context)

		base = lastRate = threadsRun = lastNTime = 0
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
						continue
					elif work == 'stop':
						return
					try:
						data   = np.array(unpack('IIIIIIIIIIIIIIII', work['data'][128:].decode('hex')), dtype=np.uint32)
						state  = np.array(unpack('IIIIIIII',         work['midstate'].decode('hex')),   dtype=np.uint32)
						target = np.array(unpack('IIIIIIII',         work['target'].decode('hex')),     dtype=np.uint32)
						state2 = partial(state, data)
					except Exception as e:
						self.sayLine('Wrong data format from RPC!')
						sys.exit()

			kernelStart = time()
			self.miner.search(	queue, (globalThreads, ), (self.worksize, ),
								data[0], data[1], data[2],
								state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
								state2[1], state2[2], state2[3], state2[5], state2[6], state2[7],
								target[6], target[7], pack('I', base), output_buf)
			cl.enqueue_read_buffer(queue, output_buf, output)

			if (time() - lastRate > self.rate):
				self.say('%s khash/s', int((threadsRun / (time() - lastRate)) / self.rateDivisor))
				threadsRun = 0
				lastRate = time()

			queue.finish()
			kernelTime = time() - kernelStart

			threadsRun += globalThreads
			base = uint32(base + globalThreads)

			if (kernelTime < lower):
				globalThreads += unit
			elif (kernelTime > upper and globalThreads > unit):
				globalThreads -= unit

			if output[0]:
				result = {}
				d = work['data']
				d = d[:136] + pack('I', long(data[1])).encode('hex') + d[144:152] + pack('I', long(output[1])).encode('hex') + d[160:]
				result['data'] = d
				result['hash'] = output[0]
				self.resultQueue.put(result)
				output[0] = 0
				cl.enqueue_write_buffer(queue, output_buf, output)

			if (time() - lastNTime > 1):
				data[1] = bytereverse(bytereverse(data[1]) + 1)
				state2 = partial(state, data)
				lastNTime = time()