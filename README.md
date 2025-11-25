# HANDSHAKE AND RELIABLE PROTOCOL TEST

INCLUDE LINE 12 IN reciver_app.py: BUFFER_CAPACITY = 1024 
INLCUDE LINE 13 IN reciver_app.py: CONSUMER_DELAY = 0.2

INCLUDE LINE 17 IN rdt.py: DEFAULT_RECV_BUFFER = 4096 

INCLUDE LINE 25-29 IN sender_app.py:
```
for i in range(5):
    payload = f"message {i}".encode("utf-8")
    print(f"[client] Queueing packet {i}")
    conn.send_data(payload)
    time.sleep(0.5) 
```
INCLUDE LINE 17 IN rdt.py: DEFAULT_RECV_BUFFER = 4096 


PLEASE ENSURE LINE 21-23 IN sender_app.py ARE COMMENTED OUT.
PLEASE ENSURE LINE 12 IN sender_app.py IS COMMENTED OUT.

PLEASE ENSURE LINE 8-9 IN reciver_app.py ARE COMMENTED OUT.
PLEASE ENSURE LINE 17 IN reciver_app.py iS COMMENTED OUT.

PLEASE ENSURE LINE 15 IN rdt.py ARE COMMENTED OUT.




# FLOW CONTROL PARAMS: 
Line 8 in reciver_app.py: BUFFER_CAPACITY = 512
Line 9 in reciver_app.py: CONSUMER_DELAY = 0.5

BUFFER_CAPACITY = 512
CONSUMER_DELAY = 0.

Line 15 in rdt.py: DEFAULT_RECV_BUFFER = 100