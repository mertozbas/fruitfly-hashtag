"""Run inside .runtime/hardware-venv. SDK transport is a fake serial device."""
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock,patch
from scservo_sdk import PacketHandler
from so101.hardware_worker import read_only_port,inspect_arm,inventory
from so101.hardware_contract import JOINTS,calibration


class SerialBoundaryTests(unittest.TestCase):
    def test_real_sdk_write_methods_blocked_before_transport(self):
        port=read_only_port('FAKE');port.ser=Mock();port.ser.write.side_effect=len
        sdk=PacketHandler(0)
        for address,value in [(40,1),(40,0),(31,123),(42,2048),(9,700)]:
            port.is_using=False
            with self.assertRaises(PermissionError):sdk.write2ByteTxRx(port,1,address,value)
        port.ser.write.assert_not_called()

    def test_real_sdk_read_serializes_a_valid_read_packet(self):
        port=read_only_port('FAKE');port.ser=Mock();port.ser.write.side_effect=len
        sdk=PacketHandler(0)
        # Tx-only path exercises the installed SDK's packet encoder, no physical I/O.
        sdk.readTx(port,1,56,2)
        sent=port.ser.write.call_args.args[0]
        self.assertEqual(sent[2:7],bytes([1,4,2,56,2]))

    def test_changed_calibration_prevents_even_opening_port(self):
        with patch('so101.hardware_worker.calibration',return_value=dict(valid=True,sha256='new')),patch('so101.hardware_worker.read_only_port') as port:
            with self.assertRaisesRegex(ValueError,'değişti'):inspect_arm('FAKE','fake.json','old',1)
            port.assert_not_called()

    def test_inventory_cannot_open_ports_or_cameras(self):
        with patch('serial.Serial') as serial,patch('cv2.VideoCapture') as camera,patch('so101.hardware_worker.emit') as emit:
            inventory();serial.assert_not_called();camera.assert_not_called()
            self.assertFalse(emit.call_args.kwargs['motors_opened']);self.assertFalse(emit.call_args.kwargs['cameras_opened'])

    def test_complete_six_motor_inspection_uses_only_reads_and_preserves_torque(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cal.json'
            motors={name:dict(id=i,drive_mode=0,homing_offset=-188,range_min=700,range_max=3400) for i,name in enumerate(JOINTS,1)}
            path.write_text(json.dumps(motors));sha=calibration(path)['sha256']
            port=Mock(is_open=True);sdk=Mock()
            registers={3:777,9:700,11:3400,31:2048+188,56:2050,40:1,33:0,60:0,62:75,63:29}
            def read(port,motor,address):return registers[address],0,0
            sdk.read1ByteTxRx.side_effect=read;sdk.read2ByteTxRx.side_effect=read
            with patch('so101.hardware_worker.read_only_port',return_value=port),patch('scservo_sdk.PacketHandler',return_value=sdk),patch('so101.hardware_worker.sys.platform','win32'),patch('so101.hardware_worker.emit') as emit:
                inspect_arm('FAKE',path,sha,.01)
            state=emit.call_args.kwargs
            self.assertTrue(state['calibration_match']);self.assertEqual(len(state['motors']),6)
            self.assertTrue(all(m['torque_enabled'] for m in state['motors']))
            self.assertTrue(all(m['value']==0 for m in state['motors'][:5]))
            self.assertEqual(set(c[0] for c in sdk.mock_calls),{'read1ByteTxRx','read2ByteTxRx'})
            port.closePort.assert_called_once()


if __name__=='__main__':unittest.main()
