"""One robot-day on a harsh floor: what three ways of metering bill, against the truth."""
import json, sys
from meter import sim, ledger

sys.stdout.reconfigure(encoding="utf-8")
cfg = json.load(open("heldout/config.json"))
days = sim.fleet(cfg["seed"], cfg["sites"], cfg["robots"], cfg["days"], cfg["cfg"])


def bill(d, tl):
    win = d["shift"] if d["contract"] == "shift" else (0.0, sim.DAY)
    return ledger.invoice(ledger.minutes(tl, win), d["contract"], d["shift"])


def interest(d):  # a day with a reboot, duplicates and a big baseline error
    boots = len({e["boot"] for e in d["events"]})
    t = bill(d, d["truth"])["amount"]
    return (boots > 1) * abs(bill(d, ledger.timeline(d["events"], "recv")[0])["amount"] - t)


d = max((x for x in days if x["contract"] == "usage"), key=interest)
fmt = lambda m: f"{int(m // 60):02d}:{int(m % 60):02d}"
dups = len(d["events"]) - len({(e["boot"], e["seq"], e["kind"], round(e["dev_t"], 4)) for e in d["events"]})
print(f"Robot {d['robot']} ({d['site']}, {d['contract']} contract, $10/h), day {d['day']}")
print(f"  telemetry: {len(d['events'])} events received, {dups} duplicates, {len({e['boot'] for e in d['events']})} boots")
fixed, how = ledger.correct(d["events"])
for b, h in sorted(how.items()):
    first = min((e for e in fixed if e["boot"] == b), key=lambda e: e["t"])
    print(f"  boot {b}: first event stamped {fmt(first['dev_t'] % 1440)} by the device -> {fmt(first['t'])} after the clock fit ({h})")
late = [e for e in fixed if e["kind"] == "HB" and e["recv_t"] - e["t"] > 2]
print(f"  dead zones: {len(late)} heartbeats arrived > 2 min late (buffered); the rest were lost when the buffer filled")
t = bill(d, d["truth"])
print(f"\n  {'':34s} {'billed':>9s} {'teleop min':>11s} {'unknown min':>12s}")
print(f"  {'truth (simulator)':34s} ${t['amount']:8.2f} {t['teleop_min']:11.0f} {'':>12s}")
for m, name in (("device", "device clock, carry last state"), ("recv", "dedupe + server receive time"), ("ledger", "ledger (this)")):
    b = bill(d, ledger.timeline(d["events"], m)[0])
    print(f"  {name:34s} ${b['amount']:8.2f} {b['teleop_min']:11.0f} {b['unknown_min']:12.0f}   ({b['amount'] - t['amount']:+.2f})")
tl, _ = ledger.timeline(d["events"])
gaps = [(s, e) for s, e, st in tl if st == "UNKNOWN" and e - s > 5]
if gaps:
    print("\n  UNKNOWN (no telemetry survived, not billed): " + ", ".join(f"{fmt(s)}-{fmt(e)}" for s, e in gaps[:4]))
