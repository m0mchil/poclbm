#!/usr/bin/python

import sys
import numpy as np
import pyopencl as cl

from struct import *
from time import sleep, time
from datetime import datetime
from jsonrpc import ServiceProxy
from jsonrpc.proxy import JSONRPCException


def uint32(x):
        return x & 0xffffffffL

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

class BitcoinMiner:
        def __init__(self, platform, context, host, user, password, port=8332, frames=60, rate=10, askrate=5, worksize=-1, vectors=False):
                (defines, self.maxBase, self.rateDivisor) = if_else(vectors, ('-DVECTORS', 0x7fffffff, 500), ('', 0xffffffff, 1000))

                self.context = context
                self.rate = int(rate)
                self.askrate = int(askrate)
                self.worksize = int(worksize)
                
                if (platform.name.lower().find('nvidia') != -1):
                        defines += ' -DNVIDIA'
                elif (self.context.devices[0].extensions.find('cl_amd_media_ops') != -1):
                        defines += ' -DBITALIGN'
                        
                kernelFile = open('btc_miner.cl', 'r')
                self.miner = cl.Program(self.context, kernelFile.read()).build(defines)
                kernelFile.close()

                if (self.worksize == -1):
                        self.worksize = self.miner.search.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, self.context.devices[0])

                frame = float(1)/float(frames)
                window = frame/30
                self.upper = frame + window
                self.lower = frame - window

                self.unit = self.worksize * 256
                self.globalThreads = self.unit

                self.bitcoin = ServiceProxy('http://%s:%s@%s:%s' % (user, password, host, port))

        def say(self, format, args=()):
                sys.stdout.write('\r                                        \r' + format % args)
                sys.stdout.flush()

        def sayLine(self, format, args=()):
                sysWrite(format + '\n', args)

        def blockFound(self, output):
                # designed to be overridden
                self.sayLine('found: %s, %s', (output, datetime.now().strftime("%d/%m/%Y %H:%M")))
        
        def mine(self):
                work = {}
                work['data'] = ''
                output = np.zeros(2, np.uint32)

                queue = cl.CommandQueue(self.context)
                
                threadsRun = 0
                lastRate = time()

                while True:
                        try:
                                work = self.bitcoin.getwork()
                        except JSONRPCException, e:
                                self.say('%s', e.error['message'])
                                sleep(2)
                                continue
                        except IOError:
                                self.say('Unable to communicate with bitcoin RPC')
                                sleep(2)
                                continue
                        
                        try:
                                block2 = np.array(unpack('IIIIIIIIIIIIIIII', work['data'][128:].decode('hex')), dtype=np.uint32)
                                state  = np.array(unpack('IIIIIIII',         work['midstate'].decode('hex')),       dtype=np.uint32)
                                target = np.array(unpack('IIIIIIII',         work['target'].decode('hex')),      dtype=np.uint32)
                        except:
                                sayLine('Wrong data format from RPC!')
                                sys.exit()
	
                        state2 = np.array(state)
                        (state2[3], state2[7]) = sharound(state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],state2[6],state2[7],block2[0],0x428A2F98)
                        (state2[2], state2[6]) = sharound(state2[7],state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],state2[6],block2[1],0x71374491)
                        (state2[1], state2[5]) = sharound(state2[6],state2[7],state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],block2[2],0xB5C0FBCF)

                        output[0] = base = 0
                        output_buf = cl.Buffer(self.context, cl.mem_flags.WRITE_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=output)

                        start = time()
                        while True:
                                if (output[0]):
                                        work['data'] = work['data'][:152] + pack('I', long(output[0])).encode('hex') + work['data'][160:]
                                        self.blockFound(output[0])
                                        self.bitcoin.getwork(work['data'])
                                        break

                                if (time() - start > self.askrate or base + self.globalThreads == self.maxBase):
                                        break

                                base += self.globalThreads
                                if (base + self.globalThreads > self.maxBase):
                                        base = self.maxBase - self.globalThreads

                                kernelStart = time()
                                self.miner.search(	queue, (self.globalThreads, ), (self.worksize, ),
						block2[0], block2[1], block2[2],
						state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
						state2[1], state2[2], state2[3], state2[5], state2[6], state2[7],
						target[6], pack('I', base), output_buf)
                                cl.enqueue_read_buffer(queue, output_buf, output).wait()
                                kernelTime = time() - kernelStart
                                threadsRun += self.globalThreads

                                if (kernelTime < self.lower):
                                        self.globalThreads += self.unit
                                elif (kernelTime > self.upper and self.globalThreads != self.unit):
                                        self.globalThreads -= self.unit

                                if (time() - lastRate > self.rate):
                                        self.say('%s khash/s', int((threadsRun / (time() - lastRate)) / self.rateDivisor))
                                        threadsRun = 0
                                        lastRate = time()
