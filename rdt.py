# Reliable, Pipelined protocol which performs 3-way handshake

import random
import socket
from typing import Tuple

from channel import UnreliableChannel
from packet import make_packet, parse_packet

N = 4 # window size for go back N

class RDTConnection:
    def __init__(self,
                channel: UnreliableChannel,
                remote_addr: Tuple[str,int],
                conn_id: int,
                send_seq: int, 
                recv_seq: int):
        self.channel = channel
        self.remote_addr = remote_addr
        self.conn_id = conn_id 
        self.send_seq = send_seq # next seq we will use when sending 
        self.recv_seq = recv_seq # next seq we expect to receive 
        self.state = "ESTABLISHED" # initialize state as established when a new connection starts

        # added attributes to implement go back N
        self.base = send_seq
        self.next_seq = send_seq
        self.window_size = N
        self.unacked = {}

    # refactored making a data packet into a helper func
    def make_data_packet(self, seq: int, payload_bytes: bytes):
        flags_data = {
            "SYN": False,
            "ACK": False,
            "FIN": False,
            "DATA": True,
        }
        packet = make_packet(
            conn_id=self.conn_id,
            seq=seq,
            ack=self.recv_seq,
            flags=flags_data,
            rwnd=0,
            payload=payload_bytes,
        )
        return packet 

    # refactored sending a data packet into a helper func
    def send_data_packet(self, seq: int, payload_bytes: bytes):
        packet = self.make_data_packet(seq, payload_bytes)
        print(f"[client] Sending data seq={seq}")
        self.channel.sendto(packet, self.remote_addr)
        return packet

    # retransmitting until an ACK arrives
    def send_data(self, payload: bytes, timeout: float = 1.0, max_retries: int = 5):
        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = bytes(payload)

        total_len = len(payload_bytes)
        if total_len == 0:
            return

        # value of last ack will be starting val + payload length 
        final_ack = self.send_seq + total_len

        attempt = 0
        # loop cond depends on final_ack as well as retries 
        while self.base < final_ack and attempt < max_retries:
            attempt += 1
            
            while (self.next_seq < self.base + self.window_size) and (self.next_seq < final_ack):
                
                remaining = final_ack - self.next_seq
                offset = self.next_seq - self.send_seq
                segment = payload_bytes[offset : offset + remaining]

                packet = self.send_data_packet(self.next_seq, segment)
                self.unacked[self.next_seq] = (packet, len(segment))
                self.next_seq += len(segment)
            
            try:
                self.channel.settimeout(timeout)
                raw, addr = self.channel.recvfrom()
            except socket.timeout:
                print("[client] Timeout, retransmitting from base={self.base}")
                
                for seq in sorted(self.unacked.keys()): # go back N step! iterate over the unacked packets
                    packet, _ = self.unacked[seq]
                    print(f"[client] Retransmitting packet seq={seq}")
                    self.channel.sendto(packet, self.remote_addr) # resend each unacked packet

                continue

            try:
                header, _ = parse_packet(raw)
            except ValueError:
                print("[client] Received corrupt packet while waiting for ACK, ignoring")
                continue

            flags = header.get("flags", {})
            if (addr == self.remote_addr and
                header.get("conn_id") == self.conn_id and
                flags.get("ACK") and not flags.get("DATA")):
                ack_num = header.get("ack", 0)
                
                if ack_num <= self.base:
                    print(f"[client] Duplicate/old ACK {ack_num}, base={self.base}")
                    continue

                if ack_num > final_ack:
                    ack_num = final_ack

                # slide window: remove all unacked packets w seq < ack_num
                acked_seqs = [s for s in self.unacked.keys() if s < ack_num]
                for s in acked_seqs:
                    self.unacked.pop(s, None)

                print(f"[client] Sliding window: base {self.base} -> {ack_num}")
                
                self.base = ack_num
                self.send_seq = ack_num # keep send_seq in sync

                if self.base >= final_ack: # acked the entire payload 
                    self.next_seq = self.base
                    return 
    
            else:
                print("[client] Unexpected packet while waiting for ACK, ignoring")

        raise RuntimeError("Failed to deliver payload after retransmissions")

