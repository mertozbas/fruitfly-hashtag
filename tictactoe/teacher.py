"""Offline minimax teacher/evaluator. Never imported by live inference."""
from functools import lru_cache
from .rules import play,turn,winner


@lru_cache(None)
def value(board):
    won=winner(board)
    if won:return -1
    if 0 not in board:return 0
    return max(-value(play(board,i)) for i,v in enumerate(board) if not v)


def targets(board):
    turn(board)
    return {i:-value(play(board,i)) for i,v in enumerate(board) if not v}
