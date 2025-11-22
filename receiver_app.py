# example app: receive & save file

from rdt import server_accept # function to accept handshake
from packet import parse_packet # parses raw bytes into header and payload

def main():
    conn = server_accept(("127.0.0.1", 9001), # (ip, port). 127.0.01 is loopback to this device, 9001 is somewhat arbitrary
                         drop_prob=0.0,
                         corrupt_prob=0.0)
    print("[server] Now in ESTABLISHED state with", conn.remote_addr)

    while True:
        raw, addr = channel.recvfrom()
        header, payload = parse_packet(raw)
        print("Got packet from", addr,
                "header:", header,
                "payload:", payload[:50]) # show only first 50 bytes in case of long payload

    # later we will add a terminate condition using a flag,
    # for now the loop will run until we ctrl^C in terminal 

if __name__ == "__main__":
    main()
