# Virtual Reactor

An open reactor modeller. Take a reactor model, generate its physics library with OpenMC,
then run it live in the browser. Operate it from a control-room panel, or fly through the core and watch the power distribution change.
The first test case is a TRIGA Mark II research reactor. The live code is reactor-agnostic: each reactor is just a library file.

- **Physics:** point kinetics (six delayed groups) with fuel and coolant temperature feedback and xenon/iodine.
- **Spatial detail:** 3D power shapes and rod worths computed ahead of time in OpenMC, interpolated live.
- **Views:** operator (instruments only), explorer (noclip 3D with overlays), instructor (time control and fault injection).

Status: planning. See [PLAN.md](PLAN.md) for the design, [TODO.md](TODO.md) for the running task list,
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the parts fit together, [docs/plans/](docs/plans/) for each area,
and [docs/TOOLING.md](docs/TOOLING.md) for every repo and tool involved (versions, alternatives, upgrade candidates).

## Quick check

From this folder, with Python 3.11 or newer (no packages needed):

```bash
python -m unittest discover -s pipeline/tests -t .
```

License: MIT (see `LICENSE`).

Multi-agent log: `../messages/virtual-reactor.md`.
