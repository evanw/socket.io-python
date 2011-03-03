from SimpleHTTPServer import SimpleHTTPRequestHandler
from SocketServer import TCPServer
import io

class Server(io.Server):
    def on_connect(self, client):
        client.name = None

    def on_message(self, client, message):
        command, value = message.split(':', 1)
        print 'got message', command, 'starting with', '"%s"' % value[:30]

        if command == 'setname':
            client.name = value
        elif command == 'broadcast':
            self.broadcast(value)
        elif command == 'echo':
            client.send(value)
        elif command == 'send':
            name, data = value.split(':', 1)
            for client in self.clients.values():
                if client.name == name:
                    client.send(data)

    def on_disconnect(self, client):
        pass

def run_server():
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from SocketServer import TCPServer
    class NiceServer(TCPServer):
        allow_reuse_address = True
    NiceServer(('', 8000), SimpleHTTPRequestHandler).serve_forever()

import threading
t = threading.Thread(target=run_server)
t.daemon = True
t.start()

print '\nopen http://localhost:8000/tests.html to run tests\n'
Server().listen(5000)
