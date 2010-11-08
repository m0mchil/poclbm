#!/usr/bin/env python

from multiprocessing import Process
from configobj import ConfigObj

import os
import time
import logging as log

import sys
import numpy as np
import pyopencl as cl

from struct import *
from time import sleep, time
from datetime import datetime
from jsonrpc import ServiceProxy
from optparse import OptionParser
from jsonrpc.proxy import JSONRPCException

def uint32(x):
	return x & 0xffffffffL
def rot(x, y):
	return (x<<y | x>>(32-y))
def sharound(a,b,c,d,e,f,g,h,x,K):
	t1=h+(rot(e, 26)^rot(e, 21)^rot(e, 7))+(g^(e&(f^g)))+K+x
	t2=(rot(a, 30)^rot(a, 19)^rot(a, 10))+((a&b)|(c&(a|b)))
	return (uint32(d + t1), uint32(t1+t2))

def sysWrite(format, args=()):
	sys.stdout.write('\r                                        \r' + format % args)
	sys.stdout.flush()

def sysWriteLn(format, args=()):
	sysWrite(format + '\n', args)

def if_else(condition, trueVal, falseVal):
	if condition:
		return trueVal
	else:
		return falseVal

def worker(device, config):
    log.debug('Worker starting on device '+device)
    log.debug('Setting DISPLAY variable for device '+device)
    os.environ['DISPLAY'] = ':0.'+device
    log.debug('Confirming environment: '+os.environ['DISPLAY'])
    log.debug('Checking that device is found now that DISPLAY is set')

    defines = if_else(config['vectors']==1, '-DVECTORS', '')

    platform = cl.get_platforms()[0]

    devices = platform.get_devices()
    context = cl.Context([devices[1]], None, None)
    queue = cl.CommandQueue(context)
    if (platform.name.lower().find('nvidia') != -1):
	defines += ' -DNVIDIA'
    else:
	stream = platform.version.find('ATI-Stream')
	if(stream != -1 and float(platform.version[stream+12:stream+15]) < 2.2):
            defines += ' -DOLD_STREAM'

    kernelFile = open('btc_miner.cl', 'r')
    log.debug('Building miner. Defines = '+defines)
    miner = cl.Program(context, kernelFile.read()).build(defines)
    kernelFile.close()
    
    if (int(config['worksize']) == -1):
	config['worksize'] = miner.search.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, context.devices[0])

    work = {}
    work['extraNonce'] = 0
    work['block'] = ''
    output = np.zeros(2, np.uint32)

    threadsRun = 0
    rate = time()

    frames = float(config['frames'])
    frame = float(1)/frames
    window = frame/30
    upper = frame + window
    lower = frame - window

    maxBase = if_else(config['vectors']==1, 0x7fffffff, 0xffffffff)
    rateDivisor = if_else(config['vectors']==1, 500, 1000)
    unit = config['worksize'] * 256
    globalThreads = unit

    bitcoin = ServiceProxy('http://' + config['user'] + ':' + config['password'] + '@' + config['hostname'] + ':' + config['port'])

    while True:
	try:
            work = bitcoin.getwork(work['extraNonce'], work['block'])
	except JSONRPCException, e:
            sysWrite('%s', e.error['message'])
            sleep(2)
            continue
	except IOError:
            sysWrite('Unable to communicate with bitcoin RPC')
            sleep(2)
            continue

	try:
            block2 = np.array(unpack('IIIIIIIIIIIIIIII', work['block'][128:].decode('hex')), dtype=np.uint32)
            state  = np.array(unpack('IIIIIIII',         work['state'].decode('hex')),       dtype=np.uint32)
            target = np.array(unpack('IIIIIIII',         work['target'].decode('hex')),      dtype=np.uint32)
	except:
            sysWriteLn('Wrong data format from RPC!')
            sys.exit()

        if (target[6] == 0):
            sysWriteLn('Check if kernel does all sha256 rounds!')
	
	state2 = np.array(state)
	(state2[3], state2[7]) = sharound(state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],state2[6],state2[7],block2[0],0x428A2F98)
	(state2[2], state2[6]) = sharound(state2[7],state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],state2[6],block2[1],0x71374491)
	(state2[1], state2[5]) = sharound(state2[6],state2[7],state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],block2[2],0xB5C0FBCF)

	output[0] = base = 0
	output_buf = cl.Buffer(context, cl.mem_flags.WRITE_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=output)

	start = time()
	while True:
		if (output[0]):
			work['block'] = work['block'][:152] + pack('I', long(output[0])).encode('hex') + work['block'][160:]
			# sysWriteLn('found: %s, %s', (output[0], datetime.now().strftime("%d/%m/%Y %H:%M")))
                        log.info('Device['+str(device)+'] found a block: '+str(output[0]))
			break

		if (time() - start > int(config['askrate']) or base + globalThreads == maxBase):
			break

		base += globalThreads
		if (base + globalThreads > maxBase):
			base = maxBase - globalThreads

		kernelStart = time()
		miner.search(	queue, (globalThreads, ), (int(config['worksize']), ),
						block2[0], block2[1], block2[2],
						state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
						state2[1], state2[2], state2[3], state2[5], state2[6], state2[7],
						target[6], pack('I', base), output_buf)
		cl.enqueue_read_buffer(queue, output_buf, output).wait()
		kernelTime = time() - kernelStart
		threadsRun += globalThreads

		if (kernelTime < lower):
			globalThreads += unit
		elif (kernelTime > upper and globalThreads != unit):
			globalThreads -= unit

		if (time() - rate > int(config['rate'])):
			log.info('Device['+device+']: '+str(int((threadsRun / (time() - rate)) / rateDivisor)) + 'khash/s')
			threadsRun = 0
			rate = time()


    log.debug('Done "working" on device '+device)
    ## END WORKER
                   
config = ConfigObj('default.cfg')
log.basicConfig(filename=config['logfile'],level=log.INFO,format='%(asctime)s %(levelname)-8s %(message)s',datefmt='%Y-%m-%d %H:%M:%S')

config['frames'] = max(int(config['frames']), 1.1)
config['askrate'] = max(int(config['askrate']), 1)
config['askrate'] = min(int(config['askrate']), 30)


if __name__ == "__main__":
    processes = []
    for device in config['devices']:
        p = Process(target=worker, args=(device, config))
        processes.append(p)

    for process in processes:
        process.start()



