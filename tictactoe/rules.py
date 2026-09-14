"""Deterministic game contract. No strategy or look-ahead in this module."""
import numpy as np

LINES=((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))
PERMUTATIONS=tuple(np.rot90(np.fliplr(np.arange(9).reshape(3,3)) if flip else np.arange(9).reshape(3,3),k).ravel()
                   for flip in (False,True) for k in range(4))


def winner(board):
    for a,b,c in LINES:
        if board[a] and board[a]==board[b]==board[c]:return int(board[a])
    return 0


def validate(board):
    raw=np.asarray(board)
    if raw.shape!=(9,) or not np.isin(raw,(-1,0,1)).all():raise ValueError('Expected nine empty/X/O cells')
    b=tuple(int(v) for v in raw)
    x,o=b.count(1),b.count(-1)
    wins={b[a] for a,c,d in LINES if b[a] and b[a]==b[c]==b[d]}
    if x not in (o,o+1) or len(wins)>1 or (1 in wins and x!=o+1) or (-1 in wins and x!=o):
        raise ValueError('Impossible board or turn counts')
    return b


def turn(board):
    b=validate(board)
    if winner(b) or 0 not in b:raise ValueError('Game has ended')
    return 1 if b.count(1)==b.count(-1) else -1


def play(board,cell,player=None):
    b=list(validate(board));actual=turn(b)
    if type(cell) not in (int,np.int64,np.int32) or not 0<=cell<9:raise ValueError('Cell must be 0..8')
    if player is not None and player!=actual:raise ValueError('Wrong turn')
    if b[cell]:raise ValueError('Occupied cell')
    b[cell]=actual
    return tuple(b)


def encode(board):
    """Canonical D4 orientation; one-hot own/empty/opponent cells only.

    The permutation maps canonical indices back to the displayed board.
    No winning lines, solver scores or hand-engineered tactics are inputs.
    """
    b=np.asarray(validate(board),np.int8)*turn(board)
    permutation=min(PERMUTATIONS,key=lambda p:tuple(b[p]))
    canonical=b[permutation]
    return np.eye(3,dtype=np.float32)[canonical+1].ravel(),permutation.copy()


def reachable():
    seen=set()
    def visit(b):
        if b in seen:return
        seen.add(b)
        if winner(b) or 0 not in b:return
        for i,v in enumerate(b):
            if not v:visit(play(b,i))
    visit((0,)*9)
    return sorted(seen)
