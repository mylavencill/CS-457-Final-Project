#!/usr/bin/env python3
"""Tic-Tac-Toe game server for CS 457 (Sprint 3).

Implements the design documents in this repository:
  * protocol_blueprint.md  - newline-delimited JSON messages over TCP
  * fsm_specification.md   - INIT -> WAITING_FOR_PLAYERS -> GAME_START ->
                             PLAYER_TURN -> EVALUATE_MOVE -> GAME_OVER ->
                             CLEANUP
  * concurrency_design.md  - one thread per client plus a single
                             threading.Lock protecting all shared state

Usage:
    python3 server.py -h
    python3 server.py -p 5000
"""

import argparse
import json
import socket
import sys
import threading

HOST = "0.0.0.0"          # Bind to all interfaces (assignment requirement)
RECV_SIZE = 4096          # Bytes requested from each recv() call
MAX_PLAYERS = 2
MIN_PORT = 1024
MAX_PORT = 65535

# ---------------------------------------------------------------------------
# FSM states (fsm_specification.md) and the transitions the diagram allows.
# ---------------------------------------------------------------------------
INIT = "INIT"
WAITING_FOR_PLAYERS = "WAITING_FOR_PLAYERS"
GAME_START = "GAME_START"
PLAYER_TURN = "PLAYER_TURN"
EVALUATE_MOVE = "EVALUATE_MOVE"
GAME_OVER = "GAME_OVER"
CLEANUP = "CLEANUP"

ALLOWED_TRANSITIONS = {
    INIT: {WAITING_FOR_PLAYERS},
    WAITING_FOR_PLAYERS: {WAITING_FOR_PLAYERS, GAME_START, CLEANUP},
    GAME_START: {PLAYER_TURN},
    PLAYER_TURN: {PLAYER_TURN, EVALUATE_MOVE, GAME_OVER},
    EVALUATE_MOVE: {PLAYER_TURN, GAME_OVER},
    GAME_OVER: {CLEANUP},
    CLEANUP: {WAITING_FOR_PLAYERS},
}

# All eight ways to win: 3 rows, 3 columns, 2 diagonals.
WIN_LINES = [
    [(0, 0), (0, 1), (0, 2)],
    [(1, 0), (1, 1), (1, 2)],
    [(2, 0), (2, 1), (2, 2)],
    [(0, 0), (1, 0), (2, 0)],
    [(0, 1), (1, 1), (2, 1)],
    [(0, 2), (1, 2), (2, 2)],
    [(0, 0), (1, 1), (2, 2)],
    [(0, 2), (1, 1), (2, 0)],
]


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
                    return None  # TCP 0-byte EOF -> peer closed
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
# Game helpers
# ---------------------------------------------------------------------------
def new_board():
    """Return an empty 3x3 board."""
    return [["", "", ""] for _ in range(3)]


def find_winner(board):
    """Return "X" or "O" if someone has three in a row, else None."""
    for line in WIN_LINES:
        first = board[line[0][0]][line[0][1]]
        if first and all(board[r][c] == first for r, c in line):
            return first
    return None


def board_is_full(board):
    """Return True when no empty squares remain."""
    return all(cell != "" for row in board for cell in row)


def is_int(value):
    """True for real integers (bool is excluded; JSON true != 1 here)."""
    return isinstance(value, int) and not isinstance(value, bool)


