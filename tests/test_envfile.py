"""Testes do leitor de .env e do diagnostico de DATABASE_URL (sem rede real)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finagent import envfile


class TestParse(unittest.TestCase):
    def test_basico(self):
        d = envfile.parse("A=1\nB=dois\n\n# comentario\nINVALIDO\n")
        self.assertEqual(d, {"A": "1", "B": "dois"})

    def test_aspas_e_export(self):
        d = envfile.parse('export X="a b"\nY=\'c d\'\nZ=  sem_espaco  \n')
        self.assertEqual(d, {"X": "a b", "Y": "c d", "Z": "sem_espaco"})

    def test_valor_vazio_e_hash_no_valor(self):
        d = envfile.parse("VAZIO=\nURL=postgresql://u:p#frag@h/db\n")
        self.assertEqual(d["VAZIO"], "")
        self.assertIn("p#frag", d["URL"])

    def test_comentario_inline(self):
        d = envfile.parse("KEEP=14   # copias mantidas\nURL=postgresql://u:p#frag@h/db\n")
        self.assertEqual(d["KEEP"], "14")
        self.assertIn("p#frag", d["URL"])

    def test_chave_invalida_ignorada(self):
        self.assertEqual(envfile.parse("1BAD=x\nOK=y\n"), {"OK": "y"})


class TestLoad(unittest.TestCase):
    def test_arquivo_ausente_nao_quebra(self):
        self.assertEqual(envfile.load("/caminho/que/nao/existe/.env"), {})

    def test_env_real_tem_prioridade(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("FINAGENT_TESTE_X=do_arquivo\nFINAGENT_TESTE_Y=do_arquivo\n")
            os.environ["FINAGENT_TESTE_X"] = "do_ambiente"
            try:
                applied = envfile.load(p)
            finally:
                os.environ.pop("FINAGENT_TESTE_X", None)
                os.environ.pop("FINAGENT_TESTE_Y", None)
            self.assertEqual(applied, {"FINAGENT_TESTE_Y": "do_arquivo"})


class TestPostgresInfo(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop("DATABASE_URL", None)

    def tearDown(self):
        os.environ.pop("DATABASE_URL", None)
        if self._old is not None:
            os.environ["DATABASE_URL"] = self._old

    def test_vazio(self):
        self.assertEqual(envfile.postgres_info(), {"configured": False})

    def test_parse_sem_vazar_senha(self):
        os.environ["DATABASE_URL"] = (
            "postgresql://finagent:SenhaSuperSecreta@db.interno:6543/finagent?sslmode=require"
        )
        info = envfile.postgres_info()
        self.assertEqual(info["host"], "db.interno")
        self.assertEqual(info["port"], 6543)
        self.assertEqual(info["database"], "finagent")
        self.assertEqual(info["user"], "finagent")
        self.assertEqual(info["sslmode"], "require")
        self.assertTrue(info["has_password"])
        self.assertNotIn("SenhaSuperSecreta", json.dumps(info))

    def test_porta_default_e_scheme_invalido(self):
        os.environ["DATABASE_URL"] = "postgres://u:p@h/finagent"
        self.assertEqual(envfile.postgres_info()["port"], 5432)
        os.environ["DATABASE_URL"] = "mysql://u:p@h/finagent"
        self.assertFalse(envfile.postgres_info()["valid"])

    def test_status_porta_fechada(self):
        os.environ["DATABASE_URL"] = "postgresql://u:p@127.0.0.1:1/finagent"
        st = envfile.postgres_status(timeout=0.5)
        self.assertTrue(st["configured"])
        self.assertFalse(st["tcp_reachable"])
        self.assertFalse(st["used_for_journal"])


class TestOrdemDeCarga(unittest.TestCase):
    """Regression: .env tem que entrar antes de os modulos lerem o ambiente.

    journal.DB_PATH e ops.BACKUP_DIR sao resolvidos no import — se o .env carregar
    depois, FINAGENT_DB/FINAGENT_DATA no arquivo sao silenciosamente ignorados.
    """

    def test_env_define_caminho_no_import(self):
        import subprocess

        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / "custom.env"
            env_file.write_text(f"FINAGENT_DB={d}/journal.db\nFINAGENT_BACKUP_KEEP=21\n")
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith("FINAGENT_") and k != "DATABASE_URL"}
            env["FINAGENT_ENV_FILE"] = str(env_file)
            out = subprocess.run(
                [sys.executable, "-c",
                 "from finagent import journal, ops; print(journal.DB_PATH); print(ops.KEEP_BACKUPS)"],
                cwd=root, env=env, capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(out.returncode, 0, out.stderr)
        linhas = out.stdout.strip().splitlines()
        self.assertEqual(linhas[0], f"{d}/journal.db")
        self.assertEqual(linhas[1], "21")


if __name__ == "__main__":
    unittest.main()
