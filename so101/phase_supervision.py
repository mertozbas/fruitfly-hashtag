"""Engineered task-progress checks, separate from the anatomical neural core.

These checks permit/reject learned phase choices. They produce no XYZ target,
joint angle, object pose or gripper command. The neural motor readout supplies
the action. This is hybrid task supervision, not independently learned logic.
"""
import numpy as np


def feasible_phases(observation):
    o=np.asarray(observation)[...,:30]
    tcp=o[...,12:15]*.15+[.06,-.18,.06]
    cube=tcp+o[...,15:18]*.15;goal=cube+o[...,18:21]*.15
    holding=o[...,22].astype(bool);inside=o[...,24].astype(bool);lifted=o[...,23].astype(bool)
    opened=o[...,5]>.7;pickup=~holding & (~inside | ~lifted)
    xy=np.linalg.norm(cube[...,:2]-tcp[...,:2],axis=-1)
    gxy=np.linalg.norm(goal[...,:2]-tcp[...,:2],axis=-1)
    allowed=np.stack([
        pickup & ~(opened & (xy<.004) & (tcp[...,2]<.088)),
        pickup & (cube[...,2]<.04) & (xy<.012) & (tcp[...,2]<cube[...,2]+.075) & opened
            & ~(opened & (xy<.004) & (tcp[...,2]<cube[...,2]+.009)),
        (xy<.006) & (tcp[...,2]<cube[...,2]+.012) & ~(holding & (o[...,25]>=.7)),
        holding & (o[...,25]>=.4) & ~(holding & (tcp[...,2]>.105)),
        holding & (cube[...,2]>.065) & (tcp[...,2]>.095) & ~(holding & (gxy<.004)),
        holding & inside & (gxy<.008) & ~(holding & (tcp[...,2]<.047)),
        inside & (tcp[...,2]<.055) & ~(inside & lifted & (o[...,5]>.75)),
        inside & lifted & (o[...,5]>.75),
    ],axis=-1)
    # Reacquisition is the bounded fallback; its motor target is still learned.
    allowed[...,0] |= ~allowed.any(axis=-1)
    return allowed
