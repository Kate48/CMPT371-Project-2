# example app: send a file / large message


from rdt import client_connect # function we wrote to initate handshake
import time

def main():
    conn = client_connect(
        local_addr=("127.0.0.1", 0),       # 0 = OS picks an ephemeral port
        remote_addr=("127.0.0.1", 9001),
        # congestion control test
        #drop_prob = 0.2

        drop_prob=0.0, 
        corrupt_prob=0.0
    )
    print("[client] Connection established to", conn.remote_addr)
    print("[client] send_seq starts at", conn.send_seq, "recv_seq starts at", conn.recv_seq)

    # Flow control test (lines 17-21)
    payload = b"x" * 4096
    print("[client] Sending bulk payload")
    conn.send_data(payload)
    

    # for i in range(5):
    #     payload = f"message {i}".encode("utf-8")
    #     print(f"[client] Queueing packet {i}")
    #     conn.send_data(payload)
    #     time.sleep(0.5) 
    
if __name__ == "__main__":
    main()
