#!/usr/bin/env python3
import socket
import threading
import time
import sys
import os
import select

class ChatServer:
    def __init__(self, host='localhost', port=4000):
        self.host = host
        self.port = port
        self.clients = {}  # username -> (socket, address, last_activity)
        self.server_socket = None
        self.running = False
        self.lock = threading.Lock()
        
    def start(self):
        """Start the chat server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            self.server_socket.setblocking(False)
            self.running = True
            print(f"Chat server started on {self.host}:{self.port}")
            print("Waiting for connections...")
            
            # Start cleanup thread for idle clients
            cleanup_thread = threading.Thread(target=self._cleanup_idle_clients, daemon=True)
            cleanup_thread.start()
            
            self._accept_connections()
                        
        except Exception as e:
            print(f"Failed to start server: {e}")
        finally:
            self.stop()
            
    def _accept_connections(self):
        """Accept new connections using select for better handling"""
        while self.running:
            try:
                read_sockets, _, exception_sockets = select.select([self.server_socket], [], [self.server_socket], 0.5)
                
                for sock in read_sockets:
                    if sock == self.server_socket:
                        client_socket, address = self.server_socket.accept()
                        client_socket.setblocking(False)
                        print(f"New connection from {address}")
                        
                        client_thread = threading.Thread(
                            target=self.handle_client,
                            args=(client_socket, address),
                            daemon=True
                        )
                        client_thread.start()
                        
                for sock in exception_sockets:
                    print("Exception on server socket")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                if self.running:
                    print(f"Error in accept loop: {e}")
            
    def stop(self):
        """Stop the server and close all connections"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        print("Server stopped")
        
    def handle_client(self, client_socket, address):
        """Handle individual client connection"""
        username = None
        buffer = ""
        
        try:
            self._send_message(client_socket, "INFO Welcome to the chat server! Please login with: LOGIN <username>")
            
            while self.running:
                try:
                    ready = select.select([client_socket], [], [], 0.1)
                    if ready[0]:
                        data = client_socket.recv(1024).decode('utf-8')
                        if not data:
                            break
                            
                        buffer += data
                        
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            
                            if not line:
                                continue
                                
                            with self.lock:
                                if username in self.clients:
                                    self.clients[username] = (client_socket, address, time.time())
                            
                            response = self._process_command(username, line, client_socket)
                            if response and response != username:
                                username = response
                                
                except BlockingIOError:
                    continue
                except socket.error as e:
                    print(f"Socket error for client {address}: {e}")
                    break
                except Exception as e:
                    print(f"Unexpected error for client {address}: {e}")
                    break
                    
        except Exception as e:
            print(f"Client {address} error: {e}")
        finally:
            if username:
                self._remove_client(username)
                self._broadcast_message(f"INFO {username} disconnected")
            client_socket.close()
            print(f"Client {address} disconnected")
            
    def _process_command(self, username, command, client_socket):
        """Process a single command from client - CASE INSENSITIVE"""
        try:
            # Convert command to uppercase for comparison, but keep original for message content
            upper_command = command.upper()
            
            if upper_command.startswith('LOGIN '):
                requested_username = command[6:].strip()
                return self._handle_login(client_socket, requested_username)
                
            elif upper_command.startswith('MSG '):
                if username:
                    message = command[4:].strip()
                    if message:
                        self._broadcast_message(f"MSG {username} {message}")
                    else:
                        self._send_message(client_socket, "ERR Message cannot be empty")
                else:
                    self._send_message(client_socket, "ERR Please login first")
                    
            elif upper_command == 'WHO':
                if username:
                    self._handle_who(client_socket)
                else:
                    self._send_message(client_socket, "ERR Please login first")
                    
            elif upper_command.startswith('DM '):
                if username:
                    self._handle_dm(client_socket, username, command[3:].strip())
                else:
                    self._send_message(client_socket, "ERR Please login first")
                    
            elif upper_command == 'PING':
                self._send_message(client_socket, "PONG")
                
            else:
                self._send_message(client_socket, "ERR Unknown command")
                
        except Exception as e:
            print(f"Error processing command: {e}")
            self._send_message(client_socket, "ERR Internal server error")
            
        return username
        
    def _handle_login(self, client_socket, requested_username):
        """Handle user login"""
        if not requested_username:
            self._send_message(client_socket, "ERR Username cannot be empty")
            return None
            
        if not all(c.isalnum() or c == '_' for c in requested_username):
            self._send_message(client_socket, "ERR Username can only contain letters, numbers and underscore")
            return None
            
        with self.lock:
            if requested_username in self.clients:
                self._send_message(client_socket, "ERR username-taken")
                return None
                
            self.clients[requested_username] = (client_socket, client_socket.getpeername(), time.time())
            
        self._send_message(client_socket, "OK")
        print(f"User '{requested_username}' logged in")
        return requested_username
        
    def _handle_who(self, client_socket):
        """Handle WHO command - list active users"""
        with self.lock:
            users = list(self.clients.keys())
            
        if users:
            for user in users:
                self._send_message(client_socket, f"USER {user}")
        else:
            self._send_message(client_socket, "INFO No users online")
            
    def _handle_dm(self, client_socket, sender, message):
        """Handle direct messages"""
        parts = message.split(' ', 1)
        if len(parts) < 2:
            self._send_message(client_socket, "ERR Usage: DM <username> <message>")
            return
            
        target_user, dm_message = parts
        dm_message = dm_message.strip()
        
        if not dm_message:
            self._send_message(client_socket, "ERR Message cannot be empty")
            return
            
        with self.lock:
            if target_user in self.clients:
                target_socket = self.clients[target_user][0]
                self._send_message(target_socket, f"DM {sender} {dm_message}")
                self._send_message(client_socket, f"INFO DM sent to {target_user}")
            else:
                self._send_message(client_socket, f"ERR User {target_user} not found")
                
    def _broadcast_message(self, message, exclude=None):
        """Broadcast message to all connected clients"""
        with self.lock:
            disconnected_users = []
            for username, (sock, addr, last_activity) in self.clients.items():
                if username != exclude:
                    try:
                        self._send_message(sock, message)
                    except (socket.error, BrokenPipeError):
                        disconnected_users.append(username)
                        
            for username in disconnected_users:
                if username in self.clients:
                    del self.clients[username]
                    print(f"Removed disconnected user: {username}")
                
    def _send_message(self, client_socket, message):
        """Send message to a client with newline"""
        try:
            client_socket.sendall(f"{message}\n".encode('utf-8'))
        except (socket.error, BrokenPipeError) as e:
            print(f"Error sending message: {e}")
            raise
            
    def _remove_client(self, username):
        """Remove client from active users"""
        with self.lock:
            if username in self.clients:
                del self.clients[username]
                print(f"User '{username}' removed")
                
    def _cleanup_idle_clients(self):
        """Clean up clients that have been idle for more than 60 seconds"""
        while self.running:
            time.sleep(30)
            current_time = time.time()
            disconnected_users = []
            
            with self.lock:
                for username, (sock, addr, last_activity) in self.clients.items():
                    if current_time - last_activity > 60:
                        print(f"Disconnecting idle user: {username}")
                        disconnected_users.append(username)
                        try:
                            sock.close()
                        except socket.error:
                            pass
                            
                for username in disconnected_users:
                    if username in self.clients:
                        del self.clients[username]
                        self._broadcast_message(f"INFO {username} disconnected (idle timeout)")

