"""Private STARTTLS mail sink for the isolated QA Compose project; never logs mail."""
import json
import os
import socketserver
import ssl
from email import policy
from email.parser import BytesParser
from pathlib import Path
from uuid import uuid4


class SMTP(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(20)
        self.reply('220 isolated QA SMTP')
        secured = False
        while line := self.rfile.readline(4096):
            command = line.decode('ascii', 'replace').strip().split(' ', 1)[0].upper()
            if command in {'EHLO', 'HELO'}:
                self.wfile.write(b'250-isolated-qa\r\n250-STARTTLS\r\n250 SIZE 65536\r\n')
                self.wfile.flush()
            elif command == 'STARTTLS' and not secured:
                self.reply('220 Ready for TLS')
                tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                tls.load_cert_chain('/qa/smtp.pem', '/qa/smtp.key')
                self.connection = tls.wrap_socket(self.connection, server_side=True)
                self.rfile = self.connection.makefile('rb')
                self.wfile = self.connection.makefile('wb')
                secured = True
            elif not secured:
                self.reply('530 STARTTLS required')
            elif command in {'MAIL', 'RCPT', 'RSET', 'NOOP'}:
                self.reply('250 OK')
            elif command == 'DATA':
                self.reply('354 End with dot')
                data = bytearray()
                while chunk := self.rfile.readline(65537):
                    if chunk == b'.\r\n':
                        break
                    data.extend(chunk[1:] if chunk.startswith(b'..') else chunk)
                    if len(data) > 65536:
                        self.reply('552 Too large')
                        return
                message = BytesParser(policy=policy.default).parsebytes(bytes(data))
                inbox = Path('/qa/inbox')
                inbox.mkdir(exist_ok=True)
                receipt = {'to': str(message['To']), 'subject': str(message['Subject']),
                           'message_id': str(message['Message-ID']), 'body': message.get_body(preferencelist=('plain',)).get_content()}
                path = inbox / f'{uuid4().hex}.json'
                with path.open('x', encoding='utf-8') as output:
                    json.dump(receipt, output)
                    output.flush()
                    os.fsync(output.fileno())
                self.reply('250 Stored')
            elif command == 'QUIT':
                self.reply('221 Bye')
                return
            else:
                self.reply('502 Unsupported')

    def reply(self, text):
        self.wfile.write((text + '\r\n').encode('ascii'))
        self.wfile.flush()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass  # No protocol payloads or synthetic credentials in container logs.


if __name__ == '__main__':
    with Server(('0.0.0.0', 8025), SMTP) as server:
        server.serve_forever()
