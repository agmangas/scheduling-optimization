import itertools
import json
import logging
import pprint

import coloredlogs
from ortools.sat.python import cp_model

_logger = logging.getLogger(__name__)

_NUM_PARTICIPANTS = 50
_NUM_GAMES = 5
_NUM_ROUNDS = 4
_SOLUTION_LIMIT = 1
_MAX_REPEAT_MATCHUPS = 2


class PartialSolutionPrinter(cp_model.CpSolverSolutionCallback):
    def __init__(self, allocations, num_participants, num_games, num_rounds, limit):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self._allocations = allocations
        self._num_participants = num_participants
        self._num_games = num_games
        self._num_rounds = num_rounds
        self._solution_count = 0
        self._solution_limit = limit

    def on_solution_callback(self):
        self._solution_count += 1

        sol = []

        for r in range(self._num_rounds):
            the_round = []

            for g in range(self._num_games):
                game_participants = []

                for p in range(self._num_participants):
                    if self.Value(self._allocations[(p, g, r)]):
                        game_participants.append(p)

                the_round.append(tuple(game_participants))

            sol.append(the_round)

        _logger.info("Solution #%i:\n%s", self._solution_count, pprint.pformat(sol))
        _logger.info("Solution #%i (JSON):\n%s", self._solution_count, json.dumps(sol))

        if self._solution_count >= self._solution_limit:
            _logger.info("Stop search after %i solutions", self._solution_limit)
            self.StopSearch()

    def solution_count(self):
        return self._solution_count


def main():
    participants_per_game = int(_NUM_PARTICIPANTS / _NUM_GAMES)
    assert participants_per_game * _NUM_GAMES == _NUM_PARTICIPANTS

    model = cp_model.CpModel()

    allocations = {
        (p, g, r): model.NewBoolVar("alloc_p_%i_g_%i_r_%i" % (p, g, r))
        for p in range(_NUM_PARTICIPANTS)
        for g in range(_NUM_GAMES)
        for r in range(_NUM_ROUNDS)
    }

    # Each participant plays exactly one game per round

    for r in range(_NUM_ROUNDS):
        for p in range(_NUM_PARTICIPANTS):
            model.AddExactlyOne(allocations[(p, g, r)] for g in range(_NUM_GAMES))

    # Exactly 'participants_per_game' participants play each game

    for r in range(_NUM_ROUNDS):
        for g in range(_NUM_GAMES):
            num_game_part = [allocations[(p, g, r)] for p in range(_NUM_PARTICIPANTS)]
            model.Add(sum(num_game_part) == participants_per_game)

    round_matchups = {
        (r, p1, p2): model.NewBoolVar("matchup_r_%i_p1_%i_p2_%i" % (r, p1, p2))
        for p1, p2 in itertools.combinations(range(_NUM_PARTICIPANTS), 2)
        for r in range(_NUM_ROUNDS)
    }

    for p1, p2 in itertools.combinations(range(_NUM_PARTICIPANTS), 2):
        model.Add(
            sum(round_matchups[(r, p1, p2)] for r in range(_NUM_ROUNDS))
            <= _MAX_REPEAT_MATCHUPS
        )

    round_game_matchups = {
        (r, g, p1, p2): model.NewBoolVar(
            "matchup_r_%i_g_%i_p1_%i_p2_%i" % (r, g, p1, p2)
        )
        for p1, p2 in itertools.combinations(range(_NUM_PARTICIPANTS), 2)
        for g in range(_NUM_GAMES)
        for r in range(_NUM_ROUNDS)
    }

    for p1, p2 in itertools.combinations(range(_NUM_PARTICIPANTS), 2):
        for g in range(_NUM_GAMES):
            for r in range(_NUM_ROUNDS):
                model.AddImplication(
                    round_game_matchups[(r, g, p1, p2)], round_matchups[(r, p1, p2)]
                )

    for r in range(_NUM_ROUNDS):
        for g in range(_NUM_GAMES):
            for p1, p2 in itertools.combinations(range(_NUM_PARTICIPANTS), 2):
                model.AddImplication(
                    allocations[(p1, g, r)], round_game_matchups[(r, g, p1, p2)]
                ).OnlyEnforceIf(allocations[(p2, g, r)])

    solver = cp_model.CpSolver()
    solver.parameters.linearization_level = 0  # type: ignore
    solver.parameters.enumerate_all_solutions = True  # type: ignore

    solution_printer = PartialSolutionPrinter(
        allocations=allocations,
        num_participants=_NUM_PARTICIPANTS,
        num_games=_NUM_GAMES,
        num_rounds=_NUM_ROUNDS,
        limit=_SOLUTION_LIMIT,
    )

    solver.Solve(model, solution_printer)

    _logger.info(
        "Statistics:\n%s",
        pprint.pformat(
            {
                "Conflicts": solver.NumConflicts(),
                "Branches": solver.NumBranches(),
                "Wall time": solver.WallTime(),
                "Solutions found": solution_printer.solution_count(),
            }
        ),
    )


if __name__ == "__main__":
    coloredlogs.install(level=logging.DEBUG)
    main()
