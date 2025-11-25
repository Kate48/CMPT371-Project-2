# Reliable, Pipelined protocol which performs 3-way handshake

import random
import socket
from collections import deque
from typing import Optional, Tuple

from channel import UnreliableChannel
from packet import make_packet, parse_packet

N = 4 # num of outstanding packets permitted by go back n

# Flow control test 
DEFAULT_RECV_BUFFER = 1000

#DEFAULT_RECV_BUFFER = 4096 # in bytes, so 4KB (a common socket buffer chunk/used in python.recv docs)

MSS = 512  # congestion-control segment size in bytes
INITIAL_SSTHRESH = 4096  # slow start threshold in bytes


class RDTConnection:
    def __init__(self,
                channel: UnreliableChannel,
                remote_addr: Tuple[str,int],
                conn_id: int,
                send_seq: int, 
                recv_seq: int,
                recv_buffer_capacity: int = DEFAULT_RECV_BUFFER):
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
        self.peer_rwnd = float("inf")  # latest advertised peer window size

        # flow-control bookkeeping for receivers
        self.recv_buffer_capacity = recv_buffer_capacity
        self.recv_buffered = 0
        # congestion-control state (AIMD style)
        self.mss = MSS
        self.cwnd = self.mss  # start slow start with one packet
        self.ssthresh = INITIAL_SSTHRESH
        self.dup_ack_count = 0
        self.last_acked = self.send_seq
        self.recv_queue = deque()  # in-order payloads waiting for the app
        self.fin_received = False

    # NOTE: Reciver window (three func below), (how many bytes the receiver can accept, and prevent buffer overflow)
    # how many bytes of payload the receiver can still store
    def available_recv_window(self) -> int:
        available = self.recv_buffer_capacity - self.recv_buffered
        return max(0, available)

    # reserve buffer space accordingly when data arrives
    def buffer_incoming(self, length: int):
        self.recv_buffered = min(self.recv_buffer_capacity, self.recv_buffered + max(0, length))

    # free buffer space when data is read 
    def consume_recv_buffer(self, length: int):
        self.recv_buffered = max(0, self.recv_buffered - max(0, length))


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
            rwnd=self.available_recv_window(), #changed form harcoded 0 to buffer flow control, data stops being sent when its 0
            payload=payload_bytes,
        )
        return packet 

    # refactored sending a data packet into a helper func
    def send_data_packet(self, seq: int, payload_bytes: bytes):
        packet = self.make_data_packet(seq, payload_bytes)
        print(f"[client] Sending data seq={seq}")
        self.channel.sendto(packet, self.remote_addr)
        return packet

    def _send_ack_packet(self):
        # send a pure ACK reflecting latest recv_seq/rwnd
        ack_flags = {
            "SYN": False,
            "ACK": True,
            "FIN": False,
            "DATA": False,
        }
        ack_packet = make_packet(
            conn_id=self.conn_id,
            seq=self.send_seq,
            ack=self.recv_seq,
            flags=ack_flags,
            rwnd=self.available_recv_window(),
            payload=b"",
        )
        self.channel.sendto(ack_packet, self.remote_addr)

    # retransmitting until an ACK arrives
    #FLOW CONTROL test line
    #def send_data(self, payload: bytes, timeout: float = 1.0, max_retries: int = 5):
    def send_data(self, payload: bytes, timeout: float = 1.0, max_retries: int = 15):
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
        self.last_acked = self.base
        while self.base < final_ack:
            peer_window = self.peer_rwnd
            if peer_window == float("inf"):
                peer_window = self.window_size * self.mss
            else:
                try:
                    peer_window = max(0, int(peer_window))
                except (TypeError, ValueError):
                    peer_window = self.window_size * self.mss

            # sender caps bytes to min(packets*MSS, receiver rwnd, congestion window)
            packets_window = self.window_size * self.mss
            send_window = min(packets_window, peer_window, self.cwnd)
            window_edge = self.base + max(0, send_window)

            while (self.next_seq < final_ack) and (self.next_seq < window_edge):
                allowance = min(final_ack - self.next_seq, window_edge - self.next_seq, self.mss)
                if allowance <= 0:
                    break

                offset = self.next_seq - self.send_seq
                segment = payload_bytes[offset : offset + allowance]

                packet = self.send_data_packet(self.next_seq, segment)
                self.unacked[self.next_seq] = (packet, len(segment))
                self.next_seq += len(segment)
            
            try:
                self.channel.settimeout(timeout)
                raw, addr = self.channel.recvfrom()
            except socket.timeout:
                print(f"[client] Timeout, retransmitting from base={self.base}")
                
                for seq in sorted(self.unacked.keys()):
                    packet, _ = self.unacked[seq]
                    print(f"[client] Retransmitting packet seq={seq}")
                    self.channel.sendto(packet, self.remote_addr)

                # congestion timeout -> multiplicative decrease
                self.ssthresh = max(self.cwnd // 2, self.mss)
                self.cwnd = self.mss
                self.dup_ack_count = 0

                attempt += 1
                if attempt >= max_retries:
                    break
                continue

            try:
                header, _ = parse_packet(raw)
            except ValueError:
                print("[client] Received corrupt packet while waiting for ACK, ignoring")
                continue

            # tracking the advertised window and resetting retries on progress
            flags = header.get("flags", {})
            if (addr == self.remote_addr and
                header.get("conn_id") == self.conn_id and
                flags.get("ACK") and not flags.get("DATA")):
                advertised_rwnd = header.get("rwnd")
                if advertised_rwnd is not None:
                    try:
                        self.peer_rwnd = max(0, int(advertised_rwnd))
                    except (TypeError, ValueError):
                        pass

                ack_num = header.get("ack", 0)

                # triple-duplicate ACKs cause a fast retransmit and halve cwnd, mirroring TCP’s behaviour
                if ack_num <= self.base:
                    print(f"[client] Duplicate/old ACK {ack_num}, base={self.base}")
                    if ack_num == self.base:
                        self.dup_ack_count += 1
                        if self.dup_ack_count >= 3 and self.base in self.unacked:
                            print("[client] Triple duplicate ACKs, fast retransmit and cwnd halved")
                            self.ssthresh = max(self.cwnd // 2, self.mss)
                            self.cwnd = self.ssthresh
                            packet, _ = self.unacked[self.base]
                            self.channel.sendto(packet, self.remote_addr)
                    continue

                if ack_num > final_ack:
                    ack_num = final_ack

                acked_seqs = [s for s in self.unacked.keys() if s < ack_num]
                for s in acked_seqs:
                    self.unacked.pop(s, None)

                print(f"[client] Sliding window: base {self.base} -> {ack_num}")
                
                self.base = ack_num
                self.send_seq = ack_num
                attempt = 0
                
                # successful ACKs grow cwnd via slow start when below ssthresh and additive increase otherwise
                if self.cwnd < self.ssthresh:
                    self.cwnd += self.mss
                else:
                    increment = max((self.mss * self.mss) // max(self.cwnd, 1), 1)
                    self.cwnd += increment
                self.dup_ack_count = 0
                self.last_acked = ack_num
                print(f"[client] cwnd={self.cwnd}, ssthresh={self.ssthresh}, rwnd={self.peer_rwnd}")

                if self.base >= final_ack:
                    self.next_seq = self.base
                    return 
    
            else:
                print("[client] Unexpected packet while waiting for ACK, ignoring")

        raise RuntimeError("Failed to deliver payload after retransmissions")

    def recv_data(self, timeout: float = 1.0) -> Optional[bytes]:
        # blocking receive that returns payload bytes, None on timeout, b'' on FIN
        while True:
            if self.recv_queue:
                data = self.recv_queue.popleft()
                self.consume_recv_buffer(len(data))
                return data

            if self.fin_received:
                return b""

            try:
                if timeout is not None:
                    self.channel.settimeout(timeout)
                raw, addr = self.channel.recvfrom()
            except socket.timeout:
                return None

            try:
                header, payload = parse_packet(raw)
            except ValueError:
                continue

            if addr != self.remote_addr or header.get("conn_id") != self.conn_id:
                continue

            flags = header.get("flags", {})

            if flags.get("FIN"):
                fin_seq = header.get("seq", 0)
                self.recv_seq = max(self.recv_seq, fin_seq + 1)
                self.fin_received = True
                self.state = "CLOSE_WAIT"
                self._send_ack_packet()
                continue

            if flags.get("DATA"):
                seq = header.get("seq", 0)
                if seq == self.recv_seq:
                    self.buffer_incoming(len(payload))
                    self.recv_queue.append(payload)
                    self.recv_seq += len(payload)
                    self._send_ack_packet()
                else:
                    self._send_ack_packet()

                continue

            # ignore other packets (eg pure ACK) in receive loop

    def close(self, timeout: float = 1.0, max_retries: int = 5):
        # terminates connection with a FIN/ACK handshake
        if self.state == "CLOSED":
            self.channel.close()
            return

        fin_flags = {
            "SYN": False,
            "ACK": False,
            "FIN": True,
            "DATA": False,
        }
        fin_seq = self.send_seq
        fin_packet = make_packet(
            conn_id=self.conn_id,
            seq=fin_seq,
            ack=self.recv_seq,
            flags=fin_flags,
            rwnd=self.available_recv_window(),
            payload=b"",
        )

        acked = False
        for attempt in range(max_retries):
            print("[conn] Sending FIN")
            self.channel.sendto(fin_packet, self.remote_addr)

            try:
                self.channel.settimeout(timeout)
                raw, addr = self.channel.recvfrom()
            except socket.timeout:
                continue

            try:
                header, payload = parse_packet(raw)
            except ValueError:
                continue

            flags = header.get("flags", {})
            if addr != self.remote_addr or header.get("conn_id") != self.conn_id:
                continue

            if (flags.get("ACK") and not flags.get("DATA")
                and header.get("ack") == fin_seq + 1):
                acked = True
                self.send_seq = fin_seq + 1
                break

            if flags.get("FIN"):
                self.recv_seq = header.get("seq", 0) + 1
                self._send_ack_packet()
                self.fin_received = True
                continue

        if not acked:
            raise RuntimeError("Failed to close connection: FIN not acknowledged")

        if not self.fin_received:
            while True:
                try:
                    self.channel.settimeout(timeout)
                    raw, addr = self.channel.recvfrom()
                except socket.timeout:
                    continue

                try:
                    header, payload = parse_packet(raw)
                except ValueError:
                    continue

                if addr != self.remote_addr or header.get("conn_id") != self.conn_id:
                    continue

                flags = header.get("flags", {})
                if flags.get("FIN"):
                    self.recv_seq = header.get("seq", 0) + 1
                    self._send_ack_packet()
                    break

        self.state = "CLOSED"
        self.channel.close()

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
