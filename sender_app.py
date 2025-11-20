# example app: send a file / large message

from channel import UnreliableChannel # class we made
from packet import make_packet 
import time

def main():
    dest = ("127.0.0.1", 9001)
    channel = UnreliableChannel(dest, # (ip, port). 127.0.01 is loopback to this device, 9001 is somewhat arbitrary
                                drop_prob=0.2, # probabilities are same as in the UnreliableChannel we made in receiver_app.py
                                corrupt_prob=0.1)
    flags = {"SYN": False, # synchronize sequence numbers - part of 3-way TCP handshake to be implemented later
             "ACK": False, # indicates if the packet contains an ack - false to start as we havent sent any acks
             "FIN": False, # termination flag - sender sets to true when they want to close the connection
             "DATA": True} # true if the packet contains any data in the payload
    payload = b"hello, unreliable world"
    packet = make_packet(conn_id=1,
                         seq=0, 
                         ack=0, 
                         flags=flags, 
                         rwnd=4096, # reciever window - later to be calculated for flow control 
                         payload=payload)
    for i in range(10):
        print(f"Sending packet {i}")
        channel.sendto(packet, dest)
        time.sleep(0.5) 
    
if __name__ == "__main__":
    main()