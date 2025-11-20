# encode/decode our protocol packet - will be a python dict

import json
from typing import Dict, Any

def make_packet(conn_id: int, # connection id
                seq: int, # sequence number
                ack: int, # ack number - latest in order recieved + 1
                flags: Dict[str, bool], # flags are SYN, ACK, FIN, DATA - explained in sender_app.py
                rwnd: int, # receiver-side window size 
                payload: bytes # the content of the packet that isn't headers
                ): # -> bytes
    header = {
        "conn_id": conn_id,
        "seq": seq, 
        "ack": ack,
        "flags": flags,
        "rwnd": rwnd,
    }
    header_bytes = json.dumps(header).encode("utf-8")
    delim = b"\n\n" # delimiter between header and payload so we can split later
    return header_bytes + delim + payload 

def parse_packet(raw: bytes): # -> Dict[str, Any], bytes:
    # split JSON header and payload
    sep = raw.find(b"\n\n")
    if sep == -1:
        raise ValueError("Invalid packet format: Missing Separator")
    header_bytes = raw[:sep]
    payload = raw[sep+2:]
    header = json.loads(header_bytes.decode("utf-8"))
    return header, payload 
