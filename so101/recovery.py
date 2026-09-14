"""Bounded retry supervision from observations; never produces motor commands.

A failed grasp resets learned phase memory, not the robot or object poses. The
neural policy still chooses every motion. This is engineered supervision, not
evidence that the network independently learned when to retry.
"""
class RetrySupervisor:
    def __init__(self,max_attempts=3):
        if not 1<=max_attempts<=5:raise ValueError('Expected 1 to 5 attempts')
        self.max_attempts=max_attempts
        self.reset()

    def reset(self):
        self.attempt=1;self.events=[];self.started=0.;self.lost_since=None
        self.held=False;self.exhausted=False
        self.attempt_lifted=False

    def observe(self,obs,time_s,policy,perception=None):
        holding=bool(obs[22]);inside=bool(obs[24]);height=float(obs[21])*.15
        if self.attempt>1 and perception is None:
            self.attempt_lifted|=holding and height>.07
            obs[23]=float(self.attempt_lifted)
        if holding:self.held=True;self.lost_since=None
        elif self.held and not inside:
            if self.lost_since is None:self.lost_since=time_s
        reason=None
        if self.lost_since is not None and time_s-self.lost_since>=.6 and height<.045:
            reason='grasp_lost'
        elif not self.held and not holding and not inside and time_s-self.started>=12.:
            reason='no_grasp_progress'
        if reason:
            if self.attempt>=self.max_attempts:
                self.exhausted=True
                return False
            self.attempt+=1;self.started=time_s;self.held=False;self.lost_since=None;self.attempt_lifted=False
            self.events.append(dict(attempt=self.attempt,time_s=round(time_s,4),reason=reason))
            policy.reset()
            # Per-attempt sensory memory must agree with the new attempt.
            if perception:perception.lifted=False;perception.held_offset=None
            obs[23]=0.
            return True
        return False

    def status(self):
        return dict(version=2,attempt=self.attempt,max_attempts=self.max_attempts,exhausted=self.exhausted,
                    retries=len(self.events),events=list(self.events),same_scene=True,
                    source='observation watchdog resets learned phase memory; neural motor actions retained')
