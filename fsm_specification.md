# Game Finite State Machine (FSM) Specification

```mermaid
stateDiagram-v2
    [*] --> INIT
    
    INIT --> WAITING_FOR_PLAYERS : Server Started and Listening
    
    WAITING_FOR_PLAYERS --> WAITING_FOR_PLAYERS : Client 1 Connects
    WAITING_FOR_PLAYERS --> GAME_START : Client 2 Connects
    
    GAME_START --> PLAYER_TURN : Initialize Board, Assign Roles, Announce Turn
    
    PLAYER_TURN --> EVALUATE_MOVE : Active Player Sends Valid MOVE
    PLAYER_TURN --> PLAYER_TURN : Invalid Move
    
    EVALUATE_MOVE --> PLAYER_TURN : Valid Move, No Win/Draw
    EVALUATE_MOVE --> GAME_OVER : Victory or Draw
    
    %% Error Handling & Disconnect State Transitions
    WAITING_FOR_PLAYERS --> CLEANUP : Client 1 Disconnects
    PLAYER_TURN --> GAME_OVER : Any Client Disconnects
    EVALUATE_MOVE --> GAME_OVER : Any Client Disconnects
    
    GAME_OVER --> CLEANUP : Announce Results
    
    CLEANUP --> WAITING_FOR_PLAYERS : Reset Board and State
    CLEANUP --> [*] : Server Shutdown
```
