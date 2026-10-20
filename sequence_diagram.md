# State Synchronization & Mermaid Sequence Diagram

This sequence diagram shows the round-trip flow of a Tic-Tac-Toe move based on my protocol blueprint. It models successful moves, out-of-turn rejections, board space validations, and synchronous broadcasts.

```mermaid
sequenceDiagram
    autonumber
    actor C1 as Client 1 (Player X)
    participant S as Game Server (Main Memory/Threads)
    actor C2 as Client 2 (Player O)
    
    C1->>S: {"msg_type": "MOVE", "role": "X", "row": 1, "col": 1}\n
    
    Note over S: Server acquires game_state_lock
    Note over S: Validates: Is active_turn == "X"?<br/>Is game_board[1][1] == ""?
    
    alt Valid Move & Active Turn
        Note over S: game_board[1][1] = "X"
        
        alt Move results in Victory (3-in-a-row)
            Note over S: Increment Player X score in round_scores
            S-->>C1: {"msg_type": "STATE_UPDATE", "board": [...], "active_turn": "NONE"}\n
            S-->>C2: {"msg_type": "STATE_UPDATE", "board": [...], "active_turn": "NONE"}\n
            S-->>C1: {"msg_type": "GAME_OVER", "reason": "WIN", "winner": "X", "scores": {"X":1, "O":0}}\n
            S-->>C2: {"msg_type": "GAME_OVER", "reason": "WIN", "winner": "X", "scores": {"X":1, "O":0}}\n
            Note over S: Clear board for next match
            
        else Normal Move (No Win/Draw)
            Note over S: active_turn = "O"
            S-->>C1: {"msg_type": "STATE_UPDATE", "board": [...], "active_turn": "O"}\n
            S-->>C2: {"msg_type": "STATE_UPDATE", "board": [...], "active_turn": "O"}\n
        end
        
    else Invalid Move (Space Occupied)
        S-->>C1: {"msg_type": "ERROR", "error_message": "Invalid move: Space already occupied."}\n
        
    else Out-of-Turn Move (Player O tries to go early)
        C2->>S: {"msg_type": "MOVE", "role": "O", "row": 0, "col": 0}\n
        S-->>C2: {"msg_type": "ERROR", "error_message": "Not your turn."}\n
    end
    
    Note over S: Server releases game_state_lock
```
