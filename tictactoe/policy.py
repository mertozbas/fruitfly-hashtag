"""Board -> learned anatomical circuit -> nine logits -> legal move mask.

No solver, lookup table, LLM or tactical fallback is used at inference.
The D4 coordinate adapter is deterministic; all strategic scores are neural.
"""
import json
from pathlib import Path
import shutil
import numpy as np
from scipy import sparse
from scipy.special import expit,softmax
from odor_policy import Circuit
from .rules import encode,turn,validate

RESPONSE_GAINS=(12.,16.,16.)


def prepare(directory):
    from task_circuit import build
    source=build('terrain');directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for name in ('body_ids.npz','layer0.npz','layer1.npz','layer2.npz'):shutil.copy2(source/name,directory/name)
    metadata=json.loads((source/'circuit.json').read_text())
    metadata.update(task='tictactoe',input_encoding='board_onehot_d4_v1',response_gains=list(RESPONSE_GAINS),
        scope='MaleCNS Touch/VNC/Motor subgraph repurposed for board strategy. Artificial 27-feature encoder and nine-cell decoder; engineered sigmoid responses; not a biological game circuit or whole brain.')
    (directory/'circuit.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return Circuit(directory)


class Policy:
    def __init__(self,path):
        path=Path(path);self.circuit=Circuit(path.parent);self.task='tictactoe'
        if self.circuit.metadata.get('task')!=self.task:raise ValueError('Expected tic-tac-toe circuit')
        with np.load(path,allow_pickle=False) as s:
            self.has_motor='motor_encoder' in s
            if str(s['task'])!=self.task or str(s['circuit_identity'])!=self.circuit.identity:raise ValueError('Checkpoint/circuit mismatch')
            for key in ('encoder','encoder_bias','decoder','bias'):setattr(self,key,s[key].copy())
            weights=[s['weight0'].copy(),s['weight1'].copy(),s['weight'].copy()]
        expected={'encoder':(27,self.circuit.layers[0].shape[0]),'encoder_bias':(self.circuit.layers[0].shape[0],),
                  'decoder':(self.circuit.layers[2].shape[1],9),'bias':(9,)}
        for key,shape in expected.items():
            a=getattr(self,key)
            if a.shape!=shape or not np.isfinite(a).all():raise ValueError('Invalid '+key)
        self.layers=[]
        for w,base in zip(weights,self.circuit.layers):
            b=base.toarray();mask=b!=0
            if w.shape!=b.shape or not np.isfinite(w).all() or np.any(w[~mask]!=0):raise ValueError('Invalid anatomical mask')
            ratios=w[mask]/b[mask]
            if np.any(ratios<np.exp(-1.5)-1e-5) or np.any(ratios>np.exp(1.5)+1e-5):raise ValueError('Invalid synaptic gain')
            self.layers.append(sparse.csr_matrix(w))
        self.sums=[np.maximum(np.asarray(w.sum(0)).ravel(),1e-8) for w in self.layers]

    def activity(self,board,silenced=False):
        board=validate(board);x,permutation=encode(board)
        h=expit(x@self.encoder+self.encoder_bias);layers=[h]
        if silenced:h=np.zeros_like(h);layers=[h]
        for w,total,gain in zip(self.layers,self.sums,RESPONSE_GAINS):
            h=expit(gain*(np.asarray(h@w).ravel()/total-.5))
            if silenced:h=np.zeros_like(h)
            layers.append(h)
        canonical=h@self.decoder+self.bias
        logits=np.empty(9,dtype=np.float32);logits[permutation]=canonical
        legal=np.asarray(board)==0
        probabilities=softmax(np.where(legal,logits,-np.inf))
        chosen=int(np.argmax(probabilities))
        return chosen,layers,dict(board=list(board),player=turn(board),input=x.tolist(),permutation=permutation.tolist(),
            logits=logits.tolist(),probabilities=probabilities.tolist(),legal_cells=np.flatnonzero(legal).tolist(),chosen_cell=chosen)

    def __call__(self,board):return self.activity(board)[0]


def torch_model(circuit,seed=42):
    import torch
    from torch import nn
    torch.manual_seed(seed)
    class Actor(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder=nn.Linear(27,circuit.layers[0].shape[0]);self.decoder=nn.Linear(circuit.layers[2].shape[1],9)
            nn.init.normal_(self.encoder.weight,std=.3);nn.init.zeros_(self.encoder.bias)
            nn.init.normal_(self.decoder.weight,std=.02);nn.init.zeros_(self.decoder.bias)
            for i,w in enumerate(circuit.layers):
                self.register_buffer(f'base{i}',torch.from_numpy(w.toarray().astype(np.float32)))
                rows,cols=w.nonzero()
                self.register_buffer(f'rows{i}',torch.from_numpy(rows.astype(np.int64)))
                self.register_buffer(f'cols{i}',torch.from_numpy(cols.astype(np.int64)))
                self.register_parameter(f'gain{i}',nn.Parameter(torch.zeros(len(rows))))
        def weight(self,i):
            w=getattr(self,f'base{i}').clone();r,c=getattr(self,f'rows{i}'),getattr(self,f'cols{i}')
            w[r,c]*=torch.exp(1.5*torch.tanh(getattr(self,f'gain{i}')))
            return w
        def forward(self,x):
            h=torch.sigmoid(self.encoder(x))
            for i,gain in enumerate(RESPONSE_GAINS):
                w=self.weight(i);h=torch.sigmoid(gain*(h@w/w.sum(0).clamp_min(1e-8)-.5))
            return self.decoder(h)
        def save(self,path):
            array=lambda a:a.detach().cpu().numpy()
            np.savez_compressed(path,task='tictactoe',circuit_identity=circuit.identity,
                encoder=array(self.encoder.weight.T),encoder_bias=array(self.encoder.bias),decoder=array(self.decoder.weight.T),bias=array(self.decoder.bias),
                weight0=array(self.weight(0)),weight1=array(self.weight(1)),weight=array(self.weight(2)),
                **{f'gain{i}':array(getattr(self,f'gain{i}')) for i in range(3)})
        def restore(self,path):
            with np.load(path,allow_pickle=False) as s,torch.no_grad():
                if str(s['circuit_identity'])!=circuit.identity:raise ValueError('Checkpoint/circuit mismatch')
                for a,key,transpose in ((self.encoder.weight,'encoder',True),(self.encoder.bias,'encoder_bias',False),
                                        (self.decoder.weight,'decoder',True),(self.decoder.bias,'bias',False)):
                    a.copy_(torch.as_tensor(s[key].T if transpose else s[key],device=a.device))
                for i in range(3):getattr(self,f'gain{i}').copy_(torch.as_tensor(s[f'gain{i}'],device=self.encoder.weight.device))
    return Actor()
