"""Telemetry -> timeline -> invoice line + margin.

timeline(events, mode):
  "ledger"  dedupe (boot, seq); per-boot clock fit from SYNC pairs (Theil-Sen), or a bound from
            receive times when a boot never synced; heartbeat gaps > 3 min -> UNKNOWN
  "device"  baseline: device clock as-is, no dedupe, last state carried across gaps
  "recv"    baseline: dedupe, but stamp events with server receive time, carry across gaps
"""
from statistics import median

GAP = 3.0            # minutes without any event while ON -> UNKNOWN
DAY = 1440.0
CONTRACT = dict(rate=10.0, charge_allowance=0.12, sla=0.95, sla_credit=0.10,
                teleop_cost_min=0.60, energy_per_h=0.15)


def _fit(pairs):
    """server = device + a + b*device, Theil-Sen."""
    if len(pairs) == 1:
        d, s = pairs[0]
        return s - d, 0.0
    slopes = [((s2 - d2) - (s1 - d1)) / (d2 - d1) for i, (d1, s1) in enumerate(pairs)
              for d2, s2 in pairs[i + 1:] if abs(d2 - d1) > 1]
    b = median(slopes) if slopes else 0.0
    a = median(s - d - b * d for d, s in pairs)
    return a, b


def correct(events):
    seen, evs = set(), []
    for e in events:
        k = (e["boot"], e["seq"], e["kind"]) if e["seq"] is not None else (e["boot"], "SYNC", round(e["dev_t"], 4))
        if k not in seen:
            seen.add(k)
            evs.append(e)
    boots = {}
    for e in evs:
        boots.setdefault(e["boot"], []).append(e)
    fits, how = {}, {}
    for b, es in boots.items():
        pairs = sorted((e["dev_t"], e["server_t"]) for e in es if e["kind"] == "SYNC")
        if pairs:
            fits[b], how[b] = _fit(pairs), f"{len(pairs)} sync pairs"
        else:  # never synced: an event can't arrive before it happened -> offset <= recv - dev
            fits[b], how[b] = (min(e["recv_t"] - e["dev_t"] for e in es) - 0.03, 0.0), "bounded by receive times (no sync)"
    out = []
    for e in evs:
        if e["kind"] == "SYNC":
            continue
        a, s = fits[e["boot"]]
        out.append(dict(e, t=e["dev_t"] + a + s * e["dev_t"]))
    return out, how


def timeline(events, mode="ledger"):
    if mode == "ledger":
        evs, how = correct(events)
    elif mode == "device":
        evs, how = [dict(e, t=e["dev_t"]) for e in events if e["kind"] != "SYNC"], {}
    else:
        seen, evs = set(), []
        for e in events:
            if e["kind"] == "SYNC" or (e["boot"], e["seq"]) in seen:
                continue
            seen.add((e["boot"], e["seq"]))
            evs.append(dict(e, t=e["recv_t"]))
        how = {}
    evs.sort(key=lambda e: (e["t"], e["boot"], e["seq"] or 0))
    tl = []
    for i, e in enumerate(evs):
        nxt = evs[i + 1]["t"] if i + 1 < len(evs) else DAY
        st = e["state"]
        if mode == "ledger" and st != "OFF" and nxt - e["t"] > GAP:
            tl.append((e["t"], e["t"] + 1.0, st))          # a heartbeat vouches for ~1 minute
            tl.append((e["t"] + 1.0, nxt, "UNKNOWN"))
        else:
            tl.append((e["t"], nxt, st))
    if evs and evs[0]["t"] > 0:
        tl.insert(0, (0.0, evs[0]["t"], "UNKNOWN" if mode == "ledger" else evs[0]["state"]))
    return tl, how


def minutes(tl, window=(0.0, DAY)):
    a, b = window
    m = {}
    for s, e, st in tl:
        x = max(0.0, min(e, b) - max(s, a))
        if x:
            m[st] = m.get(st, 0.0) + x
    return m


def invoice(m, contract, shift):
    c = CONTRACT
    W = shift[1] - shift[0]
    if contract == "usage":
        hours = (m.get("WORKING", 0) + m.get("TELEOP", 0)) / 60
        credit = 0.0
        avail = None
    else:
        excess = max(0.0, m.get("CHARGING", 0) - c["charge_allowance"] * W)
        down = m.get("FAULT", 0) + m.get("UNKNOWN", 0) + excess
        hours = (W - down) / 60
        avail = (W - down) / W
        credit = c["sla_credit"] if avail < c["sla"] else 0.0
    amount = hours * c["rate"] * (1 - credit)
    on = sum(v for k, v in m.items() if k not in ("OFF", "UNKNOWN"))
    cost = m.get("TELEOP", 0) * c["teleop_cost_min"] + on / 60 * c["energy_per_h"]
    return dict(hours=hours, amount=amount, availability=avail, sla_credit=credit, teleop_min=m.get("TELEOP", 0),
                unknown_min=m.get("UNKNOWN", 0), cost=cost, margin=amount - cost)
