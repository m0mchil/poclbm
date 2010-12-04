#!/usr/bin/env python

from BitcoinMiner import *
platform = cl.get_platforms()[0]
devices = platform.get_devices()
context = cl.Context([devices[1]], None, None)
myMiner = BitcoinMiner(platform, context, 'localhost', 'rpcusername_here', 'rpcpassword_here')
myMiner.mine()