def other_role(role):
    """Return the opposing role."""
    return "O" if role == "X" else "X"


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


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
class GameServer:
    """Multi-threaded Tic-Tac-Toe server.

    Every method whose name ends in _locked must be called while holding
    game_state_lock. All sends happen while the lock is held, which keeps
    bytes from two threads from interleaving on one socket.
    """

    def __init__(self, port):
        self.port = port
        self.listen_sock = None

        # Shared state (concurrency_design.md section 2). Every read and
        # write is guarded by game_state_lock.
        self.game_state_lock = threading.Lock()
        self.game_board = new_board()
        self.active_turn = "NONE"
        self.connected_clients = {}              # role -> socket
        self.round_scores = {"X": 0, "O": 0}
        self.player_names = {}                   # role -> alias (CONNECT)
        self.game_state = INIT                   # current FSM state

    # -- FSM ---------------------------------------------------------------
    def _set_state(self, new_state):
        """Move the FSM to new_state, enforcing the allowed transitions."""
        if new_state not in ALLOWED_TRANSITIONS[self.game_state]:
            raise RuntimeError(
                f"Illegal FSM transition {self.game_state} -> {new_state}")
        print(f"[FSM] {self.game_state} -> {new_state}")
        self.game_state = new_state

    # -- Sending helpers (lock held) ---------------------------------------
    def _send_locked(self, role, message):
        """Send to one player. Returns False if the socket failed."""
        sock = self.connected_clients.get(role)
        if sock is None:
            return False
        try:
            send_message(sock, message)
            return True
        except OSError:  # includes ConnectionResetError, BrokenPipeError
            return False

    def _broadcast_locked(self, message):
        """Send to every connected player. Returns roles that failed."""
        failed = []
        for role in list(self.connected_clients):
            if not self._send_locked(role, message):
                failed.append(role)
        return failed

    def _broadcast_state_locked(self):
        """Broadcast the board and whose turn it is (STATE_UPDATE)."""
        return self._broadcast_locked({
            "msg_type": "STATE_UPDATE",
            "board": self.game_board,
            "active_turn": self.active_turn,
        })

    def _broadcast_game_over_locked(self, reason, winner):
        """Broadcast GAME_OVER including the current scores."""
        self._broadcast_locked({
            "msg_type": "GAME_OVER",
            "reason": reason,
            "winner": winner,
            "scores": dict(self.round_scores),
        })

    def _send_error(self, sock, text):
        """Send an ERROR message to one client (takes the lock itself)."""
        with self.game_state_lock:
            try:
                send_message(sock, {"msg_type": "ERROR",
                                    "error_message": text})
            except OSError:
                pass  # the client's own thread will notice the failure

    # -- Lobby / game start ------------------------------------------------
    def register_client(self, sock, player_name):
        """Assign a role to a newly connected client.

        Returns the role ("X"/"O"), or None if the room is already full.
        The first client gets X; a later client takes whichever role is free.
        """
        with self.game_state_lock:
            if len(self.connected_clients) >= MAX_PLAYERS:
                try:
                    send_message(sock, {"msg_type": "ERROR",
                                        "error_message": "Game room is full."})
                except OSError:
                    pass
                return None

            role = "X" if "X" not in self.connected_clients else "O"
            self.connected_clients[role] = sock
            self.player_names[role] = player_name
            print(f"[SERVER] '{player_name}' joined as {role}")

            if len(self.connected_clients) < MAX_PLAYERS:
                # Client 1 connects: stay in WAITING_FOR_PLAYERS.
                self._set_state(WAITING_FOR_PLAYERS)
                self._send_lobby_wait_locked()
            else:
                # Client 2 connects: WAITING_FOR_PLAYERS -> GAME_START.
                self._start_game_locked()
            return role

    def _send_lobby_wait_locked(self):
        """Tell the lone connected player that we are waiting for Player 2."""
        self._broadcast_locked({
            "msg_type": "LOBBY_WAIT",
            "message": "Waiting for Player 2 to join.",
        })

    def _start_game_locked(self):
        """GAME_START: initialize board, announce roles, then PLAYER_TURN."""
        self._set_state(GAME_START)
        self.game_board = new_board()
        self.active_turn = "X"
        for role in list(self.connected_clients):
            self._send_locked(role, {
                "msg_type": "GAME_START",
                "assigned_role": role,
                "opponent_name": self.player_names[other_role(role)],
            })
        self._set_state(PLAYER_TURN)
        failed = self._broadcast_state_locked()
        if failed:
            self._handle_departure_locked(failed[0])

    # -- Move processing ---------------------------------------------------
    def _validate_move_locked(self, sender_role, message):
        """Return an error string if the MOVE is not acceptable, else None."""
        if self.game_state != PLAYER_TURN:
            return "Game is not in progress."

        role = message.get("role")
        row = message.get("row")
        col = message.get("col")
        if role not in ("X", "O") or not is_int(row) or not is_int(col):
            return "Malformed message: MOVE needs role, row and col."

        # Extra guard: a client may only move as the role it was assigned.
        if role != sender_role:
            return "Role does not match your assigned role."

        # Turn enforcement (concurrency_design.md step 2).
        if role != self.active_turn:
            return "Not your turn."

        if not (0 <= row <= 2 and 0 <= col <= 2):
            return "Invalid move: Coordinates must be 0, 1, or 2."
        if self.game_board[row][col] != "":
            return "Invalid move: Space already occupied."
        return None

    def handle_move(self, sock, sender_role, message):
        """Validate and apply a MOVE (concurrency_design.md steps 1-5)."""
        with self.game_state_lock:                       # 1. acquire
            if self.connected_clients.get(sender_role) is not sock:
                return  # this client was already removed

            error = self._validate_move_locked(sender_role, message)
            if error:                                    # 2. validation
                try:
                    send_message(sock, {"msg_type": "ERROR",
                                        "error_message": error})
                except OSError:
                    pass
                return  # PLAYER_TURN -> PLAYER_TURN

            # 3. State mutation: PLAYER_TURN -> EVALUATE_MOVE
            self._set_state(EVALUATE_MOVE)
            self.game_board[message["row"]][message["col"]] = sender_role

            winner = find_winner(self.game_board)
            if winner:
                self.round_scores[winner] += 1
                self._finish_round_locked("WIN", winner)
            elif board_is_full(self.game_board):
                self._finish_round_locked("DRAW", "NONE")
            else:
                self.active_turn = other_role(self.active_turn)
                self._set_state(PLAYER_TURN)
                failed = self._broadcast_state_locked()  # 4. broadcast
                if failed:
                    self._handle_departure_locked(failed[0])
        # 5. lock released by leaving the with-block

    def _finish_round_locked(self, reason, winner):
        """EVALUATE_MOVE -> GAME_OVER -> CLEANUP for a win or a draw."""
        self._set_state(GAME_OVER)
        self.active_turn = "NONE"
        self._broadcast_state_locked()
        self._broadcast_game_over_locked(reason, winner)
        # Both players stay connected for a rematch; scores are kept.
        self._cleanup_locked(reset_scores=False)

    # -- Disconnects and cleanup -------------------------------------------
    def _handle_departure_locked(self, role):
        """Remove a player; forfeit the game if one was in progress."""
        sock = self.connected_clients.pop(role, None)
        if sock is None:
            return  # already handled by another thread
        name = self.player_names.pop(role, "?")
        print(f"[SERVER] '{name}' ({role}) disconnected")
        try:
            sock.shutdown(socket.SHUT_RDWR)  # wake any thread in recv()
        except OSError:
            pass
        sock.close()

        remaining = list(self.connected_clients)
        if self.game_state in (PLAYER_TURN, EVALUATE_MOVE) and remaining:
            # Any client disconnects -> GAME_OVER by forfeit.
            self._set_state(GAME_OVER)
            self.active_turn = "NONE"
            self._broadcast_game_over_locked("FORFEIT", remaining[0])
        # A new opponent means a fresh scoreboard.
        self._cleanup_locked(reset_scores=True)

    def _cleanup_locked(self, reset_scores):
        """CLEANUP: reset the board, then return to WAITING_FOR_PLAYERS."""
        self._set_state(CLEANUP)
        self.game_board = new_board()
        self.active_turn = "NONE"
        if reset_scores:
            self.round_scores = {"X": 0, "O": 0}
        self._set_state(WAITING_FOR_PLAYERS)

        count = len(self.connected_clients)
        if count == MAX_PLAYERS:
            self._start_game_locked()       # rematch with same two players
        elif count == 1:
            self._send_lobby_wait_locked()  # remaining player waits

    def _remove_client(self, role, sock):
        """Thread exit path: drop the client if it is still registered."""
        with self.game_state_lock:
            if role is not None and self.connected_clients.get(role) is sock:
                self._handle_departure_locked(role)
                return
        try:
            sock.close()
        except OSError:
            pass

    # -- Per-client thread -------------------------------------------------
    def handle_client(self, sock, addr):
        """Thread body: CONNECT handshake, then the MOVE/DISCONNECT loop."""
        print(f"[SERVER] Connection from {addr[0]}:{addr[1]}")
        reader = LineReader(sock)
        role = None
        try:
            player_name = self._read_connect(sock, reader)
            if player_name is None:
                return
            role = self.register_client(sock, player_name)
            if role is None:
                return
            self._game_loop(sock, reader, role)
        except OSError as exc:
            # Covers ConnectionResetError and BrokenPipeError (abrupt loss).
            print(f"[SERVER] Connection error on {addr[0]}:{addr[1]}: {exc}")
        finally:
            self._remove_client(role, sock)

    def _read_connect(self, sock, reader):
        """Read the first message, which must be a valid CONNECT."""
        try:
            message = reader.read_message()
        except ProtocolError as exc:
            self._send_error(sock, f"Malformed message: {exc}.")
            return None
        if message is None:
            return None
        name = message.get("player_name")
        if (message.get("msg_type") != "CONNECT"
                or not isinstance(name, str) or not name.strip()):
            self._send_error(sock, "Malformed message: expected CONNECT "
                                   "with a player_name.")
            return None
        return name.strip()

    def _game_loop(self, sock, reader, role):
        """Process MOVE / DISCONNECT messages until the client leaves."""
        while True:
            try:
                message = reader.read_message()
            except ProtocolError as exc:
                self._send_error(sock, f"Malformed message: {exc}.")
                continue
            if message is None:
                return  # 0-byte EOF -> treated as a forfeit by the caller

            msg_type = message.get("msg_type")
            if msg_type == "MOVE":
                self.handle_move(sock, role, message)
            elif msg_type == "DISCONNECT":
                return  # graceful quit -> forfeit handled by the caller
            else:
                self._send_error(sock, "Malformed message: unexpected "
                                       "msg_type.")

    # -- Startup / shutdown ------------------------------------------------
    def run(self):
        """Bind, listen, and accept clients (one thread per client)."""
        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_sock.setsockopt(socket.SOL_SOCKET,
                                    socket.SO_REUSEADDR, 1)
        self.listen_sock.bind((HOST, self.port))
        self.listen_sock.listen()

        # INIT -> WAITING_FOR_PLAYERS: server started and listening.
        self._set_state(WAITING_FOR_PLAYERS)
        print(f"[SERVER] Listening on {HOST}:{self.port} (Ctrl+C to stop)")

        try:
            while True:
                conn, addr = self.listen_sock.accept()
                thread = threading.Thread(target=self.handle_client,
                                          args=(conn, addr), daemon=True)
                thread.start()
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down.")
        finally:
            self._shutdown()

    def _shutdown(self):
        """CLEANUP -> [*]: close every socket on server shutdown."""
        with self.game_state_lock:
            print(f"[FSM] {self.game_state} -> CLEANUP (server shutdown)")
            for sock in self.connected_clients.values():
                try:
                    sock.close()
                except OSError:
                    pass
            self.connected_clients.clear()
        self.listen_sock.close()


def parse_args():
    """Parse the server command line (-h and -p)."""
    parser = argparse.ArgumentParser(
        description="Tic-Tac-Toe game server (CS 457).",
        epilog="Example: python3 server.py -p 5000")
    parser.add_argument("-p", "--port", required=True, type=port_number,
                        metavar="PORT",
                        help=f"listening port ({MIN_PORT}-{MAX_PORT}); "
                             "binds to 0.0.0.0")
    return parser.parse_args()


def main():
    args = parse_args()
    server = GameServer(args.port)
    try:
        server.run()
    except OSError as exc:
        print(f"[ERROR] Could not start server on port {args.port}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
