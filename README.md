# Game event optimization

Solution to a scheduling problem for an event consisting of **P** participants, **R** rounds and **G** games per round. All games in a given round take place at the same time, therefore a participant can only play a single game in a round. The problem is maximizing the number of different matchups between participants (i.e. minimizing the number of times that the same pair of participants face each other during the entire event).

The implementation is based on [Google OR-Tools](https://developers.google.com/optimization/), a framework aimed at solving combinatorial optimization problems.
