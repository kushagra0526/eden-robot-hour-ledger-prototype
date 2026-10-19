"""Bill every robot-day three ways and compare with the bill from the true timeline.
python evaluate.py [dev|heldout] [out.json]"""
import json, sys
from collections import defaultdict
from meter import sim, ledger

MODES = {"device": "device clock, carry last state", "recv": "dedupe + server receive time", "ledger": "ledger (this)"}


def run(which):
    if which == "heldout":
        cfg = json.load(open("heldout/config.json"))
        days = sim.fleet(cfg["seed"], cfg["sites"], cfg["robots"], cfg["days"], cfg["cfg"])
    else:
        days = sim.fleet(11, 4, 5, 7)
    res = {m: dict(abs_err=0.0, net_err=0.0, over_days=0, teleop_err=0.0, unknown_min=0.0) for m in MODES}
    truth_total, site_truth, site_est = 0.0, defaultdict(float), {m: defaultdict(float) for m in MODES}
    worst = []
    for d in days:
        win = d["shift"] if d["contract"] == "shift" else (0.0, sim.DAY)
        tb = ledger.invoice(ledger.minutes(d["truth"], win), d["contract"], d["shift"])
        truth_total += tb["amount"]
        site_truth[d["site"]] += tb["margin"]
        for m in MODES:
            tl, _ = ledger.timeline(d["events"], m)
            eb = ledger.invoice(ledger.minutes(tl, win), d["contract"], d["shift"])
            err = eb["amount"] - tb["amount"]
            r = res[m]
            r["abs_err"] += abs(err)
            r["net_err"] += err
            r["over_days"] += err > 0.01 * tb["amount"] + 0.5
            r["teleop_err"] += abs(eb["teleop_min"] - tb["teleop_min"])
            r["unknown_min"] += eb["unknown_min"]
            site_est[m][d["site"]] += eb["margin"]
            if m == "ledger" and err > 0.01 * tb["amount"] + 0.5:
                worst.append((d["robot"], d["day"], round(err, 2)))
    for m in MODES:
        res[m]["site_margin_err"] = {s: round(site_est[m][s] - site_truth[s], 2) for s in site_truth}
    return dict(set=which, robot_days=len(days), truth_billed=round(truth_total, 2), results=res,
                site_truth_margin={s: round(v, 2) for s, v in site_truth.items()}, ledger_overbilled=worst[:20])


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "dev"
    r = run(which)
    print(f"{which}: {r['robot_days']} robot-days, ${r['truth_billed']:,.2f} true billings")
    for m, x in r["results"].items():
        print(f"  {MODES[m]:32s} |error| ${x['abs_err']:8.2f}  net ${x['net_err']:+9.2f}  over-billed days {x['over_days']:3d}"
              f"  teleop-min error {x['teleop_err']:7.0f}  unknown min {x['unknown_min']:6.0f}")
    print("  site margin error ($):", {m: r["results"][m]["site_margin_err"] for m in MODES})
    if len(sys.argv) > 2:
        json.dump(r, open(sys.argv[2], "w"), indent=1)
