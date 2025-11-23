# example app: receive & save file

import socket

from rdt import server_accept # function to accept handshake
from packet import parse_packet, make_packet # parses raw bytes into header and payload

def main():
    conn = server_accept(("127.0.0.1", 9001), # (ip, port). 127.0.01 is loopback to this device, 9001 is somewhat arbitrary
                         drop_prob=0.0,
                         corrupt_prob=0.0)
    channel = conn.channel
    print("[server] Now in ESTABLISHED state with", conn.remote_addr)

    while True:
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
        if seq == expected:
            conn.recv_seq += len(payload)
            print("Got in-order packet from", addr,
                    "payload:", payload[:50]) # show only first 50 bytes in case of long payload
        else:
            print(f"[server] Out-of-order packet seq={seq}, expected={expected}. Re-ACKing last in-order byte.")

        ack_flags = {"SYN": False,
                     "ACK": True,
                     "FIN": False,
                     "DATA": False}
        ack_packet = make_packet(conn_id=conn.conn_id,
                                 seq=conn.send_seq,
                                 ack=conn.recv_seq,
                                 flags=ack_flags,
                                 rwnd=0,
                                 payload=b"")
        channel.sendto(ack_packet, addr)

    # later we will add a terminate condition using a flag,
    # for now the loop will run until we ctrl^C in terminal 

if __name__ == "__main__":
    main()
