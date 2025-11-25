# Testing Guide

Please follow these toggles when testing each feature of the RDT project. 

## Running the demo apps
1. Start the receiver in one terminal: `python receiver_app.py`
2. Start the sender in another terminal: `python sender_app.py`
3. Observe the logs that correspond to the scenario you are executing, then stop both with `Ctrl+C`.

Revert any constants that were changed before moving to the next scenario—each test assumes a specific configuration.
This file has been submiited with everything on defualt/flow control and congestion control params have been commented out. 

Feel free to also open the pcap files that are saved in wireshark.

## 1. Three-way Handshake + Reliable Delivery
**Goal:** Show the SYN/SYN-ACK/ACK exchange and that ordered messages arrive when there is no loss.

Configuration:
- `receiver_app.py:7-12` → uncomment the “fast consumer” settings
  - `BUFFER_CAPACITY = 1024`
  - `CONSUMER_DELAY = 0.2`
  - comment out the `BUFFER_CAPACITY = 512` / `CONSUMER_DELAY = 0.5` lines.
- `rdt.py:14-18` -> set `DEFAULT_RECV_BUFFER = 4096` and comment out the `1000` value.
- `sender_app.py:20-29` -> comment out the bulk payload block and uncomment the 5-message loop:
  ```python
  for i in range(5):
      payload = f"message {i}".encode("utf-8")
      print(f"[client] Queueing packet {i}")
      conn.send_data(payload)
      time.sleep(0.5)
  ```
- `sender_app.py:8-16` & `receiver_app.py:15-18` -> keep `drop_prob = 0.0` so no synthetic loss occurs.

Expected receiver output:
- `[server] Now in ESTABLISHED state with ...`
- Five `[server] Received <len> bytes ... sample=b'message i'` lines in order, then `[server] FIN received...`.
Expected sender output:
- `[client] Connection established ...`
- `[client] Queueing packet i` for `i=0..4`
- `[client] Closing connection` without timeout/retry warnings.

## 2. Flow Control / Receiver Backpressure
**Goal:** Demonstrate the receiver advertising zero window, the sender pausing, and eventual recovery once the app drains the buffer.

Configuration:
- `receiver_app.py:7-12` → enable the “slow consumer” defaults:
  - `BUFFER_CAPACITY = 512`
  - `CONSUMER_DELAY = 0.5`
  - comment out the 1024/0.2 definitions.
- `rdt.py:14-18` → set `DEFAULT_RECV_BUFFER = 1000` and comment out the 4096 value.
- `sender_app.py:20-24` → uncomment the bulk payload block:
  ```python
  payload = b"x" * 3000
  print("[client] Sending bulk payload")
  conn.send_data(payload, timeout=1.0, max_retries=20)
  ```
  and leave the small loop commented.

Expected receiver output:
- `[server] Received ... rwnd=<value>` messages where `rwnd` eventually drops to `0` while the app sleeps.
- Once the artificial delay drains the buffer you should see `rwnd` climb back up and the connection close cleanly.
Expected sender output:
- `[client] Sending bulk payload`
- Periodic timeout/backoff messages (if logging enabled) followed by `[client] Closing connection` after recovery.

## 3. Congestion Control Under Loss (optional)
**Goal:** Show additive-increase/multiplicative-decrease behavior when the channel randomly drops packets.

Configuration:
- `sender_app.py:11-15` -> set `drop_prob = 0.2` (uncomment the loss line and comment out `drop_prob = 0.0`).
- `receiver_app.py:15-18` -> use the matching `server_accept(... drop_prob=0.2, corrupt_prob=0.0)` line and comment out the zero-loss line.
- Keep the fast consumer settings (`BUFFER_CAPACITY = 1024`, `CONSUMER_DELAY = 0.2`, `DEFAULT_RECV_BUFFER = 4096`) so flow control does not interfere.
- Use either the lightweight loop or the bulk payload depending on how long you want the trace to be.

Expected receiver output:
- Normal `[server] Received ...` lines even though drops occur, confirming eventual delivery.
Expected sender output:
- Retransmission notices plus congestion-window adjustments (e.g., cwnd reset after timeouts) before `[client] Closing connection`.

Together these three scenarios cover handshake/reliability, receiver-driven flow control, and congestion-control robustness. Packet captures (`*.pcap`) are included if packet-level inspection is needed during grading.
