## 1. Message Types & Structured Schema Definitions

### 1. `CONNECT`
* **Direction:** Client -> Server
* **Purpose & Description:** Client requests to join game room with player alias.
* **Field Specs and Data Types:**
  * `msg_type` (string): "CONNECT"
  * `player_name` (string): Alias for the player.
* **Example:**
  ```json
  {
    "msg_type": "CONNECT",
    "player_name": "Player 1"
  }
  ```
  
### 2. `LOBBY_WAIT`
* **Direction:** Server -> Client
* **Purpose & Description:** Server notifies Client 1 that it is waiting for Player 2 to connect.
* **Field Specs and Data Types:**
  * `msg_type` (string): "LOBBY_WAIT"
  * `message` (string): Status message.
* **Example:**
  ```json
  {
    "msg_type": "LOBBY_WAIT",
    "message": "Waiting for Player 2 to join."
  }
  ```
  
### 3. `GAME_START`
* **Direction:** Server -> Clients
* **Purpose & Description:** Server notifies both clients that game has started and assigns roles (Player 1 / Player 2).
* **Field Specs and Data Types:**
  * `msg_type` (string): "GAME_START"
  * `assigned_role` (string): "X" or "O"
  * `opponent_name` (string): Username of other player.
* **Example:**
  ```json
  {
    "msg_type": "GAME_START",
    "assigned_role": "X",
    "opponent_name": "Player 2"
  }
  ```
  
### 4. `MOVE`
* **Direction:** Client -> Server
* **Purpose & Description:** Active player submits move coordinates.
* **Field Specs and Data Types:**
  * `msg_type` (string): "MOVE"
  * `role` (string): "X" or "O"
  * `row` (integer): 0, 1, or 2
  * `col` (integer): 0, 1, or 2
* **Example:**
  ```json
  {
    "msg_type": "MOVE",
    "role": "X",
    "row": 1,
    "col": 1
  }
  ```

### 5. `STATE_UPDATE`
* **Direction:** Server -> Clients
* **Purpose & Description:** Server broadcasts updated board state, scores, and active player turn.
* **Field Specs and Data Types:**
  * `msg_type` (string): "STATE_UPDATE"
  * `board` (2D array of strings): Current board state.
  * `active_turn` (string): "X" or "O"
* **Example:**
  ```json
  {
    "msg_type": "STATE_UPDATE",
    "board": [["X", "", ""], ["", "O", ""], ["", "", ""]],
    "active_turn": "X"
  }
  ```

### 6. `GAME_OVER`
* **Direction:** Server -> Clients
* **Purpose & Description:** Server broadcasts final game outcome (Winner / Draw / Forfeit) and final scores.
* **Field Specs and Data Types:**
  * `msg_type` (string): "GAME_OVER"
  * `reason` (string): "WIN", "DRAW", or "FORFEIT"
  * `winner` (string): "X", "O", or "NONE"
* **Example:**
  ```json
  {
    "msg_type": "GAME_OVER",
    "reason": "WIN",
    "winner": "X"
  }
  ```

### 7. `ERROR`
* **Direction:** Server -> Client
* **Purpose & Description:** Server notifies client of out-of-turn move, invalid coordinates, or malformed message.
* **Field Specs and Data Types:**
  * `msg_type` (string): "ERROR"
  * `error_message` (string): Description of the error.
* **Example:**
  ```json
  {
    "msg_type": "ERROR",
    "error_message": "Invalid move: Space already occupied."
  }
  ```

### 8. `DISCONNECT`
* **Direction:** Client -> Server
* **Purpose & Description:** Client notifies server of intentional departure/quit.
* **Field Specs and Data Types:**
  * `msg_type` (string): "DISCONNECT"
* **Example:**
  ```json
  {
    "msg_type": "DISCONNECT",
  }
  ```


## 2. TCP Stream Packet Framing & Boundary Handling

### Framing Rule
* Every JSON object is UTF-8 encoded and terminated by a newline character \n (0x0A). The receiver accumulates incoming bytes into a stream buffer until a \n is encountered, extracts the complete line, and deserializes the JSON object.

### Wire Stream Example
```
{"msg_type":"STATE_UPDATE","board":[["X","X","X"],["","O",""],["","",""]],"active_turn":"NONE"}\n{"msg_type":"GAME_OVER","reason":"WIN","winner":"X"}\n
```

### Receiver Extraction Logic
1. The receiver collects bytes into a temporary `buffer` string/bytearray.
2. The loop checks for `\n` in the buffer.
3. If `\n` is found, it splits the buffer, extracts the content up to the `\n`, and the remaining bytes stay in the buffer for the next loop.


## 3. Connection Termination & Socket Lifecycle Management

### Graceful Application Disconnection
If a player quits, the client sends the DISCONNECT message type and closes the socket. Server interprets message and calls the GAME_OVER by forfeit, terminating the game.

### Abrupt Termination Handling
If the client loses connection, turns of computer, or the forces the process to close:
* The server program wraps `recv()` and `sendall()` in `try/except` blocks to catch `ConnectionResetError` and `BrokenPipeError`. Server then calls the GAME_OVER by forfeit and terminates the game.

### TCP 0-byte EOF Condition
If a 0-byte payload is detected, it is treated as an EOF, and the server triggers a FORFEIT disconnect.
