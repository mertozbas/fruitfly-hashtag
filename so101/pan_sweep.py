"""Explicit larger/faster request, restricted to the previously tested pan joint.

At most 340 encoder counts (29.88 deg), five counts per command and native
velocity 60. All body torque stays on; no EEPROM/torque/other-joint writes.
Restore native velocity 20 on success or failure. No automatic repeat.
"""
from .alignment_probe import ProbeBus
from .range_probe import RangeBus
from .hardware_contract import assert_read_packet


class PanSweepBus(RangeBus):
    step_counts=5

    def __init__(self,port,span):
        if type(span) is not int or not 1<=span<=340:raise ValueError('Pan sweep is limited to 340 counts')
        ProbeBus.__init__(self,port)
        self.motor_id=1;self.span=span;self.direction=1;self.tracking_limit=16
        self.may_be_on=True;self.speed_changed=False

    def guard(self,packet):
        p=bytes(packet)
        if len(p)>4 and p[4] in (1,2):return assert_read_packet(p)
        if self.phase not in ('speed_setup','speed_restore'):return super().guard(p)
        if (len(p)!=9 or p[:2]!=b'\xff\xff' or p[2]!=1 or p[3]!=5 or p[4]!=3
                or p[5]!=46 or sum(p[2:])&255!=255):raise PermissionError('Only pan velocity may be configured')
        data=p[6:-1];value=int.from_bytes(data,'little')
        if self.permit!=(46,data):raise PermissionError('Missing pan velocity permit')
        self.permit=None
        if value!=(60 if self.phase=='speed_setup' else 20):raise PermissionError('Unreviewed pan velocity')
        return p

    def prepare(self,q,saved):
        report=super().prepare(q,saved)
        report.update(native_velocity=60,native_velocity_before=20,maximum_command_step_counts=5,
                      explicit_pan_sweep=True,note='Only pan motor 1: reviewed 29.88-degree range, 16-count tracking lead, unchanged coarse return tolerance')
        return report

    def begin_motion(self):
        self.phase='speed_setup';self.speed_changed=True
        self.write(46,60);self.phase='move'

    def finish(self):
        errors=[]
        # A failed speed setup has not changed the position target.
        if self.phase!='speed_setup':errors=super().finish()
        if self.speed_changed:
            try:
                self.phase='speed_restore';self.write(46,20);self.speed_changed=False
            except Exception as exc:errors.append(str(exc))
        self.phase='done';return errors
