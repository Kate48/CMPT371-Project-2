# example app: send a file / large message

from rdt import client_connect # function we wrote to initate handshake
from packet import make_packet 
import time

def main():
    conn = client_connect(
        local_addr=("127.0.0.1", 0),       # 0 = OS picks an ephemeral port
        remote_addr=("127.0.0.1", 9001),
        drop_prob=0.0,
        corrupt_prob=0.0
    )
    print("[client] Connection established to", conn.remote_addr)
    print("[client] send_seq starts at", conn.send_seq, "recv_seq starts at", conn.recv_seq)

    for i in range(5):
        payload = f"message {i}".encode("utf-8")
        flags = {"SYN": False, # synchronize sequence numbers - part of 3-way TCP handshake to be implemented later
                "ACK": False, # indicates if the packet contains an ack - false to start as we havent sent any acks
                "FIN": False, # termination flag - sender sets to true when they want to close the connection
                "DATA": True} # true if the packet contains any data in the payload
 
        packet = make_packet(conn_id=conn.conn_id,
                            seq=conn.send_seq, 
                            ack=0, 
                            flags=flags, 
                            rwnd=0, # reciever window - later to be calculated for flow control 
                            payload=payload)

        print(f"Sending packet {i}")
        conn.channel.sendto(packet, conn.remote_addr)
        print("[client] Sent data with seq", conn.send_seq)
        conn.send_seq += len(payload)
        time.sleep(0.5) 
    
if __name__ == "__main__":
    main()