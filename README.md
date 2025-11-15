# TCP Chat Server

This repository contains a simple multi-client TCP chat server implemented in Python using only the standard library.

The server file you should run is `chat_server.py`.

## Features

- Multi-client support (thread-per-connection)
- Username-based login system
- Real-time message broadcasting
- Disconnect notifications
- Bonus features: `WHO`, `DM`, `PING`/`PONG`

## Requirements

- Python 3.7+
- No external dependencies

## How to run

Open PowerShell in this project folder and run:

## 1. Start the Server
# Default port 4000
python chat_server.py

## 2. Connect Clients

Using netcat
nc localhost 4000

Using telnet  
telnet localhost 4000

## 3. Login & Chat

Client 1:
LOGIN alice
OK
MSG Hello everyone!

Client 2:
LOGIN bob
OK
MSG alice Hello world!
MSG Hi Alice!

## Protocol commands

- `LOGIN <username>` — must be the first command; success -> `OK`, failure -> `ERR username-taken`.
- `MSG <text>` — broadcasted as `MSG <username> <text>` to all connected users.
- `WHO` — server responds with `USER <username>` for each connected user.
- `DM <username> <text>` — direct message to a specific user, delivered as `MSG <from> <text>` to the target.
- `PING` — server replies `PONG`.

When a user disconnects, the server broadcasts:

```
INFO <username> disconnected
```

## Notes

- The server expects newline-terminated text commands. Tools like `nc` and `telnet` add newlines automatically when you press Enter.
- This implementation uses only the Python standard library and is meant for local/testing use.

## Contact / License

MIT-style for this small educational project.
