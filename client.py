#!/usr/bin/env python3
"""Tic-Tac-Toe console client for CS 457 (Sprint 3).

Speaks the protocol in protocol_blueprint.md: newline-delimited JSON over
a TCP stream.

Usage:
    python3 client.py -h
    python3 client.py -i server.vencill.edu -p 5000
"""

import argparse
import json
import socket
import sys

RECV_SIZE = 4096          # Bytes requested from each recv() call
MIN_PORT = 1024
MAX_PORT = 65535


# ---------------------------------------------------------------------------
# Wire framing (protocol_blueprint.md section 2)
# ---------------------------------------------------------------------------
class ProtocolError(Exception):
    """Raised when a complete line is received but is not a valid message."""


def send_message(sock, message):
    """Serialize a dict as UTF-8 JSON terminated by a newline and send it."""
    data = json.dumps(message, separators=(",", ":")) + "\n"
    sock.sendall(data.encode("utf-8"))


class LineReader:
    """Accumulates bytes from a TCP stream and yields one JSON object per
    newline-terminated line, so message boundaries survive TCP chunking."""

    def __init__(self, sock):
        self.sock = sock
        self.buffer = b""

    def read_message(self):
        """Return the next message dict, or None on EOF (0-byte recv).

        Raises ProtocolError if a full line is not a JSON object. The bad
        line is already consumed, so the caller can keep reading.
        """
        while True:
            # Collect bytes until the buffer holds at least one full line.
            while b"\n" not in self.buffer:
                chunk = self.sock.recv(RECV_SIZE)
                if not chunk:
                    return None  # TCP 0-byte EOF -> server closed
                self.buffer += chunk
            # Split off the first line; leftover bytes stay in the buffer.
            line, self.buffer = self.buffer.split(b"\n", 1)
            if not line.strip():
                continue  # ignore blank lines
            try:
                message = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ProtocolError("not valid UTF-8 JSON")
            if not isinstance(message, dict):
                raise ProtocolError("message must be a JSON object")
            return message


# ---------------------------------------------------------------------------
# Command line, DNS and connection setup
# ---------------------------------------------------------------------------
def port_number(value):
    """argparse type: an integer port within 1024-65535."""
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{value}' is not a valid port number")
    if not MIN_PORT <= port <= MAX_PORT:
        raise argparse.ArgumentTypeError(
            f"port must be between {MIN_PORT} and {MAX_PORT} (got {port})")
    return port


def parse_args():
    """Parse the client command line (-h, -i and -p)."""
    parser = argparse.ArgumentParser(
        description="Tic-Tac-Toe console client (CS 457).",
        epilog="Example: python3 client.py -i server.vencill.edu -p 5000")
    parser.add_argument("-i", "--hostname", required=True,
                        metavar="HOSTNAME",
                        help="server DNS hostname (resolved via DNS)")
    parser.add_argument("-p", "--port", required=True, type=port_number,
                        metavar="PORT",
                        help=f"server port ({MIN_PORT}-{MAX_PORT})")
    return parser.parse_args()


def resolve_hostname(hostname):
    """Resolve hostname via DNS; exit cleanly with status 1 on failure."""
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        print(f"[ERROR] Unable to resolve DNS hostname '{hostname}'.")
        print("Please check your Cisco router DNS configuration "
              "('ip dns server' / 'ip host') or verify domain spelling.")
        sys.exit(1)