def main():
    port = 4000
    if 'CHAT_SERVER_PORT' in os.environ:
        try:
            port = int(os.environ['CHAT_SERVER_PORT'])
        except ValueError:
            print("Invalid CHAT_SERVER_PORT environment variable. Using default port 4000.")
    elif len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 4000.")
    
    server = ChatServer(port=port)
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()

if __name__ == "__main__":
    main()#!/usr/bin/env python3
import socket
import threading
import sys
import os

class SimpleChatServer:
    def __init__(self, host='localhost', port=4000):
        self.host = host
        self.port = port
        self.clients = {}  # username -> (socket, address)
        self.server_socket = None
        self.running = False
        self.lock = threading.Lock()
        
    def start(self):
        """Start the chat server"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            self.running = True
            print(f"Chat server started on {self.host}:{self.port}")
            print("Waiting for connections...")
            print("Press Ctrl+C to stop the server")
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    print(f"New connection from {address}")
                    
                    # Handle each client in a separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    if self.running:
                        print(f"Error accepting connection: {e}")
                        
        except Exception as e:
            print(f"Failed to start server: {e}")
        finally:
            self.stop()
            
    def stop(self):
        """Stop the server and close all connections"""
        print("Shutting down server...")
        self.running = False
        
        # Close all client connections
        with self.lock:
            for username, (sock, addr) in self.clients.items():
                try:
                    sock.close()
                except:
                    pass
            self.clients.clear()
            
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("Server stopped")
        
    def handle_client(self, client_socket, address):
        """Handle individual client connection"""
        username = None
        
        try:
            self._send_message(client_socket, "INFO Welcome to the chat server! Please login with: LOGIN <username>")
            
            while self.running:
                try:
                    data = client_socket.recv(1024).decode('utf-8')
                    if not data:
                        break  # Client disconnected
                    
                    # Process each line
                    for line in data.split('\n'):
                        line = line.strip()
                        if not line:
                            continue
                            
                        print(f"Received from {address}: {line}")
                        
                        # Process command
                        response = self._process_command(username, line, client_socket)
                        if response and response != username:
                            username = response
                            
                except (ConnectionResetError, ConnectionAbortedError):
                    break
                except Exception as e:
                    print(f"Error handling client {address}: {e}")
                    break
                    
        except Exception as e:
            print(f"Client {address} error: {e}")
        finally:
            if username:
                with self.lock:
                    if username in self.clients:
                        del self.clients[username]
                try:
                    self._broadcast_message(f"INFO {username} disconnected", exclude=username)
                except:
                    pass
                print(f"User '{username}' disconnected")
                
            try:
                client_socket.close()
            except:
                pass
            
    def _process_command(self, username, command, client_socket):
        """Process commands (case insensitive)"""
        upper_command = command.upper()
        
        if upper_command.startswith('LOGIN '):
            requested_username = command[6:].strip()
            return self._handle_login(client_socket, requested_username)
            
        elif upper_command.startswith('MSG '):
            if username:
                message = command[4:].strip()
                if message:
                    self._broadcast_message(f"MSG {username} {message}")
                else:
                    self._send_message(client_socket, "ERR Message cannot be empty")
            else:
                self._send_message(client_socket, "ERR Please login first")
                
        elif upper_command == 'WHO':
            if username:
                self._handle_who(client_socket)
            else:
                self._send_message(client_socket, "ERR Please login first")
                
        elif upper_command.startswith('DM '):
            if username:
                self._handle_dm(client_socket, username, command[3:].strip())
            else:
                self._send_message(client_socket, "ERR Please login first")
                
        elif upper_command == 'PING':
            self._send_message(client_socket, "PONG")
            
        else:
            self._send_message(client_socket, "ERR Unknown command")
            
        return username
        
    def _handle_login(self, client_socket, requested_username):
        """Handle user login"""
        if not requested_username:
            self._send_message(client_socket, "ERR Username cannot be empty")
            return None
            
        with self.lock:
            if requested_username in self.clients:
                self._send_message(client_socket, "ERR username-taken")
                return None
                
            self.clients[requested_username] = (client_socket, client_socket.getpeername())
            
        self._send_message(client_socket, "OK")
        print(f"User '{requested_username}' logged in")
        
        # Notify all users about new user
        self._broadcast_message(f"INFO {requested_username} joined the chat", exclude=requested_username)
        return requested_username
        
    def _handle_who(self, client_socket):
        """List active users"""
        with self.lock:
            users = list(self.clients.keys())
            
        if users:
            for user in users:
                self._send_message(client_socket, f"USER {user}")
        else:
            self._send_message(client_socket, "INFO No users online")
            
    def _handle_dm(self, client_socket, sender, message):
        """Handle direct messages"""
        parts = message.split(' ', 1)
        if len(parts) < 2:
            self._send_message(client_socket, "ERR Usage: DM <username> <message>")
            return
            
        target_user, dm_message = parts
        dm_message = dm_message.strip()
        
        if not dm_message:
            self._send_message(client_socket, "ERR Message cannot be empty")
            return
            
        with self.lock:
            if target_user in self.clients:
                target_socket = self.clients[target_user][0]
                try:
                    self._send_message(target_socket, f"DM {sender} {dm_message}")
                    self._send_message(client_socket, f"INFO DM sent to {target_user}")
                except:
                    self._send_message(client_socket, f"ERR Failed to send DM to {target_user}")
            else:
                self._send_message(client_socket, f"ERR User {target_user} not found")
                
    def _broadcast_message(self, message, exclude=None):
        """Broadcast message to all connected clients"""
        with self.lock:
            disconnected_users = []
            for username, (sock, addr) in self.clients.items():
                if username != exclude:
                    try:
                        self._send_message(sock, message)
                    except:
                        disconnected_users.append(username)
                        
            # Remove disconnected clients
            for username in disconnected_users:
                if username in self.clients:
                    del self.clients[username]
                
    def _send_message(self, client_socket, message):
        """Send message to a client"""
        try:
            client_socket.sendall(f"{message}\n".encode('utf-8'))
        except:
            raise

def main():
    port = 4000
    if 'CHAT_SERVER_PORT' in os.environ:
        try:
            port = int(os.environ['CHAT_SERVER_PORT'])
        except ValueError:
            print("Invalid CHAT_SERVER_PORT. Using default port 4000.")
    elif len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 4000.")
    
    server = SimpleChatServer(port=port)
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()

if __name__ == "__main__":
    main()