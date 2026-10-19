"""A rented robot's true day, and the telemetry that reaches the server.

Truth: states over one day (minutes 0..1440, server time).
Telemetry: STATE events and 1-min heartbeats stamped with the DEVICE clock and a
per-boot sequence number, SYNC pairs (device time, server time) every 30 min while
online. Things that go wrong on a warehouse floor:
  clock offset + drift; clock reset on reboot (RTC falls back)
  Wi-Fi dead zones: events buffered and uploaded late; buffer overflow drops the oldest
  retries upload some events twice
"""
import random

DAY = 1440.0
STATES = ("WORKING", "TELEOP", "WAITING", "FAULT", "CHARGING", "OFF")
DEV = dict(offline_rate=0.25, offline_max=25, buffer=40, dup=0.03, reboot_on_fault=0.5, drift=2e-4,
           reset_offsets=(-420, -60, 0, 300), teleop_p=0.35, fault_p=0.03)


def truth_day(r, shift, cfg):
    """[(start, end, state)] covering [0, DAY)."""
    a, b = shift
    tl, t = [], 0.0
    if a > 0:
        tl.append((0.0, a, "OFF"))
        t = a
    since_charge = r.uniform(0, 150)
    while t < b:
        w = min(r.expovariate(1 / 25), b - t)
        tl.append((t, t + w, "WORKING"))
        t += w
        since_charge += w
        if t >= b:
            break
        if since_charge > r.uniform(170, 240):
            d, s = r.uniform(30, 45), "CHARGING"
            since_charge = 0
        else:
            x = r.random()
            if x < cfg["fault_p"]:
                d, s = r.uniform(5, 60), "FAULT"
            elif x < cfg["fault_p"] + cfg["teleop_p"]:
                d, s = r.uniform(1, 6), "TELEOP"
            elif x < cfg["fault_p"] + cfg["teleop_p"] + 0.15:
                d, s = r.uniform(2, 20), "WAITING"
            else:
                continue
        d = min(d, b - t)
        tl.append((t, t + d, s))
        t += d
    if t < DAY:
        tl.append((t, DAY, "OFF"))
    return tl


def telemetry(r, tl, cfg):
    """Events as received: dict(boot, seq, dev_t, kind, state|server_t, recv_t)."""
    # connectivity: offline spells [s, e)
    off, t = [], 0.0
    while True:
        t += r.expovariate(cfg["offline_rate"] / 60)
        if t >= DAY:
            break
        e = t + r.uniform(2, cfg["offline_max"])
        off.append((t, min(e, DAY)))
        t = e

    def offline_until(t):
        for s, e in off:
            if s <= t < e:
                return e
        return None

    boot, seq = 0, 0
    clock = dict(off=r.gauss(0, 3), drift=r.uniform(-cfg["drift"], cfg["drift"]))
    dev = lambda t: t + clock["off"] + clock["drift"] * t
    raw = []  # (true_t, event)

    def emit(t, **ev):
        nonlocal seq
        seq += 1
        raw.append((t, dict(boot=boot, seq=seq, dev_t=dev(t), **ev)))

    for s, e, st in tl:
        if st == "FAULT" and r.random() < cfg["reboot_on_fault"]:
            emit(s, kind="STATE", state="FAULT")
            boot, seq = boot + 1, 0                       # reboot: RTC falls back, sequence restarts
            clock["off"] = r.choice(cfg["reset_offsets"]) + r.gauss(0, 1)
            emit(s + 1.5, kind="STATE", state="FAULT")
        else:
            emit(s, kind="STATE", state=st)
        if st != "OFF":
            h = s + 1
            while h < e:
                emit(h, kind="HB", state=st)
                h += 1
    k = 0
    while k * 30 < DAY:
        t = k * 30 + 0.2
        k += 1
        if offline_until(t) is None and any(s <= t < e and st != "OFF" for s, e, st in tl):
            b = boot_at(raw, t)
            raw.append((t, dict(boot=b[0], seq=None, dev_t=b[1](t), kind="SYNC", server_t=t + r.uniform(0.005, 0.03))))
    # upload: online -> now; offline -> at reconnect, ring buffer keeps the newest `buffer` events
    out, pending = [], []
    raw.sort(key=lambda x: x[0])
    for t, ev in raw:
        until = offline_until(t)
        if until is None:
            out.append(dict(ev, recv_t=t + r.uniform(0.005, 0.05)))
        else:
            pending.append((until, ev))
    by_spell = {}
    for until, ev in pending:
        by_spell.setdefault(until, []).append(ev)
    for until, evs in by_spell.items():
        for ev in evs[-cfg["buffer"]:]:
            out.append(dict(ev, recv_t=until + r.uniform(0.01, 0.5)))
    for ev in list(out):
        if r.random() < cfg["dup"]:
            out.append(dict(ev, recv_t=ev["recv_t"] + r.uniform(0.1, 5)))
    r.shuffle(out)
    return out


def boot_at(raw, t):
    """(boot id, device clock fn) in force at true time t, read back from emitted events."""
    last = None
    for tt, ev in raw:
        if tt <= t and ev["seq"] is not None:
            last = (tt, ev)
    if last is None:
        return 0, (lambda x: x)
    tt, ev = last
    o = ev["dev_t"] - tt
    return ev["boot"], (lambda x, o=o: x + o)


def fleet(seed, sites=4, robots=5, days=7, cfg=None):
    cfg = {**DEV, **(cfg or {})}
    r = random.Random(seed)
    out = []
    for s in range(sites):
        contract = r.choice(["usage", "shift"])
        shift = r.choice([(0.0, DAY), (360.0, 1320.0), (420.0, 1140.0)])
        site_cfg = dict(cfg, teleop_p=cfg["teleop_p"] * r.uniform(0.5, 1.6))
        for k in range(robots):
            for d in range(days):
                tl = truth_day(r, shift, site_cfg)
                out.append(dict(site=f"site{s + 1}", robot=f"E1-{s + 1}{k + 1:02d}", day=d, contract=contract,
                                shift=shift, truth=tl, events=telemetry(r, tl, site_cfg)))
    return out
