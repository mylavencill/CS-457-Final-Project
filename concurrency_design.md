# Server Concurrency & Thread-Safety Design

## 1. Server Concurrency Architecture & Connection Lifecycle
### Server Concurrency Architecture
**Chosen Architecture:** Option A - Multi-Threading (`threading.Thread`)
To handle two simultaneous client connections without blocking, the server utilizes a multi-threaded architecture.
- The main server thread runs a continuous `accept()` loop.
- When a client connects, the server spawns a dedicated thread (`threading.Thread`) for that specific client.
- This lets Player X and Player O to be connected concurrently.

### Connection Lifecycle:
1. **Listening Socket Accept:** The server binds to the interface and listens. The main thread blocks on `socket.accept()`.
2. **Client Connection:** When a client connects, the server assigns the new client socket to a player alias and "X" or "O".
3. **Thread Creation:** A new `threading.Thread` is created.
4. **Active Game Loop:** The thread enters a loop, waiting for `MOVE` or `DISCONNECT` messages. It updates as messages with updates to the game state come in.
5. **Client Socket Teardown:** If a `DISCONNECT` is received, the thread triggers a `GAME_OVER` (FORFEIT) announcement to the remaining player, closes its socket, and terminates.


## 2. Thread Safety, Lock Acquisition & State Isolation Strategy

Because client requests are processed concurrently, they must access and change the shared Tic-Tac-Toe board. To prevent race conditions, a mutex (`threading.Lock()`) is utilized.

The following variables are in the server's shared memory:
- **`game_board`**: A 2D array `[["", "", ""], ["", "", ""], ["", "", ""]]` representing the Tic-Tac-Toe grid.
- **`active_turn`**: A string tracking the current turn (`"X"` or `"O"`).
- **`connected_clients`**: A dictionary mapping roles (`"X"`, `"O"`) to their active socket objects.
- **`round_scores`**: A dictionary `{"X": 0, "O": 0}` tracking the leaderboard.

A lock, `game_state_lock = threading.Lock()`, isolates all mutations.

1. **Wait:** When a thread gets a `MOVE` request, it calls `game_state_lock.acquire()`.
2. **Turn and Move Validation:** 
   - Out of Turn: The server checks if `request["role"] == active_turn`. If not, it releases the lock and sends an `ERROR` (`"Not your turn"`) to that client.
   - Invalid Move: The server checks if `game_board[row][col] == ""`. If occupied, it releases the lock and sends an `ERROR` (`"Invalid move: Space already occupied."`).
3. **State Mutation:** If valid, `game_board[row][col] = role`. The server checks for a win or draw. If no win, it toggles `active_turn`.
4. **Synchronous Broadcast:** While holding the lock, the server loops through `connected_clients` and sends a `STATE_UPDATE` to all clients. 
5. **Release:** Finally, `game_state_lock.release()` is called.

### 2.3 Score & Leaderboard Synchronization Design
- **Score Storage:** Round scores are stored in the server's shared memory as `{"X": 0, "O": 0}`.
- **Broadcast Logic:** If a move results in a win, the server increases the winner's score in memory. It then announces a `GAME_OVER` containing `"reason": "WIN"` and `"winner": "X"`. The server appends the updated scores to the broadcast so both clients can update their leaderboards at the same time before the board resets.
