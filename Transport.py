from Queue import Queue
from log import *
import log

class Transport(object):
    def __init__(self, miner):
        self.miner = miner
        self.result_queue = Queue()

        self.backup_server_index = 1
        self.errors = 0
        self.failback_getwork_count = 0
        self.failback_attempt_count = 0
        self.server = None
        self.user_agent = 'poclbm/' + miner.version

        self.servers = []
        for server in miner.options.servers:
            try:
                temp = server.split('://', 1)
                if len(temp) == 1:
                    proto = ''; temp = temp[0]
                else: proto = temp[0]; temp = temp[1]
                user, temp = temp.split(':', 1)
                pwd, host = temp.split('@')
                if host.find('#') != -1:
                    host, name = host.split('#')
                else: name = host
                self.servers.append((proto, user, pwd, host, name))
            except ValueError:
                say_line("Ignored invalid server entry: '%s'", server)
                continue
        if not self.servers:
            self.failure('At least one server is required')
        else:
            self.set_server(self.servers[0])
            self.user_servers = list(self.servers)

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def set_server(self, server):
        self.server = server
        proto, user, pwd, host, name = server
        self.proto = proto
        self.host = host
        #self.say_line('Setting server %s (%s @ %s)', (name, user, host))
        say_line('Setting server (%s @ %s)', (user, name))
        log.server = name + ' '

    def add_servers(self, hosts):
        self.servers = list(self.user_servers)
        for host in hosts[::-1]:
            server = self.server
            server = (server[0], server[1], server[2], ''.join([host['host'], ':', str(host['port'])]), server[4])
            self.servers.insert(self.backup_server_index, server)