from http.server import BaseHTTPRequestHandler
from asgiref.wsgi import WsgiToAsgi
from main import app
import json

class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.wsgi_app = WsgiToAsgi(app)
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        self.handle_request()
    
    def do_POST(self):
        self.handle_request()
    
    def handle_request(self):
        environ = {
            'REQUEST_METHOD': self.command,
            'PATH_INFO': self.path,
            'QUERY_STRING': '',
            'CONTENT_TYPE': self.headers.get('Content-Type', ''),
            'CONTENT_LENGTH': self.headers.get('Content-Length', ''),
            'HTTP_HOST': self.headers.get('Host', ''),
            'wsgi.url_scheme': 'https',
            'wsgi.input': self.rfile,
            'wsgi.errors': sys.stderr,
            'wsgi.version': (1, 0),
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
        }
        
        headers = []
        def start_response(status, response_headers):
            headers.extend(response_headers)
            self.send_response(int(status.split()[0]))
            for k, v in response_headers:
                self.send_header(k, v)
            self.end_headers()
        
        import sys
        body = b''.join(self.wsgi_app(environ, start_response))
        self.wfile.write(body)

handler = Handler