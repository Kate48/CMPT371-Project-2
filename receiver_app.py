# example app: receive data using the RDT API (no file writes)

import time

from rdt import server_accept

BUFFER_CAPACITY = 1024  # bytes
CONSUMER_DELAY = 0.2  # seconds between reads to simulate slow application


def main():
    # Congestion control test 
    conn = server_accept(("127.0.0.1", 9001),drop_prob=0.2,corrupt_prob=0.0)
    # conn = server_accept(("127.0.0.1", 9001),drop_prob=0.0,corrupt_prob=0.0)

    conn.recv_buffer_capacity = BUFFER_CAPACITY
    print("[server] Now in ESTABLISHED state with", conn.remote_addr)

    total_bytes = 0
    while True:
        chunk = conn.recv_data(timeout=1.0)
        if chunk is None:
            continue
        if chunk == b"":  # FIN received
            print("[server] FIN received, closing connection")
            break

        total_bytes += len(chunk)
        preview = chunk[:50]
        print(f"[server] Received {len(chunk)} bytes (total={total_bytes}, rwnd={conn.available_recv_window()}, sample={preview})")
        time.sleep(CONSUMER_DELAY)

    conn.close()
    print(f"[server] Total bytes received: {total_bytes}")


if __name__ == "__main__":
    main()
