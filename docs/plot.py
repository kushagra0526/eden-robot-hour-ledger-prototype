import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

r = json.load(open("out/heldout_first_run.json"))
names = {"device": "device clock,\ncarry last state", "recv": "dedupe + server\nreceive time", "ledger": "ledger (this)"}
res = r["results"]
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
col = ["#bbb", "#888", "#2a7"]
ax[0].bar(list(names.values()), [res[m]["over_days"] for m in names], color=col)
ax[0].set_title(f"robot-days over-billed by >1% (of {r['robot_days']})")
ax[1].bar(list(names.values()), [res[m]["net_err"] for m in names], color=col)
ax[1].axhline(0, color="k", lw=0.8)
ax[1].set_title(f"net billing error, $ (true billings ${r['truth_billed']:,.0f})")
fig.suptitle("Held-out harsh warehouse floor, first run (ledger under-bills only where telemetry was lost)")
fig.tight_layout()
fig.savefig("docs/result.png", dpi=110)
