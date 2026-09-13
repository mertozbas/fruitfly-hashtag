"""An isolated UI run; never overwrite the verified baseline."""
import argparse
import json
from odor_brain import MODEL, train, load_policy
from fly_sim import rollout, json_default

def event(**values):
    print("LAB_EVENT " + json.dumps(values), flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--steps",type=int,required=True)
    p.add_argument("--seed",type=int,required=True)
    args=p.parse_args()
    train(steps=args.steps,seed=args.seed)
    event(status="evaluating", evaluated=0, evaluation_total=6)
    policy=load_policy("trained")
    results=[]
    for i, goal in enumerate([(12,4),(12,-4),(10,5),(10,-5),(14,3),(14,-3)]):
        r=rollout(policy,seed=10+i,goal=goal,seconds=2.5)
        r["seed"]=10+i
        results.append(r)
        event(status="evaluating",evaluated=i+1,evaluation_total=6,success_count=sum(x["success"] for x in results))
    evaluation=dict(episodes=6,success_count=sum(x["success"] for x in results),falls=sum(x["fallen"] for x in results),
                    mean_final_distance_mm=sum(x["final_distance_mm"] for x in results)/6,results=results)
    (MODEL/"evaluation.json").write_text(json.dumps(evaluation,default=json_default,indent=2))

if __name__ == "__main__":
    main()
