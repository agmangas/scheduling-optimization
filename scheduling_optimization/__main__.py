import itertools
import json
import logging
import pprint

import coloredlogs
import numpy
from ortools.sat.python import cp_model

_logger = logging.getLogger(__name__)

_NUM_PARTICIPANTS = 50
_NUM_GAMES = 5
_NUM_ROUNDS = 4
_SOLUTION_LIMIT = 1
_MAX_REPEAT_MATCHUPS = 2


def count_repeated_matchups(sol):
    flat_sol = [item for the_round in sol for item in the_round]

    counts = {}

    for p1, p2 in itertools.combinations(range(_NUM_PARTICIPANTS), 2):
        counts[(p1, p2)] = counts.get((p1, p2), 0)

        for item in flat_sol:
            if p1 in item and p2 in item:
                counts[(p1, p2)] += 1

    return sum(val - 1 for val in counts.values() if val > 1)


def get_avg_meetups(sol):
    flat_sol = [item for the_round in sol for item in the_round]

    meetups = {}

    for p in range(_NUM_PARTICIPANTS):
        meetups[p] = meetups.get(p, [])

        for the_game in flat_sol:
            if p in the_game:
                meetups[p].extend([item for item in the_game if item != p])

    meetups = {key: set(val) for key, val in meetups.items()}
    stats_arr = numpy.array([len(val) for val in meetups.values()])

    _logger.debug(
        "Meetups stats: %s",
        {
            "mean": numpy.mean(stats_arr),
            "median": numpy.median(stats_arr),
            "min": numpy.min(stats_arr),
            "max": numpy.max(stats_arr),
        },
    )

    return numpy.mean(stats_arr)


def build_solution_c_arr_template(sol, tag_len=12):
    entries = []

    for p in range(_NUM_PARTICIPANTS):
        games = []

        for the_round in sol:
            for idx_game, the_game in enumerate(the_round):
                if p in the_game:
                    games.append(idx_game)

        assert len(games) == _NUM_ROUNDS

        entries.append(
            '{{"{tag}", {{{games_idx}}}}}'.format(
                tag="F" * tag_len, games_idx=", ".join([str(item) for item in games])
            )
        )

    assert len(entries) == _NUM_PARTICIPANTS

    return ", \n".join(entries)


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

        _logger.info(
            "Solution #%i (avg. meetups): %s",
            self._solution_count,
            get_avg_meetups(sol),
        )

        _logger.info(
            "Solution #%i (C arr):\n%s",
            self._solution_count,
            build_solution_c_arr_template(sol),
        )

        _logger.info(
            "Solution #%i (repeated matchups): %s",
            self._solution_count,
            count_repeated_matchups(sol),
        )

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
