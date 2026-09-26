# Connectome-derived task circuits for SO-101 and tic-tac-toe

Mert Özbaş · Hashtag World Company / Hashtag Robotics · 26 September 2026

**Research software and retrospective technical note; not peer reviewed.** This snapshot reports existing experiments. Preparing it did not run a new physical robot experiment.

## Abstract

We repurpose selected anatomical connectivity from MaleCNS for engineered tasks, while keeping sensory encoding, artificial neural responses, learned readouts and deterministic robot execution explicit. A 3,488-neuron subgraph learned tic-tac-toe strategy and was adapted to contact-based SO-101 manipulation in MuJoCo. The final strategy selected an optimal move in 4,520/4,520 reachable decision states; its training included the complete finite canonical board set. A separate motor evaluation completed nine single-destination placements and five sequential robot placements in one game. Earlier SO-101 simulation experiments achieved 94/100 held-out cube placements. Separately, a 4,387-neuron visual subgraph drove measured motion of a physical SO-101 base joint. One recorded segment contains 85 target updates and 160 encoder counts of motion, approximately 14.07°. These are distinct task models and evidence levels. Physical tic-tac-toe and autonomous physical grasping have not been demonstrated.

## Research questions and method

The experiments ask whether anatomical connectivity can serve as a trainable task substrate, whether its live computed activity can be traced to an action, and whether a bounded adapter can connect a derived circuit to real motors. They do not test whole-brain emulation, consciousness or a universal advantage of biological topology.

