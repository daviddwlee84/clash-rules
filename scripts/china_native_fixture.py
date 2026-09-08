"""Loopback-only DNS/provider fixture; never loads private profiles or real nodes."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time


def fixture(core):
    queries=[]
    def dns_handler(label,address):
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                data,udp=self.request
                end=data.index(b'\0',12)+5
                cursor=12;labels=[]
                while data[cursor]:
                    length=data[cursor];cursor+=1
                    labels.append(data[cursor:cursor+length].decode());cursor+=length
                name='.'.join(labels)
                query_type=struct.unpack('!H',data[end-4:end-2])[0]
                queries.append((name,label))
                count=1 if query_type==1 else 0
                response=data[:2]+struct.pack('!5H',0x8180,1,count,0,0)+data[12:end]
                if count:
                    response+=b'\xc0\x0c'+struct.pack('!HHIH',1,1,60,4)+socket.inet_aton(address)
                udp.sendto(response,self.client_address)
        return Handler
    class Web(BaseHTTPRequestHandler):
        def do_GET(self):
            body=b'fixture-ok'
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):
            pass
    cn=socketserver.ThreadingUDPServer(('127.0.0.1',0),dns_handler('cn','127.0.0.1'))
    base=socketserver.ThreadingUDPServer(('127.0.0.1',0),dns_handler('baseline','127.0.0.1'))
    web=ThreadingHTTPServer(('127.0.0.1',0),Web)
    for server in (cn,base,web):
        server.daemon_threads=True
        threading.Thread(target=server.serve_forever,daemon=True).start()
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    process=None
    try:
        with tempfile.TemporaryDirectory(prefix='china-dns-fixture-') as tmp:
            home=Path(tmp)
            (home/'china.list').write_text('pilot.example\n')
            config={'mixed-port':port,'bind-address':'127.0.0.1','allow-lan':False,'ipv6':False,'mode':'rule','log-level':'info',
                    'tun':{'enable':False},'dns':{'enable':True,'ipv6':False,'use-hosts':False,'use-system-hosts':False,
                                               'nameserver':[f'udp://127.0.0.1:{base.server_address[1]}'],
                                               'nameserver-policy':{'rule-set:china-services-pilot':[f'udp://127.0.0.1:{cn.server_address[1]}']}},
                    'rule-providers':{'china-services-pilot':{'type':'file','behavior':'domain','format':'text','path':str(home/'china.list')}},
                    'proxy-groups':[{'name':name,'type':'select','proxies':['DIRECT']} for name in ['ChinaServices','HKMTMedia','PROXY','Final']],
                    'rules':['DOMAIN,media.example,HKMTMedia','DOMAIN,sef.example,PROXY','RULE-SET,china-services-pilot,ChinaServices','MATCH,Final']}
            (home/'config.json').write_text(json.dumps(config))
            log_path=home/'core.log'
            with log_path.open('wb') as log:
                process=subprocess.Popen([str(core),'-d',str(home),'-f',str(home/'config.json')],stdout=log,stderr=log)
                def probe(host):
                    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
                    try:
                        connection.request('GET',f'http://{host}:{web.server_address[1]}/')
                        response=connection.getresponse()
                        assert response.status==200 and response.read()==b'fixture-ok'
                    finally:connection.close()
                deadline=time.monotonic()+15
                while True:
                    try:
                        probe('ready.example')
                        break
                    except (OSError,AssertionError):
                        if process.poll() is not None or time.monotonic()>=deadline:
                            raise ValueError('China fixture did not become ready') from None
                        time.sleep(.1)
                cases=[('pilot.example','cn','ChinaServices'),('media.example','baseline','HKMTMedia'),
                       ('sef.example','baseline','PROXY'),('general.example','baseline','Final')]
                for host,resolver,policy in cases:
                    probe(host)
                    assert (host,resolver) in queries
                    assert (host,'baseline' if resolver=='cn' else 'cn') not in queries
                    text=log_path.read_text()
                    assert any(host+':' in line and 'using '+policy+'[DIRECT]' in line for line in text.splitlines()), host
                return len(cases)
    finally:
        if process:
            process.terminate();process.wait(timeout=5)
        for server in (cn,base,web):
            server.shutdown();server.server_close()
