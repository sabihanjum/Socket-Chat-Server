#!/usr/bin/env python3
import socket
import time
import threading

def test_user(name, messages):
    """Test a single user"""
    time.sleep(1)
    try:
        print(f"\n--- {name} connecting ---")
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('localhost', 4000))
        
        # Get welcome
        print(client.recv(1024).decode().strip())
        
        # Login
        client.send(f"LOGIN {name}\n".encode())
        time.sleep(0.5)
        print(f"Login response: {client.recv(1024).decode().strip()}")
        
        # Send messages
        for msg in messages:
            client.send(f"MSG {msg}\n".encode())
            time.sleep(2)
            
        # Listen for messages
        print(f"{name} listening for messages...")
        for i in range(5):
            try:
                data = client.recv(1024)
                if data:
                    print(f"{name} received: {data.decode().strip()}")
            except:
                break
            time.sleep(1)
            
        client.close()
        print(f"--- {name} disconnected ---")
        
    except Exception as e:
        print(f"{name} error: {e}")

# Test two users
users = [
    ("alice", ["Hello!", "Is anyone there?", "I'm Alice"]),
    ("bob", ["Hi Alice!", "I'm here!", "Nice to meet you!"])
]

threads = []
for name, messages in users:
    t = threading.Thread(target=test_user, args=(name, messages))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

print("\nTest completed!")