The anatomical source is [MaleCNS v1.0](https://male-cns.janelia.org/). The project uses selected directed paths, artificial sigmoid responses, task encoders and motor decoders. The models are not living brains or validated physiological simulations. Existing anatomical edge gains can change; new anatomical edges are not added. [MuJoCo](https://mujoco.readthedocs.io/en/stable/overview.html) provides simulated contact dynamics.

| Experiment | Anatomical core | Engineered interface |
| --- | --- | --- |
| SO-101 simulation / XOX | Touch → VNC relay → VNC premotor → Motor; 3,488 neurons, 81,104 edges | Task-specific input encoders, learned readouts, IK, bounded servos and task supervision |
| Physical visual experiment | Photoreceptor → optic relay → visual projection → descending; 4,387 neurons, 23,327 edges | Bilateral red-salience input, signed base command, deterministic execution limits |

XOX uses 27 board features, rotation/reflection canonicalization and nine output scores. Minimax provides offline supervision and evaluation. Live strategy inference performs a neural forward pass, masks occupied cells and selects the highest score; it does not invoke minimax, a move table or an LLM. The motor adaptation keeps the learned anatomical weights fixed and fits a separate readout using 4,000 synthetic geometries, with 1,000 separate validation geometries. A nine-phase supervisor, inverse kinematics, contact checks and retry limits remain engineered components. [Implementation and complete protocol](../tictactoe-local.md).

## Recorded results

### Tic-tac-toe strategy

The recorded strategy used seed 51 and 6,000 optimization steps. A first stage held out entire D4 symmetry orbits: 502 canonical training boards and 125 validation boards. The final stage trained on all 627 canonical boards. The first-stage validation set was used for model selection, so its result is not an independent final test.

| Measurement | Recorded result | Interpretation |
| --- | ---: | --- |
| First-stage validation optimal move | 96.8% | Held-out symmetry groups at that stage |
| Final exhaustive decision-state coverage | 4,520 / 4,520 | Finite learned coverage; not unseen-board generalization |
| Random opponent, both roles, 400 games | 352 wins / 48 draws / 0 losses | Fixed evaluation seed 731 |
| Minimax opponent, both roles, 400 games | 400 draws / 0 losses | Fixed evaluation seed 731 |
| All possible opponent replies from empty board | Worst case: draw as X and O | Exhaustive finite-game evaluation |
| All four activity layers silenced, random opponent | 96 wins / 37 draws / 267 losses | Readout biases and legal-move mask remain |
| Untrained network, random opponent | 185 wins / 18 draws / 197 losses | Same opponent seed and episode count |

### Contact-based XOX motor simulation

| Measurement | Recorded result |
| --- | ---: |
| First X cube placed in each of nine destinations | 9 / 9, first attempt |
| One complete sequential self-play game | 5 / 5 robot X placements, first attempt; nine-move draw |
| Silenced motor activity, center destination | Failed; invalid command rejected at workspace limit |

The robot moves 30 mm cubes marked X through contact physics. The opponent's O pieces are placed virtually. The original thin printed X/O tokens did not achieve reliable lifting and are not covered by the success claim. Fixed scene tests do not estimate arbitrary game-sequence or real-world success. Sensor input is simulated RGB-D with a fixed palette; a physical UVC camera supplies RGB only.

### SO-101 cube placement simulation

The state-based model was selected before evaluating seeds 8000–8099. Success requires the cube fully inside the receptacle, released and stationary, with the end effector more than 65 mm away for 0.5 s and no prohibited contact or physics warning.

| Condition | Successful / total | Unsafe outcomes |
| --- | ---: | ---: |
| Trained anatomical model, state input | 94 / 100 | 0 |
| Untrained model | 0 / 100 | 0 |
| Neural activity silenced | 0 / 100 | 0 |
| Anatomical core fixed during training | 37 / 100 | 0 |
| MLP reference | 62 / 100 | 0 |
| Same trained model, synthetic RGB-D input | 93 / 100 | 0 |
| Later wrist-camera controller, normal scenes | 38 / 40 | 0 |
| Wrist controller, forced release after lift | 23 / 24 | 0 |
| Wrist controller, forced release during transport | 3 / 8 | 0 |
| Wrist controller, pre-grasp lateral push | 7 / 8 | 1 |
| Wrist controller, neural activity silenced | 0 / 8 | 0 |

The MLP has different parameter counts; this single dataset comparison does not establish general superiority of anatomical connectivity. The wrist controller passed its basic 40/24 acceptance suite and failed extended robustness. Its matched previous **trained** controller obtained 35/40 normal and 20/24 release-after-lift successes. Changes include both neural readouts and task supervision, so improvements cannot be attributed to anatomy alone. [Training, assumptions and failure modes](../so101-local.md).

### Physical SO-101 motion, 16 September 2026

Real hardware was tested and measured base motion was obtained from the connectome-derived visual model through a bounded motor adapter. The table preserves all four analyzed segments, including the segment with no measured displacement.

| Segment | Logged samples | Target updates | Base displacement | Logged span |
| --- | ---: | ---: | ---: | ---: |
| R1 | 157 | 85 | 160 counts / 14.07° | 16.160 s |
| R2 | 6 | 4 | 0 counts / 0° | 0.463 s |
| R3 | 134 | 85 | 165 counts / 14.51° | 13.733 s |
| R4 | 33 | 31 | 52 counts / 4.57° | 3.275 s |

R3 and R4 are segments of one session, separated by a logging gap; these are not four independent randomized trials. Every analyzed neural drive value is −1. The data establish a functioning model-output → bounded-command → encoder-motion path, not physical bidirectional visual target tracking or an advantage over a simpler controller. Counts convert to degrees using 360/4095; this is an encoder displacement rather than external pose metrology. Logged span is not necessarily active-motion duration.

Separate deterministic tests moved body joints and opened an empty gripper, but gripper/body attempts ended on tracking or settling criteria. A two-tag camera/model candidate had 1.93 px coordinate RMS over eight poses and 1.27–2.17 px on two additional poses in the same setup. This is image reprojection error, not millimetric contact accuracy. The candidate retained `physical_alignment_verified=false` and `execution_allowed=false`. Intermittent elevated servo temperature readings remained unresolved. Autonomous cube grasping was not achieved.

## Evidence and reproducibility

This directory contains a compact public export, not the complete local workspace or training dataset:

| File | Content |
| --- | --- |
| [results.json](results.json) | Source-derived aggregates, circuit sizes, model hashes, training history and limitations |
| [so101-episodes.csv](so101-episodes.csv) | Per-seed outcomes, including failures, for 13 simulation conditions |
| [tictactoe-motor.csv](tictactoe-motor.csv) | Nine destinations, five sequential placements and the silenced control |
| [physical-runs.csv](physical-runs.csv) | Four anonymized physical segment summaries |
| [physical-motion.csv](physical-motion.csv) | All 330 logged samples: relative time, base/goal displacement and drive |
| [provenance.json](provenance.json) | Source paths, SHA256 identities, redactions and hashes of the public data files |
| [validation-2026-09-26.json](validation-2026-09-26.json) | Fresh software checks, environment versions and a repeated strategy evaluation |

The original 51-entry physical evidence manifest matched its local files during export. Original raw sessions, device IDs, absolute paths, calibration profiles, full activity vectors and private archives are not bundled. Hashes preserve identity; they do not independently certify experimental correctness. The public CSVs support recalculation of outcome counts and physical displacement. The strategy's exhaustive optimality result is an aggregate; the public snapshot alone does not rerun its policy.

During publication preparation on 26 September, **247 distinct software tests passed**: 178 virtual hardware/safety contracts, 12 hardware-manager contracts and 57 scientific tests including local MuJoCo assets. The separate default scientific run is not double-counted. The local XOX checkpoint was evaluated again, reproducing 4,520/4,520 optimal decisions, 352/48/0 against random play, 0/400/0 against minimax and 96/37/267 under neural silencing. The [validation record](validation-2026-09-26.json) preserves commands, versions, durations and warnings. These fresh checks did not retrain the model, rerun the full robot placement benchmark or connect to physical hardware. The motor success tables and physical trajectories remain historical evidence.

From the repository root, using only Python's standard library:

```bash
python3 docs/research/verify_evidence.py
```

This checks public file hashes, recomputes simulation counts and physical displacement, and confirms that all physical drive samples are −1. It does not train a model, simulate new trials or operate a robot. Maintainers with the original source records can regenerate the data into a **new** directory:

```bash
python3 docs/research/export_evidence.py \
  --source /path/to/original-workspace --output /path/to/new-evidence-export \
  --validation-record docs/research/validation-2026-09-26.json
```

Training and simulation require the scientific environment, external assets and separate model data described in the [SO-101](../so101-local.md) and [XOX](../tictactoe-local.md) guides. This publication does not claim a complete one-command reproduction from a fresh clone.

## Limitations and next work

The physical evidence is a descriptive single-robot case study. It has no matched physical non-anatomical controller, no independent torque/temperature/TCP metrology, no successful autonomous grasp and no physical XOX evaluation. Simulation geometry, fixed colors, known targets, synthetic depth and engineered control stages limit transfer claims. Model-selection decisions and a finite game-state space further limit generalization claims.

The next robotics experiment is controlled leader teleoperation, verified motor-driven grasps and synchronized recordings before learning a physical readout. Earlier hand-guided movement did not establish successful autonomous grasping.

**Coming soon — an LLM-like interface to a connectome-derived model.** A future research direction will investigate prompting, sequential interaction and bounded task interfaces around these neural circuits. No language-model capability, language benchmark or replacement for an LLM is claimed by the present results.
