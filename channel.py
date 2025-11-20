# UnreliableChannel wrapper (UDP + random drop/corrupt)

import socket
import random
from typing import Tuple

class UnreliableChannel: # define our own data type to represent the underlying UDP channel
    def __init__(self,
                local_addr: Tuple[str, int], # (ip, port) to bind this UDP socket
                drop_prob: float = 0.0, # chance of a packet being dropped - implemented manually 
                corrupt_prob: float = 0.0): # chance of a bit being flipped - implemented manually 

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(local_addr)
        self.drop_prob = drop_prob
        self.corrupt_prob = corrupt_prob
    
    def sendto(self, data: bytes, addr: Tuple[str, int]):
        r = random.random()
        if r < self.drop_prob: # condition for dropping a packet 
            return 0 # nothing is sent: simulates packet loss 

        if r < self.drop_prob + self.corrupt_prob and len(data) > 0: # condition for corrupting a packet
            i = random.randrange(len(data)) # pick a byte from range of bytes we could flip 
            corrupted = bytearray(data)
            corrupted[i] ^= 0xFF # this bit mask flips the 8 bits in the byte we picked
            data = bytes(corrupted)

        # if packet is not dropped or corrupted it gets sent properly
        return self.sock.sendto(data, addr)
    
    def recvfrom(self, bufsize: int = 4096) -> Tuple[bytes, [Tuple[str, int]]]:
        data, addr = self.sock.recvfrom(bufsize) # I assume sock.recvfrom is diff from the recvfrom defined here
        return data, addr

    def settimeout(self, t: float):
        self.sock.settimeout(t)

    def close(self):
        self.sock.close()