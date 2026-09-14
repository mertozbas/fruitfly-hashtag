"""Real worker lifecycle with a patched serial transport; never opens hardware."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[2]
BOOTSTRAP='''
import json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()/'tests/hardware'))
from test_calibration_motor import VirtualSerial
from so101.calibration_motor import main
serial=VirtualSerial()
with patch('serial.Serial',return_value=serial),patch('fcntl.ioctl'):
    try:main()
    finally:Path(sys.argv[sys.argv.index('--directory')+1],'wire.json').write_text(json.dumps(serial.writes))
'''


class CalibrationLifecycleTests(unittest.TestCase):
    def exercise(self,ending):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/('a'*32);target=Path(temp)/'follower.json'
            process=subprocess.Popen([sys.executable,'-u','-c',BOOTSTRAP,'--port','OFFLINE_TEST','--target',str(target),
                '--directory',str(directory),'--identity','{"serial_number":"VIRTUAL"}'],cwd=ROOT,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.addCleanup(lambda:process.kill() if process.poll() is None else None)
            records=queue.Queue()
            def read():
                for line in process.stdout:records.put(json.loads(line))
            reader=threading.Thread(target=read,daemon=True);reader.start()
            state=records.get(timeout=5);self.assertEqual(state['stage'],'backup')
            process.stdin.write(json.dumps(dict(op='release',revision=state['revision'],supported=True))+'\n');process.stdin.flush()
            while state['stage']!='reference':state=records.get(timeout=5)
            if ending=='eof':process.stdin.close()
            elif ending=='sigterm':process.terminate()
            process.wait(timeout=19 if ending=='lease' else 5);reader.join(1)
            error=process.stderr.read();process.stdout.close();process.stderr.close()
            if not process.stdin.closed:process.stdin.close()
            self.assertEqual(process.returncode,0,error)
            result=json.loads((directory/'status.json').read_text());self.assertEqual(result['stage'],'cancelled')
            writes=json.loads((directory/'wire.json').read_text())
            self.assertTrue(writes);self.assertFalse(any(a==40 and v!=0 for _,a,v in writes))
            for motor in range(1,7):
                for address,value in [(9,700),(11,3400),(31,2236),(40,0),(55,1)]:
                    self.assertEqual([v for m,a,v in writes if m==motor and a==address][-1],value)
            self.assertFalse(target.exists())

    def test_stdin_loss_restores_motor_settings(self):self.exercise('eof')
    def test_sigterm_restores_motor_settings(self):self.exercise('sigterm')
    def test_missing_heartbeat_restores_after_lease(self):self.exercise('lease')


if __name__=='__main__':unittest.main()
