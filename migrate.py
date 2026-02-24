#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EPWin MDB → MySQL Migrator
Converte qualquer par EPWinData.mdb + BLPatients.mdb para MySQL.

Uso:
  python migrate.py <EPWinData.mdb> <BLPatients.mdb> [opções]

Exemplos:
  # Com Docker (sobe MySQL automaticamente)
  python migrate.py "Bancos/EPWinData.mdb" "Bancos/BLPatients.mdb" --docker

  # MySQL já rodando, usando config.ini
  python migrate.py "Bancos/EPWinData.mdb" "Bancos/BLPatients.mdb" --config config.ini

  # Sem Docker, credenciais na linha de comando
  python migrate.py "Bancos/EPWinData.mdb" "Bancos/BLPatients.mdb" \\
      --host localhost --user root --password epwin

  # Apenas aplicar o schema (sem migrar dados)
  python migrate.py --schema-only

  # Listar bancos MDB disponíveis em um diretório
  python migrate.py --scan "Bancos de dados/"
"""
from __future__ import annotations

import argparse
import configparser
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BOLD  = "\033[1m"
GREEN = "\033[32m"
CYAN  = "\033[36m"
YELLOW= "\033[33m"
RED   = "\033[31m"
RESET = "\033[0m"


def _log(msg: str, color: str = "") -> None:
    print(f"{color}{msg}{RESET}" if color else msg, flush=True)


def _banner(title: str) -> None:
    line = "─" * (len(title) + 4)
    _log(f"\n┌{line}┐", CYAN)
    _log(f"│  {title}  │", CYAN)
    _log(f"└{line}┘", CYAN)


def _load_config(path: str, args) -> dict:
    cfg = configparser.ConfigParser()
    cfg.read(path)
    return {
        "host":     cfg.get("mysql", "host",     fallback=args.host),
        "port":     cfg.getint("mysql", "port",  fallback=args.port),
        "user":     cfg.get("mysql", "user",     fallback=args.user),
        "password": cfg.get("mysql", "password", fallback=args.password),
        "database": cfg.get("mysql", "database", fallback=args.database),
    }


def _wait_for_mysql(host: str, port: int, user: str, password: str,
                    database: str, timeout: int = 90) -> bool:
    _log("Aguardando MySQL ficar pronto...", YELLOW)
    deadline = time.monotonic() + timeout
    try:
        import pymysql
        while time.monotonic() < deadline:
            try:
                conn = pymysql.connect(host=host, port=port, user=user,
                                       password=password, database=database,
                                       connect_timeout=3)
                conn.close()
                return True
            except Exception:
                time.sleep(2)
        return False
    except ImportError:
        while time.monotonic() < deadline:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((host, port))
                s.close()
                return True
            except OSError:
                time.sleep(2)
        return False


def _docker_up(cwd: Path) -> bool:
    _log("Subindo MySQL com Docker...", YELLOW)
    r = subprocess.run(["docker", "compose", "up", "-d", "mysql"],
                       cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        _log(r.stderr or r.stdout or "Falha ao subir Docker", RED)
        return False
    return True


def _apply_schema_docker(cfg: dict, schema_path: Path, cwd: Path) -> bool:
    _log("Aplicando schema (via docker compose exec)...", YELLOW)
    with open(schema_path, "rb") as f:
        r = subprocess.run(
            ["docker", "compose", "exec", "-T", "mysql",
             "mysql", f"-u{cfg['user']}", f"-p{cfg['password']}", cfg["database"]],
            cwd=cwd, stdin=f, capture_output=True, text=True,
        )
    if r.returncode != 0:
        _log(r.stderr or "Falha ao aplicar schema", RED)
        return False
    return True


def _apply_schema_local(cfg: dict, schema_path: Path) -> bool:
    _log("Aplicando schema (mysql client)...", YELLOW)
    with open(schema_path, "rb") as f:
        r = subprocess.run(
            ["mysql",
             f"-h{cfg['host']}", f"-P{cfg['port']}",
             f"-u{cfg['user']}", f"-p{cfg['password']}"],
            stdin=f, capture_output=True, text=True,
        )
    if r.returncode != 0:
        _log(r.stderr or "Falha ao aplicar schema (mysql no PATH?)", RED)
        return False
    return True


# ---------------------------------------------------------------------------
# Subcommand: scan
# ---------------------------------------------------------------------------

def cmd_scan(directory: str) -> None:
    _banner(f"Scan: {directory}")
    base = Path(directory)
    if not base.exists():
        _log(f"Diretório não encontrado: {directory}", RED)
        sys.exit(1)
    found = []
    for epwin in base.rglob("EPWinData.mdb"):
        bl = epwin.parent / "BLPatients.mdb"
        found.append((epwin, bl if bl.exists() else None))
    if not found:
        _log("Nenhum EPWinData.mdb encontrado.", YELLOW)
        return
    _log(f"Encontrados {len(found)} banco(s):\n")
    for i, (epwin, bl) in enumerate(found, 1):
        bl_status = "✓" if bl else "✗ BLPatients.mdb ausente"
        _log(f"  [{i}] {epwin.parent.name}/")
        _log(f"       EPWinData.mdb  → {epwin}")
        _log(f"       BLPatients.mdb → {bl or bl_status}")
        print()
    _log("Para migrar, execute:", CYAN)
    epwin, bl = found[0]
    _log(f'  python migrate.py "{epwin}" "{bl}" --docker', CYAN)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="EPWin MDB → MySQL Migrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Positional / scan
    parser.add_argument("epwin_mdb",    nargs="?", help="Caminho para EPWinData.mdb")
    parser.add_argument("blpatients_mdb", nargs="?", help="Caminho para BLPatients.mdb")
    parser.add_argument("--scan", metavar="DIR",
                        help="Listar bancos MDB disponíveis em um diretório")

    # Conexão
    parser.add_argument("--config", "-c", metavar="FILE", default="config.ini",
                        help="Arquivo .ini com seção [mysql] (default: config.ini)")
    parser.add_argument("--host",     default="localhost")
    parser.add_argument("--port",     default=3306,  type=int)
    parser.add_argument("--user",     default="root")
    parser.add_argument("--password", default="epwin")
    parser.add_argument("--database", default="epwin")

    # Comportamento
    parser.add_argument("--docker",      action="store_true",
                        help="Subir MySQL com 'docker compose up -d mysql' antes de migrar")
    parser.add_argument("--schema-only", action="store_true",
                        help="Apenas aplicar o schema.sql, sem migrar dados")
    parser.add_argument("--no-truncate", action="store_true",
                        help="Não limpar tabelas antes de inserir (modo append)")
    parser.add_argument("--schema",      metavar="FILE",
                        help="Caminho alternativo para schema.sql")

    args = parser.parse_args()

    # --- Scan mode ---
    if args.scan:
        cmd_scan(args.scan)
        return 0

    # --- Resolver config ---
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    cfg = _load_config(str(config_path) if config_path.exists() else "", args)

    schema_path = Path(args.schema) if args.schema else ROOT / "schema.sql"
    if not schema_path.exists():
        _log(f"schema.sql não encontrado: {schema_path}", RED)
        return 1

    _banner("EPWin MDB → MySQL Migrator")
    _log(f"  MySQL: {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']}")

    # --- Docker ---
    if args.docker:
        if not _docker_up(ROOT):
            return 1
        if not _wait_for_mysql(**cfg):
            _log("MySQL não respondeu a tempo.", RED)
            return 1
        if not _apply_schema_docker(cfg, schema_path, ROOT):
            return 1
    else:
        if not _wait_for_mysql(**cfg, timeout=10):
            _log(f"MySQL não acessível em {cfg['host']}:{cfg['port']}.\n"
                 "Use --docker para subir automaticamente, ou verifique a conexão.", RED)
            return 1
        if not _apply_schema_local(cfg, schema_path):
            return 1

    _log("Schema aplicado.", GREEN)

    if args.schema_only:
        _log("Modo --schema-only: concluído.", GREEN)
        return 0

    # --- Precisamos dos .mdb ---
    if not args.epwin_mdb or not args.blpatients_mdb:
        _log("Informe os caminhos para EPWinData.mdb e BLPatients.mdb.", RED)
        _log("Use --scan <dir> para listar bancos disponíveis.", YELLOW)
        parser.print_usage()
        return 1

    epwin_path = args.epwin_mdb
    bl_path = args.blpatients_mdb
    _log(f"\n  EPWinData:   {epwin_path}")
    _log(f"  BLPatients:  {bl_path}")

    # --- Leitura MDB ---
    _log("\nLendo dados do MDB...", YELLOW)
    try:
        from src.mdb_reader import load as mdb_load
    except ImportError as e:
        _log(f"Erro ao importar mdb_reader: {e}", RED)
        return 1

    data = mdb_load(epwin_path, bl_path)
    if data.error:
        _log(f"Erro ao ler MDB: {data.error}", RED)
        return 1
    _log(f"  {len(data.patients)} paciente(s) lidos do MDB.", GREEN)

    # --- Escrita no MySQL ---
    _log("\nGravando no MySQL...", YELLOW)
    try:
        import pymysql
        from src.mysql_writer import connect, write as mysql_write
    except ImportError as e:
        _log(f"Erro: {e}", RED)
        return 1

    try:
        conn = connect(**cfg)
    except pymysql.Error as e:
        _log(f"Erro ao conectar: {e}", RED)
        return 1

    try:
        counts = mysql_write(
            data, conn,
            truncate=not args.no_truncate,
            progress=lambda msg: _log(msg),
        )
    finally:
        conn.close()

    _banner("Migração concluída")
    _log(f"  Pacientes:  {counts['patients']}", GREEN)
    _log(f"  Sessões:    {counts['sessions']}", GREEN)
    _log(f"  Records:    {counts['records']}", GREEN)
    _log(f"  EPData:     {counts['ep_data']}  (pares canal/banco)", GREEN)
    _log(f"  Estímulos:  {counts['stimulus']}", GREEN)
    _log("\nPronto! Execute o EPWinViewer com: python run.py\n", GREEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
