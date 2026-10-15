"""Load a validated reactor library into plain Python objects for the engine.

A library is loaded only if it passes pipeline.library.validate. Tests may override
fields afterwards; `Library.mark_modified()` then changes the digest so checkpoints
and sessions can't be mistaken for ones made with the unmodified library.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import struct
from pathlib import Path

from pipeline.library.validate import validate_library


class LibraryError(Exception):
    def __init__(self, issues):
        self.issues = issues
        super().__init__("; ".join(f"{i.code} {i.path}" for i in issues[:5]))


class Table:
    """Piecewise-linear table with declared out-of-range behaviour.

    value(x) returns (y, flag) where flag is None inside the table, else "below"/"above".
    "clamp-and-flag" holds the end value; "extrapolate-and-flag" extends the end segment;
    "reject" still clamps here, and the engine turns the flag into a rejected state.
    """

    def __init__(self, xs, ys, out_of_range="clamp-and-flag"):
        if len(xs) != len(ys) or len(xs) < 2:
            raise ValueError("table needs two equal-length columns of at least 2 points")
        self.xs, self.ys, self.out_of_range = list(xs), list(ys), out_of_range

    def value(self, x):
        xs, ys = self.xs, self.ys
        if x < xs[0]:
            if self.out_of_range == "extrapolate-and-flag":
                return ys[0] + (x - xs[0]) * (ys[1] - ys[0]) / (xs[1] - xs[0]), "below"
            return ys[0], "below"
        if x > xs[-1]:
            if self.out_of_range == "extrapolate-and-flag":
                return ys[-1] + (x - xs[-1]) * (ys[-1] - ys[-2]) / (xs[-1] - xs[-2]), "above"
            return ys[-1], "above"
        i = min(bisect.bisect_right(xs, x) - 1, len(xs) - 2)
        t = (x - xs[i]) / (xs[i + 1] - xs[i])
        return ys[i] + t * (ys[i + 1] - ys[i]), None

    def __call__(self, x):
        return self.value(x)[0]

    def integral(self, a, b):
        """Exact integral of the piecewise-linear table from a to b (clamped ends held constant)."""
        if b < a:
            return -self.integral(b, a)
        pts = [a] + [x for x in self.xs if a < x < b] + [b]
        total = 0.0             # explicit loop, not sum(): see numerics.py
        for p, q in zip(pts, pts[1:]):
            total += 0.5 * (self(p) + self(q)) * (q - p)
        return total


class Rod:
    def __init__(self, d):
        self.id = d["id"]
        self.name = d["name"]
        self.travel_cm = d["travelCm"]
        self.speed = d["speed"]
        self.pulse_capable = d["pulseCapable"]
        self.fire_time = d.get("fireTime")
        w = d["worth"]
        self.worth = Table(w["x"], w["rho"], w["outOfRange"])
        self.scram_t = list(d["scram"]["t"])
        self.scram_x = list(d["scram"]["x"])
        self._scram_table = Table(self.scram_t, self.scram_x)

    def scram_position(self, tau):
        """Position tau seconds along the scram profile."""
        return self._scram_table(tau)

    def scram_tau(self, x):
        """Time along the scram profile where the profile first reaches position x (profile is non-increasing)."""
        ts, xs = self.scram_t, self.scram_x
        if x >= xs[0]:
            return 0.0
        for i in range(len(xs) - 1):
            if xs[i] >= x >= xs[i + 1]:
                if xs[i] == xs[i + 1]:
                    return ts[i]
                return ts[i] + (xs[i] - x) / (xs[i] - xs[i + 1]) * (ts[i + 1] - ts[i])
        return ts[-1]


BORON_CAPABILITY = "point-kinetics/boron-v1"
ROD_INTERACTION_CAPABILITY = "point-kinetics/rod-interaction-v1"
ROD_SHADOW_CAPABILITY = "point-kinetics/rod-interaction-v2"


def _digest(folder: Path, manifest: dict) -> str:
    h = hashlib.sha256((folder / "manifest.json").read_bytes())
    for name in sorted(manifest["arrays"]):
        h.update(manifest["arrays"][name]["sha256"].encode())
    return h.hexdigest()


class Library:
    def __init__(self, folder):
        folder = Path(folder)
        issues = validate_library(folder)
        if issues:
            raise LibraryError(issues)
        m = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        self.manifest = m
        self.id = m["id"]
        self.status = m["status"]
        self.digest = _digest(folder, m)

        ref = m["reference"]
        self.ref_rods = dict(ref["rods"])
        self.ref_tfuel = ref["Tfuel"]["value"]
        self.ref_tcool = ref["Tcoolant"]["value"]
        self.ref_xenon = ref["xenon"]["value"]
        self.ref_rho = ref["rho"]["value"]
        self.calibration = ref["calibration"]["deltaRho"] if ref["calibration"] else 0.0

        k = m["kinetics"]
        self.beta = list(k["beta"]["values"])
        self.lam = list(k["lambda"]["values"])
        self.beta_total = 0.0
        for b in self.beta:     # explicit loop, not sum(): see numerics.py
            self.beta_total += b
        self.gen_time = k["genTime"]["value"]
        self.ext_source = k["extSource"]["value"]

        r = m["reactivity"]
        self.rods = [Rod(d) for d in r["rods"]]
        self.rod_by_id = {rod.id: rod for rod in self.rods}
        self.fuel_temp = Table(r["fuelTemp"]["T"], r["fuelTemp"]["rho"], r["fuelTemp"]["outOfRange"])
        self.cool_temp = Table(r["coolantTemp"]["T"], r["coolantTemp"]["rho"], r["coolantTemp"]["outOfRange"])
        self.xenon = Table(r["xenon"]["N"], r["xenon"]["rho"], r["xenon"]["outOfRange"])
        self.has_rod_interaction = ROD_INTERACTION_CAPABILITY in m["capabilities"]
        self.rod_interaction = (Table(r["rodInteraction"]["S"], r["rodInteraction"]["rho"], r["rodInteraction"]["outOfRange"])
                                if self.has_rod_interaction else None)     # a correction added to the sum of the single-rod reactivities, a function of that sum
        self.has_rod_shadow = ROD_SHADOW_CAPABILITY in m["capabilities"]
        self.rod_shadow = (Table(r["rodShadowing"]["R"], r["rodShadowing"]["g"], r["rodShadowing"]["outOfRange"])
                           if self.has_rod_shadow else None)     # g(R): the fractional change of a rod's worth when the other rods' summed reactivity is R
        self.has_boron = BORON_CAPABILITY in m["capabilities"]
        self.boron = None
        self.ref_boron = None
        self.boron_range = None
        self.boron_max_rate = None
        if self.has_boron:
            self.install_boron(ref["boron"]["value"], m["plant"]["boron"]["range"], m["plant"]["boron"]["maxRatePpmPerS"],
                               r["boron"]["C"], r["boron"]["rho"], r["boron"]["outOfRange"])

        t = m["thermal"]
        self.fuel_mass = t["fuel"]["mass"]["value"]
        self.fuel_cp = Table(t["fuel"]["cp"]["T"], t["fuel"]["cp"]["c"], t["fuel"]["cp"]["outOfRange"])
        self.cool_mass = t["coolant"]["mass"]["value"]
        self.cool_cp = t["coolant"]["cp"]["value"]
        self.hA = t["hA"]["value"]
        self.hA_exponent = t["hA"].get("exponent", 0.0)        # hA(dT) = hA * |dT / dTRef|^exponent, 0 is the constant law
        self.hA_dt_ref = t["hA"].get("dTRef", 100.0)
        self.UA = t["heatExchanger"]["UA"]["value"]
        self.sink_temp = t["heatExchanger"]["sinkTemp"]["value"]
        self.hx_pump = t["heatExchanger"]["pump"]
        self.fuel_fraction = t["deposition"]["fuelFraction"]["value"]

        p = m["poisons"]
        self.flux_per_watt = p["fluxPerWatt"]["value"]
        self.sigma_f = p["sigmaF"]["value"]
        self.gamma_i = p["gammaI"]["value"]
        self.gamma_x = p["gammaXe"]["value"]
        self.lambda_i = p["lambdaI"]["value"]
        self.lambda_x = p["lambdaXe"]["value"]
        self.sigma_x = p["sigmaXe"]["value"]

        pl = m["plant"]
        self.modes = list(pl["modes"])
        self.initial_mode = pl["initialMode"]
        self.pumps = [x["id"] for x in pl["pumps"]]
        self.instruments = [dict(i) for i in pl["instruments"]]
        self.trips = [dict(t) for t in pl["trips"]]
        self.interlocks = [dict(i) for i in pl["interlocks"]]

        self.domain = m["domain"]
        self.shapes = m["shapes"]
        self.arrays = {name: self._load_array(folder, d) for name, d in m["arrays"].items()}

    @staticmethod
    def _load_array(folder, d):
        data = (folder / d["file"]).read_bytes()
        n = int(d["byteLength"]) // 4        # integral floats (0.0) are valid JSON integers
        return list(struct.unpack_from(f"<{n}f", data, int(d["offset"])))

    def install_boron(self, ref: float, rng, max_rate: float, axis, rho, out_of_range: str = "clamp-and-flag") -> None:
        """Set the soluble-boron fields (from the manifest at load, or by a test override); `ref` is the reference concentration, ppm."""
        self.has_boron = True
        self.ref_boron = float(ref)
        self.boron_range = (float(rng[0]), float(rng[1]))
        self.boron_max_rate = float(max_rate)
        self.boron = Table(axis, rho, out_of_range)

    def mark_modified(self, note: str) -> None:
        """Call after changing fields in a test; the digest then can't match an unmodified library."""
        self.digest = hashlib.sha256((self.digest + "|modified:" + note).encode()).hexdigest()
