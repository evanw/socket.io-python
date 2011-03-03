from SimpleHTTPServer import SimpleHTTPRequestHandler
from SocketServer import TCPServer
import io

class Server(io.Socket):
    def on_connect(self, client):
        client.name = None

    def on_message(self, client, message):
        command, value = message.split(':', 1)
        print 'got message', command, value

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

print '\nopen tests.html to run tests\n'
Server().listen(5000)
