"""Temporary LAN board viewer. No hardware routes or arbitrary file serving."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]


def serve(host='127.0.0.1',port=8767,seconds=1800):
    assets={
        '/':('text/html; charset=utf-8',(ROOT/'ui/calibration-target.html').read_bytes()),
        '/calibration-target.html':('text/html; charset=utf-8',(ROOT/'ui/calibration-target.html').read_bytes()),
        '/calibration-board.svg':('image/svg+xml',(ROOT/'ui/calibration-board.svg').read_bytes()),
    }

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(3)

        def do_GET(self):
            item=assets.get(urlsplit(self.path).path)
            if item is None:self.send_error(404);return
            content_type,data=item
            self.send_response(200);self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data)

        def log_message(self,*args):pass

    with ThreadingHTTPServer((host,port),Handler) as server:
        server.timeout=.5;deadline=time.monotonic()+seconds
        print(f'Pano: http://{host}:{server.server_port}/ · {seconds} saniye · yalnız HTML/SVG',flush=True)
        while time.monotonic()<deadline:server.handle_request()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--seconds',type=int,default=1800);args=parser.parse_args()
    if not 1<=args.seconds<=3600:parser.error('Süre 1–3600 saniye olmalı')
    serve(args.host,args.port,args.seconds)