def connect_to_server(server_ip, port):
    """Open the TCP connection; exit cleanly with status 1 on failure."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((server_ip, port))
    except OSError as exc:
        sock.close()
        print(f"[ERROR] Could not connect to {server_ip}:{port} ({exc}).")
        print("Check that the server is running and the port is correct.")
        sys.exit(1)
    return sock


# ---------------------------------------------------------------------------
# Game client
# ---------------------------------------------------------------------------
class GameClient:
    """Receives server messages, draws the game, and sends this player's
    moves. Moves are only requested when the server says it is our turn."""

    def __init__(self, sock, player_name):
        self.sock = sock
        self.player_name = player_name
        self.reader = LineReader(sock)
        self.role = None
        self.opponent_name = "Opponent"
        self.scores = {"X": 0, "O": 0}
        self.awaiting_move = False  # True while it is our turn

    # -- Main loop ---------------------------------------------------------
    def run(self):
        """Send CONNECT, then react to server messages until the end."""
        try:
            send_message(self.sock, {"msg_type": "CONNECT",
                                     "player_name": self.player_name})
            while True:
                try:
                    message = self.reader.read_message()
                except ProtocolError as exc:
                    print(f"[WARN] Ignoring malformed server message: {exc}")
                    continue
                if message is None:
                    print("Connection closed by server.")
                    return
                if not self.handle_message(message):
                    return
        except KeyboardInterrupt:
            print("\nQuitting...")
            self.send_disconnect()
        except OSError as exc:
            print(f"[ERROR] Lost connection to server: {exc}")
        finally:
            self.sock.close()

    def handle_message(self, message):
        """Dispatch one server message. Returns False to stop the client."""
        msg_type = message.get("msg_type")
        if msg_type == "LOBBY_WAIT":
            self.awaiting_move = False
            print("\nWaiting for Player 2...")
        elif msg_type == "GAME_START":
            self.on_game_start(message)
        elif msg_type == "STATE_UPDATE":
            return self.on_state_update(message)
        elif msg_type == "GAME_OVER":
            self.on_game_over(message)
        elif msg_type == "ERROR":
            print(f"[SERVER ERROR] {message.get('error_message', '')}")
            if self.awaiting_move:  # our move was rejected; ask again
                return self.take_turn()
        else:
            print(f"[WARN] Ignoring unknown message type: {msg_type}")
        return True

    # -- Message handlers --------------------------------------------------
    def on_game_start(self, message):
        self.role = message.get("assigned_role")
        self.opponent_name = message.get("opponent_name", "Opponent")
        self.awaiting_move = False
        print("\n=== Game Start ===")
        print(f"You are {self.role}. Opponent: {self.opponent_name}")

    def on_state_update(self, message):
        board = message.get("board")
        turn = message.get("active_turn")
        if not self.is_valid_board(board):
            print("[WARN] Ignoring STATE_UPDATE with an invalid board.")
            return True
        self.print_board(board)
        if turn == self.role:
            self.awaiting_move = True
            return self.take_turn()
        self.awaiting_move = False
        if turn in ("X", "O"):
            print(f"Waiting for {self.opponent_name} ({turn}) to move...")
        return True

    def on_game_over(self, message):
        reason = message.get("reason")
        winner = message.get("winner")
        self.awaiting_move = False
        scores = message.get("scores")
        if isinstance(scores, dict):
            self.scores = {"X": scores.get("X", 0), "O": scores.get("O", 0)}

        print()
        if reason == "WIN":
            print("*** You win! ***" if winner == self.role
                  else f"*** You lose. {winner} wins. ***")
        elif reason == "DRAW":
            print("*** It's a draw. ***")
        elif reason == "FORFEIT":
            print("*** Opponent disconnected. You win by forfeit. ***"
                  if winner == self.role
                  else "*** Game ended by forfeit. ***")
        print(self.score_line())

        if reason == "FORFEIT":
            # The server resets scores when the opponent leaves.
            self.scores = {"X": 0, "O": 0}
        else:
            print("Starting the next round...")

    # -- Turn input --------------------------------------------------------
    def take_turn(self):
        """Prompt for a move and send it. Returns False if the user quits."""
        move = self.prompt_move()
        if move is None:
            self.send_disconnect()
            print("Disconnected.")
            return False
        row, col = move
        send_message(self.sock, {"msg_type": "MOVE", "role": self.role,
                                 "row": row, "col": col})
        return True

    def prompt_move(self):
        """Ask for 'row col' (0-2 each). Returns (row, col) or None=quit."""
        while True:
            try:
                raw = input(f"Your Turn ({self.role}) - enter 'row col' "
                            "(0-2) or 'quit': ").strip().lower()
            except EOFError:
                return None
            if raw in ("quit", "q"):
                return None
            parts = raw.replace(",", " ").split()
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                row, col = int(parts[0]), int(parts[1])
                if 0 <= row <= 2 and 0 <= col <= 2:
                    return row, col
            print("Invalid input. Example: 1 1 (row 1, column 1).")

    def send_disconnect(self):
        """Tell the server we are leaving (ignore errors if it is gone)."""
        try:
            send_message(self.sock, {"msg_type": "DISCONNECT"})
        except OSError:
            pass

    # -- Display -----------------------------------------------------------
    @staticmethod
    def is_valid_board(board):
        """True if board is a 3x3 list of strings."""
        return (isinstance(board, list) and len(board) == 3
                and all(isinstance(row, list) and len(row) == 3
                        and all(isinstance(cell, str) for cell in row)
                        for row in board))

    def score_line(self):
        """One-line score summary, marking which side is this player."""
        marks = {r: " (you)" if r == self.role else "" for r in ("X", "O")}
        return (f"Scores - X{marks['X']}: {self.scores['X']} | "
                f"O{marks['O']}: {self.scores['O']}")

    def print_board(self, board):
        """Draw the 3x3 board with row/column indexes."""
        print("\n     0   1   2")
        for r, row in enumerate(board):
            cells = " | ".join(cell if cell else " " for cell in row)
            print(f"  {r}  {cells}")
            if r < 2:
                print("    ---+---+---")
        print(self.score_line())


def ask_player_name():
    """Ask for the alias sent in CONNECT (default if left blank)."""
    try:
        name = input("Enter your player name: ").strip()
    except EOFError:
        name = ""
    return name or "Player"


def main():
    args = parse_args()
    server_ip = resolve_hostname(args.hostname)
    player_name = ask_player_name()
    sock = connect_to_server(server_ip, args.port)
    print(f"Connected to {args.hostname} ({server_ip}:{args.port})")
    GameClient(sock, player_name).run()


if __name__ == "__main__":
    main()
