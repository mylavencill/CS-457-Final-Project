# Game Finite State Machine (FSM) Specification

```mermaid
stateDiagram-v2
    [*] --> INIT
    
    INIT --> WAITING_FOR_PLAYERS : Server Started & Listening
    
    WAITING_FOR_PLAYERS --> WAITING_FOR_PLAYERS : Client 1 Connects (Send LOBBY_WAIT)
    WAITING_FOR_PLAYERS --> GAME_START : Client 2 Connects
    
    GAME_START --> PLAYER_TURN : Initialize Board, Assign Roles (X/O), Broadcast Turn
    
    PLAYER_TURN --> EVALUATE_MOVE : Active Player Sends Valid MOVE
    PLAYER_TURN --> PLAYER_TURN : Invalid or Out-of-turn Move (Send ERROR back)
    
    EVALUATE_MOVE --> PLAYER_TURN : Valid Move, No Win/Draw (Toggle Active Player)
    EVALUATE_MOVE --> GAME_OVER : Victory or Draw Detected
    
    %% Error Handling & Disconnect State Transitions
    WAITING_FOR_PLAYERS --> CLEANUP : Client 1 Disconnects
    PLAYER_TURN --> GAME_OVER : Any Client Disconnects (Declare opponent win by forfeit)
    EVALUATE_MOVE --> GAME_OVER : Any Client Disconnects (Declare opponent win by forfeit)
    
    GAME_OVER --> CLEANUP : Broadcast Final Results
    
    CLEANUP --> WAITING_FOR_PLAYERS : Reset Board & State for subsequent rounds
    CLEANUP --> [*] : Server Shutdown
```
