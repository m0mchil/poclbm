#!/usr/bin/env python

from multiprocessing import Process
from configobj import ConfigObj

import os
import logging as log
import smtplib
from email.mime.text import MIMEText

import sys
import pyopencl as cl

from struct import *
from time import sleep, time, strftime
from datetime import datetime

from BitcoinMiner import *

def if_else(condition, trueVal, falseVal):
	if condition:
		return trueVal
	else:
		return falseVal

def sendEmail(config, subject, message):
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = config['emailFrom']
        msg['To'] = config['emailTo']

        s = smtplib.SMTP('localhost')
        s.sendmail(msg['From'], [msg['To']], msg.as_string())
        s.quit()
        


def worker(device, config):
    log.debug('Worker starting on device '+device)
    log.debug('Setting DISPLAY variable for device '+device)
    os.environ['DISPLAY'] = ':0.'+device
    #os.environ['DISPLAY'] = ':0'
    log.debug('Confirming environment: '+os.environ['DISPLAY'])
    log.debug('Checking that device is found now that DISPLAY is set')

    platform = cl.get_platforms()[0]
    devices = platform.get_devices()
    context = cl.Context([devices[1]], None, None)

    class customMiner(BitcoinMiner):
        def say(self, format, args=()):
                log.info('Device[%s]: ' % device + format % args)

        def sayLine(self, format, args=()):
                self.say(format, args)
                
        def blockFound(self, output):
                currentBlock = self.bitcoin.getblocknumber()
                matures = int(currentBlock) + 120
                message = 'Device['+device+'] found a block with output: '+str(output)+'. Matures at block '+str(matures)+'.'
                log.info(message)
                sendEmail(config, 'Miner found a block', message)
    
    myMiner = customMiner(platform, context, config['hostname'], config['user'], config['password'], config['port'], config['frames'], config['rate'], config['askrate'], config['worksize'], config['vectors'])
                                                                                                       
    myMiner.mine()
    # END WORKER
                   
config = ConfigObj('daemon.cfg')
    
logfile = config['logfile']+'_'+strftime("%Y-%m-%d_%H%M%S")+'.log'
log.basicConfig(filename=logfile,level=log.INFO,format='%(asctime)s %(levelname)-8s %(message)s',datefmt='%Y-%m-%d %H:%M:%S')
if os.path.isfile('last.log'):
        os.remove('last.log')
os.symlink(logfile, 'last.log')

config['frames'] = int(max(int(config['frames']), 1.1))
config['askrate'] = int(max(int(config['askrate']), 1))
config['askrate'] = int(min(int(config['askrate']), 30))
if config['vectors'] == '0':
        config['vectors'] = False
else:
        config ['vectors'] = True

if __name__ == "__main__":
    processes = []
    for device in config['devices']:
        p = Process(target=worker, args=(device, config))
        processes.append(p)

    for process in processes:
        process.start()