def client_connect(local_addr: Tuple[str, int],
                   remote_addr: Tuple[str, int],
                   drop_prob: float = 0.0,
                   corrupt_prob: float = 0.0,
                   timeout:float = 1.0,
                   max_retries: int = 5) -> RDTConnection:

    channel = UnreliableChannel(local_addr,
                                drop_prob=drop_prob,
                                corrupt_prob=corrupt_prob)  
    channel.settimeout(timeout)

    conn_id = random.randint(1,1000000) # connect to a random client - conn ids start at 1
    client_isn = random.randint(0,1000000) # starting at a large random number to mimick TCP's robustness

    flags_syn = {"SYN": True, 
                 "ACK": False,
                 "FIN": False,
                 "DATA": False }
    syn_packet = make_packet(conn_id=conn_id,
                          seq=client_isn,
                          ack=0,
                          flags=flags_syn,
                          rwnd=0,
                          payload=b"")        
    
    for attempt in range(max_retries):
        print(f"[client] Sending SYN, {attempt+1}")
        channel.sendto(syn_packet, remote_addr) # send SYN packet to receiver - initiating handshake

        try: 
            raw, addr = channel.recvfrom() # receive SYN-ACK
        except socket.timeout:
            print("[client] Timeout waiting for SYN-ACK, retrying")
            continue

        header, payload = parse_packet(raw)
        flags = header["flags"]

        if flags.get("SYN") and flags.get("ACK") and header["ack"] == client_isn + 1:
            server_isn = header["seq"]
            print(f"[client] Got SYN-ACK from {addr}, server_isn={server_isn}")

            flags_ack = {"SYN": False, 
                         "ACK": True,
                         "FIN": False,
                         "DATA": False}
            ack_packet = make_packet(conn_id=conn_id,
                                     seq=client_isn + 1,
                                     ack=server_isn + 1,
                                     flags=flags_ack,
                                     rwnd=0,
                                     payload=b"")
            print("[client] Sending final ACK, connection established")
            channel.sendto(ack_packet, remote_addr) # send ACK to receiver

            return RDTConnection(channel=channel,
                                 remote_addr=remote_addr,
                                 conn_id=conn_id,
                                 send_seq=client_isn + 1,
                                 recv_seq=server_isn + 1)
        
        else:
            print("[client] Recived unexpected packet during handshake")
    
    channel.close()
    raise RuntimeError("Handshake failed: exceeded max retries")

def server_accept(local_addr: Tuple[str, int],
                  drop_prob: float = 0.0, # increase later
                  corrupt_prob: float = 0.0, # increase later
                  timeout: float = 2.0):
    channel = UnreliableChannel(local_addr,
                                drop_prob=drop_prob,
                                corrupt_prob=corrupt_prob)
    channel.settimeout(timeout)
    print(f"[server] Listening for SYN on {local_addr[0]}:{local_addr[1]}")

    while True:
        try:
            raw, addr = channel.recvfrom()
        except socket.timeout:
            continue # just keep listening for simplicity

        try: 
            header, payload = parse_packet(raw)
        except Exception:
            print("[server] Failed to parse packet:", Exception)
            continue

        flags = header["flags"]

        if flags.get("SYN") and not flags.get("ACK"): # expect an initial SYN
            client_isn = header["seq"]
            conn_id = header["conn_id"]
            print(f"[server] Received SYN from {addr}, client_isn={client_isn}")

            server_isn = random.randint(0, 10000000)
            flags_synack = {"SYN": True, 
                            "ACK": True,
                            "FIN": False,
                            "DATA": False }
            synack_packet = make_packet(conn_id=conn_id, # make a SYN-ACK
                                        seq=server_isn,
                                        ack=client_isn + 1,
                                        flags=flags_synack,
                                        rwnd=0,
                                        payload=b"")
            print("[server] Sending SYN-ACK")
            channel.sendto(synack_packet, addr) # send SYN-ACK

            while True:
                try:
                    raw2, addr2 = channel.recvfrom() # receive what we hope is an ACK
                except socket.timeout:
                    # for now go back to top-level listen loop
                    print("[server] Timeout waiting for final ACK, restarting listen.")
                    break
            
                header2, payload2 = parse_packet(raw2) # parse the ACK
                flags2 = header2["flags"]

                # if what we have received is a correct ACk
                if flags2.get("ACK") and not flags2.get("SYN") and header2["ack"] == server_isn + 1:
                    print (f"[server] Got final ACK from {addr2}, connection established")
                    return RDTConnection(channel=channel, # handshake complete, return this connection object
                                         remote_addr=addr,
                                         conn_id=conn_id,
                                         send_seq=server_isn + 1,
                                         recv_seq=client_isn + 1)
                else:
                    print("[server] Unexpected packet while waiting for final ACK, ignoring.")
        else:
            print("[server] Non-SYN packet in LISTEN state, ignoring.")
