import os, random, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meter import sim, ledger


def ev(boot, seq, dev_t, state, kind="STATE", recv=None):
    return dict(boot=boot, seq=seq, dev_t=dev_t, kind=kind, state=state, recv_t=recv if recv is not None else dev_t)


class T(unittest.TestCase):
    def test_duplicates_removed(self):
        es = [ev(0, 1, 0, "WORKING"), ev(0, 1, 0, "WORKING"), ev(0, 2, 1, "WORKING", "HB"), ev(0, 3, 2, "OFF")]
        out, _ = ledger.correct(es)
        self.assertEqual(len(out), 3)

    def test_clock_fit_recovers_offset_and_drift(self):
        pairs = [(d, d + 120 + 1e-3 * d) for d in range(0, 1400, 30)]
        a, b = ledger._fit(pairs)
        self.assertAlmostEqual(a, 120, places=6)
        self.assertAlmostEqual(b, 1e-3, places=9)

    def test_reboot_clock_reset_corrected(self):
        # boot 1's clock reads 420 min behind; its sync pair puts events back in place
        es = [ev(0, 1, 100, "WORKING"), dict(boot=0, seq=None, dev_t=100.2, kind="SYNC", server_t=100.21, recv_t=100.3),
              ev(1, 1, 130 - 420, "FAULT"), dict(boot=1, seq=None, dev_t=131 - 420, kind="SYNC", server_t=131.01, recv_t=131.1)]
        out, how = ledger.correct(es)
        self.assertAlmostEqual(sorted(e["t"] for e in out)[1], 130, delta=0.05)

    def test_gap_becomes_unknown(self):
        es = [ev(0, 1, 100, "WORKING"), ev(0, 2, 101, "WORKING", "HB"), ev(0, 3, 140, "WORKING", "HB"), ev(0, 4, 141, "OFF")]
        es += [dict(boot=0, seq=None, dev_t=100.5, kind="SYNC", server_t=100.5, recv_t=100.6)]
        tl, _ = ledger.timeline(es)
        m = ledger.minutes(tl, (100, 141))
        self.assertAlmostEqual(m["UNKNOWN"], 38, delta=0.01)
        tl, _ = ledger.timeline(es, "device")
        self.assertNotIn("UNKNOWN", ledger.minutes(tl, (100, 141)))

    def test_shift_contract_sla_credit(self):
        m = {"WORKING": 800, "FAULT": 100, "CHARGING": 60}
        inv = ledger.invoice(m, "shift", (360.0, 1320.0))
        self.assertAlmostEqual(inv["availability"], 860 / 960)
        self.assertEqual(inv["sla_credit"], 0.10)
        self.assertAlmostEqual(inv["amount"], 860 / 60 * 10 * 0.9)

    def test_dev_fleet_regression(self):
        for d in sim.fleet(5, 1, 2, 2):
            win = d["shift"] if d["contract"] == "shift" else (0.0, sim.DAY)
            t = ledger.invoice(ledger.minutes(d["truth"], win), d["contract"], d["shift"])["amount"]
            e = ledger.invoice(ledger.minutes(ledger.timeline(d["events"])[0], win), d["contract"], d["shift"])["amount"]
            self.assertLessEqual(e, t * 1.01 + 0.5)


if __name__ == "__main__":
    unittest.main()
