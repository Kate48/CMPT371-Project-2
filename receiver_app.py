# example app: receive & save file with flow control

import socket
import time

from rdt import server_accept
from packet import parse_packet, make_packet

# these act as a finite application buffer and a consumer that periodically frees space
BUFFER_CAPACITY = 1024  # bytes
DRAIN_CHUNK = 128       # bytes freed every interval
DRAIN_INTERVAL = 0.5    # seconds


def main():
    conn = server_accept(("127.0.0.1", 9001),
                         drop_prob=0.0,
                         corrupt_prob=0.0)
    channel = conn.channel
    conn.recv_buffer_capacity = BUFFER_CAPACITY
    print("[server] Now in ESTABLISHED state with", conn.remote_addr)
    
    # the helper keeps the sender informed of the current advertised window (rwnd) whenever ACKs go out
    last_drain = time.time()
    last_advertised = conn.available_recv_window()

    def send_ack(addr):
        nonlocal last_advertised
        ack_flags = {"SYN": False,
                     "ACK": True,
                     "FIN": False,
                     "DATA": False}
        advertised = conn.available_recv_window()
        ack_packet = make_packet(conn_id=conn.conn_id,
                                 seq=conn.send_seq,
                                 ack=conn.recv_seq,
                                 flags=ack_flags,
                                 rwnd=advertised,
                                 payload=b"")
        channel.sendto(ack_packet, addr)
        last_advertised = advertised

    # emulates a slow reader freeing room and proactively sending a window-update when space increases
    while True:
        now = time.time()
        if now - last_drain >= DRAIN_INTERVAL:
            conn.consume_recv_buffer(DRAIN_CHUNK)
            last_drain = now
            if conn.available_recv_window() > last_advertised:
                print(f"[server] Buffer drained, advertising rwnd={conn.available_recv_window()}")
                send_ack(conn.remote_addr)

        try:
            raw, addr = channel.recvfrom()
        except socket.timeout:
            continue

        try:
            header, payload = parse_packet(raw)
        except ValueError:
            print("[server] Failed to parse incoming packet, dropping")
            continue

        flags = header.get("flags", {})
        if not flags.get("DATA"):
            print("[server] Received non-DATA packet, ignoring")
            continue

        seq = header.get("seq", 0)
        expected = conn.recv_seq
        # enforces the receive-window limit and forces the sender to pause when the buffer is full
        if len(payload) > conn.available_recv_window():
            print(f"[server] No buffer space for seq={seq}, advertising rwnd={conn.available_recv_window()}")
            send_ack(addr)
            continue

        if seq == expected:
            conn.buffer_incoming(len(payload))
            conn.recv_seq += len(payload)
            print("Got in-order packet from", addr,
                    "payload:", payload[:50],
                    f"(rwnd={conn.available_recv_window()})")
        else:
            print(f"[server] Out-of-order packet seq={seq}, expected={expected}. Re-ACKing last in-order byte.")

        send_ack(addr)

    # later we will add a terminate condition using a flag


if __name__ == "__main__":
    main()
