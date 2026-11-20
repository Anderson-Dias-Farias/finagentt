"""Testes do modulo de operacao (storage, backup, relatorio) — sem rede."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finagent import journal, ops  # noqa: E402

NOW = 1_700_000_000_000


class OpsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self._db, self._bk = journal.DB_PATH, ops.BACKUP_DIR
        journal.DB_PATH = root / "journal.db"
        ops.BACKUP_DIR = root / "backups"
        ops.init_storage()

    def tearDown(self) -> None:
        journal.DB_PATH, ops.BACKUP_DIR = self._db, self._bk
        self.tmp.cleanup()

    def _seed(self, rows):
        with journal._conn() as c:
            for i, (setup, direction, conv, outcome, r) in enumerate(rows):
                c.execute(
                    "INSERT INTO signals (ts,symbol,tf,direction,status,setup,conviction,price,"
                    "entry,stop,tp1,tp2,rr,snapshot,outcome,exit_price,r_multiple,closed_ts,"
                    "mfe_pct,mae_pct) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (NOW + i, "BTCUSDT", "15m", direction, "EXECUTAVEL", setup, conv,
                     100.0, 100.0, 99.0, 102.0, 103.0, 2.0, "{}", outcome, 101.0 if r > 0 else 99.0,
                     r, NOW + 10_000, abs(r) * 1.5, -abs(r) * 0.4),
                )

    def test_performance_separa_setup_tf_e_conviccao(self):
        self._seed([
            ("Liquidity sweep + reversao", "LONG", 72, "WIN_TP1", 2.0),
            ("Liquidity sweep + reversao", "LONG", 65, "LOSS", -1.0),
            ("Breakout/BOS com continuacao", "SHORT", 58, "WIN_TP2", 3.2),
            ("Breakout/BOS com continuacao", "SHORT", 40, "LOSS", -1.0),
        ])
        p = ops.performance()
        self.assertEqual(p["total"]["n"], 4)
        self.assertAlmostEqual(p["total"]["win_rate"], 50.0)
        self.assertAlmostEqual(p["total"]["avg_r"], (2.0 - 1.0 + 3.2 - 1.0) / 4)
        self.assertIn("Liquidity sweep + reversao (LONG)", p["by_setup"])
        self.assertEqual(p["by_setup"]["Breakout/BOS com continuacao (SHORT)"]["n"], 2)
        self.assertEqual(p["by_tf"]["15m"]["n"], 4)
        self.assertEqual(p["by_conviction"][">=60"]["n"], 2)
        self.assertEqual(p["by_conviction"]["45-60"]["n"], 1)
        self.assertEqual(p["by_conviction"]["<45"]["n"], 1)
        self.assertIsNotNone(p["sample_warning"])

    def test_performance_vazio_nao_quebra(self):
        p = ops.performance()
        self.assertEqual(p["total"]["n"], 0)
        self.assertEqual(p["total"]["win_rate"], 0.0)
        self.assertEqual(p["by_setup"], {})

    def test_state_e_health_refletem_storage(self):
        self._seed([("X", "LONG", 70, "WIN_TP1", 2.0)])
        self._seed([("Y", "SHORT", 30, "OPEN", 0.0)])
        st = ops.state()
        self.assertTrue(st["db"]["exists"])
        self.assertTrue(st["db"]["writable"])
        self.assertGreater(st["db"]["size_bytes"], 0)
        self.assertEqual(st["counts"]["signals"], 2)
        self.assertEqual(st["counts"]["open"], 1)
        self.assertTrue(ops.health()["ok"])

    def test_backup_copia_e_podruga(self):
        self._seed([("X", "LONG", 70, "WIN_TP1", 2.0)])
        first = ops.backup()
        self.assertTrue(first and Path(first).exists())
        with sqlite3.connect(first) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM signals").fetchone()[0], 1)
        old = ops.KEEP_BACKUPS
        try:
            ops.KEEP_BACKUPS = 2
            for _ in range(3):
                ops.backup()
            self.assertLessEqual(len(list(ops.BACKUP_DIR.glob("journal-*.db"))), 2)
        finally:
            ops.KEEP_BACKUPS = old

    def test_init_storage_idempotente(self):
        ops.init_storage()
        ops.init_storage()
        self.assertTrue(ops.BACKUP_DIR.exists())
        self.assertTrue(ops.health()["ok"])


if __name__ == "__main__":
    unittest.main()
