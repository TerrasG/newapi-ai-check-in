#!/usr/bin/env python3
"""
本机 TCP 转发代理：监听 0.0.0.0:7898，转发到 127.0.0.1:7897 (Clash mixed proxy)。
用途：让服务器经 Tailscale 访问本机 Clash 代理（不改 Clash 配置）。
支持 HTTP 明文代理 和 HTTP CONNECT 隧道（HTTPS/任意 TCP）。
"""
import socketserver
import socket
import threading

LISTEN = ('0.0.0.0', 7898)
UPSTREAM = ('127.0.0.1', 7897)
BUFSIZE = 64 * 1024


def pump(src, dst, log_prefix):
    try:
        while True:
            data = src.recv(BUFSIZE)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        client = self.request
        try:
            first = client.recv(BUFSIZE)
            if not first:
                return
            head = first.decode('latin-1', errors='replace')

            # 检测 CONNECT 请求 (HTTPS 隧道)
            if head.startswith('CONNECT '):
                # 建到上游 Clash 的连接，把 CONNECT 请求转给它（Clash 是 mixed proxy，支持 CONNECT）
                up = socket.create_connection(UPSTREAM)
                up.sendall(first)
                # 读上游响应，确认隧道建立
                resp = up.recv(BUFSIZE)
                # 把上游响应转发给客户端（通常 200 Connection Established）
                client.sendall(resp)
                # 如果上游还没建立成功（resp 里不含 200 且还有数据要读），继续泵
                # 双向泵（残余数据 + 后续流量）
                t1 = threading.Thread(target=pump, args=(client, up, 'c2u'), daemon=True)
                t2 = threading.Thread(target=pump, args=(up, client, 'u2c'), daemon=True)
                t1.start(); t2.start()
                t1.join(); t2.join()
                up.close()
                return

            # HTTP 明文代理：把请求转发给 Clash，原样透传（Clash 会解析请求行）
            up = socket.create_connection(UPSTREAM)
            up.sendall(first)
            t1 = threading.Thread(target=pump, args=(client, up, 'c2u'), daemon=True)
            t2 = threading.Thread(target=pump, args=(up, client, 'u2c'), daemon=True)
            t1.start(); t2.start()
            t1.join(); t2.join()
            up.close()
        except Exception as e:
            print(f'[proxy] error: {e}')
        finally:
            try:
                client.close()
            except Exception:
                pass


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    srv = ThreadingTCPServer(LISTEN, Handler)
    print(f'[proxy] forwarding {LISTEN[0]}:{LISTEN[1]} -> {UPSTREAM[0]}:{UPSTREAM[1]}')
    srv.serve_forever()
