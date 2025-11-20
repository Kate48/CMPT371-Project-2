# example app: receive & save file

from channel import UnreliableChannel # class we made
from packet import parse_packet # parses raw bytes into header and payload

def main():
    channel = UnreliableChannel(("127.0.0.1", 9001), # (ip, port). 127.0.01 is loopback to this device, 9001 is somewhat arbitrary
                                drop_prob=0.2, # probabilities are same as in the UnreliableChannel we made in sender_app.py
                                corrupt_prob=0.1)
    print("Receiver listening on 127.0.0.1:9001")

    while True:
        raw, addr = channel.recvfrom()
        try:
            header, payload = parse_packet(raw)
        except Exception:
            print("Failed to parse packet:", Exception)
            continue
        print("Got packet from", addr,
                "header:", header,
                "payload:", payload[:50]) # show only first 50 bytes in case of long payload

    # later we will add a terminate condition using a flag,
    # for now the loop will run until we ctrl^C in terminal 

if __name__ == "__main__":
    main()
