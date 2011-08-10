'''
A socket.io bridge for Python

This gives Python users access to socket.io, a node.js library. This library
provides simple and efficient bidirectional communication between browsers
and servers over a message-oriented socket. Transport is normalized over
various technologies including WebSockets, Flash sockets, and AJAX polling.

For the latest source, visit https://github.com/evanw/socket.io-python
'''

import os
import json
import atexit
import socket
import tempfile
import subprocess

# A socket.io template that connects to a Python socket over TCP and forwards
# messages as JSON strings separated by null characters. TCP was chosen over
# UDP to allow for arbitrarily large packets.
_js = '''
var net = require('net');
var http = require('http');
var io = require('socket.io');

// http server
var server = http.createServer(function() {});
server.listen(%d);

// tcp connection to server
var tcp = net.createConnection(%d, 'localhost');
var buffer = '';
tcp.addListener('data', function(data) {
    var i = 0;
    while (i < data.length) {
        if (data[i] == 0) {
            sendToClient(JSON.parse(buffer + data.toString('utf8', 0, i)));
            data = data.slice(i + 1);
            buffer = '';
            i = 0;
        } else {
            i++;
        }
    }
    buffer += data.toString('utf8');
});

// socket.io connection to clients
var socket = io.listen(server);
function sendToServer(client, command, data) {
    data = JSON.stringify({
        session: client.sessionId,
        command: command,
        data: data,
        address: client.connection.remoteAddress,
        port: client.connection.remotePort
    });
    tcp.write(data + '\0');
}
function sendToClient(json) {
    if (json.broadcast) {
        for (var session in socket.clients) {
            socket.clients[session].send(json.data);
        }
    } else if (json.session in socket.clients) {
        socket.clients[json.session].send(json.data);
    }
}
socket.on('connection', function(client) {
    sendToServer(client, 'connect', null);
    client.on('message', function(data) {
        sendToServer(client, 'message', data);
    });
    client.on('disconnect', function() {
        sendToServer(client, 'disconnect', null);
    });
});
'''

class Client:
    '''
    Represents a client connection. Each client has these properties:
    
    server - the Socket instance that owns this client
    session - the session id used by node (a string of numbers)
    address - the remote address of the client
    port - the remote port of the client
    '''
    
    def __init__(self, server, session, address, port):
        self.server = server
        self.session = session
        self.address = address
        self.port = port
    
    def send(self, data):
        '''
        Send a message to this client.
        
        data - a string with the data to transmit
        '''
        self.server._send(data, { 'session': self.session })
    
    def __str__(self):
        '''
        Returns "client-ADDRESS:PORT", where ADDRESS and PORT are the
        remote address and port of the client.
        '''
        return 'client-%s:%s' % (self.address, self.port)

class Server:
    '''
    This is a socket.io server, and is meant to be subclassed. A subclass
    might look like this:
    
        import socket_io as io
        
        class Server(io.Server):
            def on_connect(self, client):
                print client, 'connected'
                self.broadcast(str(client) + ' connected')
                print 'there are now', len(self.clients), 'clients'
            
            def on_message(self, client, message):
                print client, 'sent', message
                client.send(message)
            
            def on_disconnect(self, client):
                print client, 'disconnected'
                self.broadcast(str(client) + ' disconnected')
                print 'there are now', len(self.clients), 'clients'
        
        Server().listen(5000)
    
    The server has self.clients, a dictionary of client session ids to
    Client instances.
    '''
    
    def __init__(self):
        self.clients = {}
    
    def _handle(self, info):
        command = info['command']
        session = info['session']
        if command == 'connect':
            self.clients[session] = Client(self, session, info['address'], info['port'])
            self.on_connect(self.clients[session])
        elif command == 'message':
            if session in self.clients:
                self.on_message(self.clients[session], info['data'])
        elif command == 'disconnect':
            if session in self.clients:
                client = self.clients[session]
                del self.clients[session]
                self.on_disconnect(client)
    
    def on_connect(self, client):
        '''
        Called after a client connects. Override this in a subclass to
        be notified of connections.
        
        client - a Client instance representing the connection
        '''
        pass
    
    def on_message(self, client, data):
        '''
        Called when client sends a message. Override this in a subclass to
        be notified of sent messages.
        
        client - a Client instance representing the connection
        data - a string with the transmitted data
        '''
        pass

    def on_disconnect(self, client):
        '''
        Called after a client disconnects. Override this in a subclass to
        be notified of disconnections.
        
        client - a Client instance representing the connection
        '''
        pass

    def broadcast(self, data):
        '''
        Send a message to all connected clients.
        
        data - a string with the data to transmit
        '''
        self._send(data, { 'broadcast': True })
    
    def listen(self, ws_port, py_port=None):
        '''
        Run the server on the port given by ws_port. We actually need two
        ports, an external one for the browser (ws_port) and an internal
        one to communicate with node.js (py_port):
        
        browser:        node.js:                     this module:
        ---------       ----------------------       ---------------------
        io.Socket  <->  ws_port <-> TCP socket  <->  py_port <-> io.Socket
        
        ws_port - the port that the browser will connect to
        py_port - the port that python will use to talk to node.js
                  (defaults to ws_port + 1)
        '''
        
        # set default port
        if py_port is None:
            py_port = ws_port + 1
        
        # create a custom node.js script
        js = _js % (ws_port, py_port)
        handle, path = tempfile.mkstemp(suffix='.js')
        os.write(handle, js)
        os.close(handle)
        
        # run that script in node.js
        process = subprocess.Popen(['node', path])
        def cleanup():
            process.kill()
            os.remove(path)
        atexit.register(cleanup)
        
        # make sure we can communicate with node.js
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('localhost', py_port))
        sock.listen(0)
        sock, addr = sock.accept()
        def send(data, info):
            info['data'] = data
            sock.send(json.dumps(info) + '\0')
        self._send = send
        
        # run the server
        buffer = ''
        while 1:
            buffer += sock.recv(4096)
            index = buffer.find('\0')
            while index >= 0:
                data, buffer = buffer[0:index], buffer[index+1:]
                self._handle(json.loads(data))
                index = buffer.find('\0')
