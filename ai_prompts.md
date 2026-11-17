## AI Prompting & Constraint Strategy

### Constraint Strategy
To ensure that my exact specifications are used, I will attach my protocol_blueprint.md and my fsm_specification.md in all of my prompts. 

### *Documented Prompts:*

### Sprint 3:
**Prompt - Initial implementation request**
#### "can you help me implement sprint 3 of my project using the exact specifications that i have required in my planning documents on github (protocol_blueprint.md, fsm_specification.md, and concurrency_design.md). make sure to not change any rules and ensure it strictly follows the blueprint and specifications. it must follow the attached sprint 3 requirements and rubric. this is still an ongoing project so don't implement anything that is not necessary for this specific sprint description. if there is any input or answers needed from me, or conflicting instructions please state them before implementing the program."

- Context: Linked GitHub repo, Sprint 3 instructions
- Result: The AI read my docs and listed contradictions in my documents and open questions (port, scores, rematch behavior).
- My review: Read and went through the questions and contradictions.

**Prompt - Design decisions**
#### "I would like the first client to connect to be X and second as O. scores on all GAME_OVER messages, "NONE" allowed, clients stay connected for rematches, there is no default port."

- Result: Generated server.py and client.py.
- My review: Imported both files locally and read them, inspecting them to make sure they fit with my design documents.

**Prompt - Ran into issues running it**
#### "why is my client.py returning this error when run? it is throwing a DNS hostname error and no alternative names or ports work."

- Context: Screenshots of the client DNS error and the running server.
- Result: Pointed out that the assignment description states that initial development and software testing can take place on localhost.
- My review: Ran client successfully with localhost, testing it worked with disconnects, playing full games, and rematches.

**Prompt - Reviewing documentation based on implemented program**
#### "what changes would you suggest i make to my current blueprint, diagrams, and FSM that need to directly reflect the code implemented? i don't want any potential improvements to them, just changes to correct the contradictions that currently exist and the addition of rematch functionality."

- Result: A list of corrections to my protocol, FSM, sequence and concurrency docs.
- My Review: Went through the suggested changes and updated my repo files with the changes I deemed necessary.
