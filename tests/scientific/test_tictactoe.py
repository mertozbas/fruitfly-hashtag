"""Game rules, neural inference, export and stale-action contracts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
import io
import os
import numpy as np
from scipy import sparse
from odor_policy import Circuit
from tictactoe.rules import encode,play,reachable,turn,validate,winner,PERMUTATIONS
from tictactoe.policy import Policy,torch_model
from tictactoe.teacher import targets


class RulesTests(unittest.TestCase):
    def test_complete_reachable_space(self):
        boards=reachable();self.assertEqual(len(boards),5478)
        decisions=[b for b in boards if not winner(b) and 0 in b]
        self.assertEqual(len(decisions),4520)
        self.assertEqual(len({tuple(encode(b)[0]) for b in decisions}),627)

    def test_reject_impossible_and_finished_boards(self):
        for b in ([0]*8,[0]*8+[float('nan')],[1,1,1,-1,-1,-1,0,0,0],[-1]+[0]*8):
            with self.assertRaises(ValueError):validate(b)
        with self.assertRaises(ValueError):play((1,1,1,-1,-1,0,0,0,0),5)
        with self.assertRaises(ValueError):play((1,0,0,0,0,0,0,0,0),0)
        with self.assertRaises(ValueError):play((0,)*9,0,-1)
        with self.assertRaises(ValueError):play((0,)*9,1.5)

    def test_tactical_teacher_examples(self):
        win=(1,1,0,-1,-1,0,0,0,0)
        self.assertEqual(targets(win)[2],1)
        block=(1,1,0,0,-1,0,0,0,0)
        best=targets(block);self.assertEqual([i for i,v in best.items() if v==max(best.values())],[2])

    def test_symmetry_has_one_input_and_correct_move_mapping(self):
        board=np.array([1,1,0,-1,-1,0,0,0,0]);original=encode(board)[0]
        for p in PERMUTATIONS:
            b=board[p];x,mapping=encode(b);np.testing.assert_array_equal(original,x)
            chosen=int(np.flatnonzero(mapping==int(np.flatnonzero(p==2)[0]))[0])
            self.assertEqual(targets(tuple(b))[int(mapping[chosen])],1)


class NeuralTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        groups=['Touch','VNC_relay','VNC_premotor','Motor'];records=[]
        for i in range(3):
            p=self.root/f'layer{i}.npz';sparse.save_npz(p,sparse.eye(5,dtype=np.float32,format='csr'))
            records.append(dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        ids=self.root/'body_ids.npz';np.savez_compressed(ids,**{g:np.arange(i*5,i*5+5) for i,g in enumerate(groups)},orn_side=[0]*5)
        (self.root/'circuit.json').write_text(json.dumps(dict(task='tictactoe',group_order=groups,groups={g:5 for g in groups},layers=records,
            body_ids_sha256=hashlib.sha256(ids.read_bytes()).hexdigest())))
        self.circuit=Circuit(self.root);self.actor=torch_model(self.circuit);self.path=self.root/'trained.npz';self.actor.save(self.path)

    def test_torch_numpy_and_live_activity(self):
        import torch
        p=Policy(self.path)
        for b in [(0,)*9,(1,0,0,0,-1,0,0,0,0),(1,1,0,-1,-1,0,0,0,0)]:
            chosen,layers,d=p.activity(b);x,mapping=encode(b)
            with torch.no_grad():expected=self.actor(torch.from_numpy(x)[None]).numpy()[0]
            np.testing.assert_allclose(expected,np.array(d['logits'])[mapping],atol=2e-6)
            self.assertEqual(b[chosen],0);self.assertAlmostEqual(sum(d['probabilities']),1,places=6)
            self.assertEqual([len(x) for x in layers],[5]*4)
            np.testing.assert_allclose(layers[-1]@p.decoder+p.bias,np.array(d['logits'])[mapping],atol=1e-6)
            _,silent,_=p.activity(b,True);self.assertTrue(all(np.count_nonzero(x)==0 for x in silent))

    def test_nonanatomical_and_nonfinite_parameters_rejected(self):
        with np.load(self.path) as s:state={k:s[k].copy() for k in s.files}
        bad=dict(state);bad['weight']=state['weight'].copy();bad['weight'][0,1]=1
        np.savez_compressed(self.path,**bad)
        with self.assertRaisesRegex(ValueError,'mask'):Policy(self.path)
        bad=dict(state);bad['decoder']=np.full_like(state['decoder'],np.nan);np.savez_compressed(self.path,**bad)
        with self.assertRaises(ValueError):Policy(self.path)

    def test_portable_export_needs_no_teacher_or_source_repo(self):
        from tictactoe.export import archive
        output=self.root/'portable';output.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive(self.path))) as z:
            self.assertNotIn('tictactoe/teacher.py',z.namelist());z.extractall(output)
        result=subprocess.run([sys.executable,'infer.py',*['0']*9],cwd=output,capture_output=True,text=True,check=True)
        self.assertIn(json.loads(result.stdout)['cell_zero_based'],range(9))


class LiveInputTests(unittest.TestCase):
    def test_server_rejects_wrong_turn_stale_and_occupied_moves(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        import threading
        import lab_server as server
        from fastapi import HTTPException
        board=[0,0,0,0,1,0,0,0,0];commands=[]
        state=dict(episode=2,paused=False,game=dict(waiting_for_human=True,agent=1,board=board))
        fake=SimpleNamespace(behavior='tictactoe',sim_lock=threading.RLock(),read=lambda:state,control=commands.append)
        with patch.object(server,'runtime',fake):
            for args,status in [(dict(cell=1,episode=1,board=board),409),(dict(cell=4,episode=2,board=board),422)]:
                with self.assertRaises(HTTPException) as e:server.game_move(server.GameMove(**args))
                self.assertEqual(e.exception.status_code,status)
            self.assertEqual(len(commands),0)
            server.game_move(server.GameMove(cell=1,episode=2,board=board));self.assertEqual(commands[0]['cell'],1)
            state['paused']=True
            with self.assertRaises(HTTPException):server.game_move(server.GameMove(cell=1,episode=2,board=board))


@unittest.skipUnless(os.environ.get('SO101_TEST_ASSETS')=='1','Requires local SO-101 meshes and MuJoCo renderer')
class CameraTests(unittest.TestCase):
    def test_next_token_does_not_average_a_placed_similar_colour(self):
        from tictactoe.scene import GameEnv,SUPPLY
        from tictactoe.vision import Eyes
        env=GameEnv(token_style='blocks');self.addCleanup(env.close)
        for cell,player in [(4,1),(8,-1),(7,1),(1,-1)]:env.virtual_move(cell,player)
        env.begin_placement(3);eyes=Eyes(env);self.addCleanup(eyes.close);eyes.capture()
        measured=eyes.token(np.r_[SUPPLY[2][:2],.015])
        self.assertTrue(measured['valid'])
        self.assertLess(np.linalg.norm(measured['position'][:2]-SUPPLY[2][:2]),.004)

    def test_camera_recognizes_both_symbols_in_every_cell(self):
        from tictactoe.scene import GameEnv
        from tictactoe.vision import Eyes
        for style in ('printed','blocks'):
            env=GameEnv(token_style=style);eyes=Eyes(env)
            try:
                for cell in range(9):
                    env.reset();env.virtual_move(cell,1);env.virtual_move((cell+4)%9,-1);eyes.capture()
                    observed=eyes.board()
                    self.assertTrue(observed['valid'],(style,cell,observed))
                    self.assertEqual(observed['board'],list(env.board))
            finally:eyes.close();env.close()


if __name__=='__main__':unittest.main()
