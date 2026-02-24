# -*- coding: utf-8 -*-
"""
MySQL Writer: grava um LoadResult (lido de MDB) no banco MySQL.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    raise ImportError("pymysql não instalado. Execute: pip install pymysql cryptography")

from .mdb_reader import LoadResult, ep_data_meta_key, EpDataMeta


# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------

def connect(host: str, user: str, password: str, database: str, port: int = 3306):
    """Abre conexão com o MySQL. Lança pymysql.Error em caso de falha."""
    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def apply_schema(conn, schema_path: Optional[str] = None) -> None:
    """Executa o schema.sql na conexão fornecida."""
    if schema_path is None:
        schema_path = str(Path(__file__).resolve().parent.parent / "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()
    cursor = conn.cursor()
    for statement in sql.split(";"):
        stmt = statement.strip()
        if stmt and not stmt.startswith("--"):
            cursor.execute(stmt)
    conn.commit()


# ---------------------------------------------------------------------------
# Migração
# ---------------------------------------------------------------------------

def write(data: LoadResult, conn, truncate: bool = True, progress=None) -> dict:
    """
    Grava o LoadResult no MySQL.

    Args:
        data:     resultado da leitura MDB (mdb_reader.load)
        conn:     conexão pymysql
        truncate: se True, limpa as tabelas antes de inserir
        progress: callable(msg: str) para output de progresso (padrão: print)

    Retorna dict com contagens: patients, sessions, records, ep_data, stimulus.
    """
    if progress is None:
        progress = print

    cursor = conn.cursor()

    if truncate:
        progress("Limpando tabelas...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        for table in ("stimulus_data", "amplifier_calibration", "ep_data", "records", "sessions", "patients"):
            cursor.execute(f"TRUNCATE TABLE {table}")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()

    # Pacientes
    patient_map: dict[str, int] = {}
    for p in data.patients:
        cursor.execute(
            """INSERT INTO patients (blsc_id, patient_id, first_name, last_name, birthdate, sex, last_test)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 patient_id=VALUES(patient_id), first_name=VALUES(first_name),
                 last_name=VALUES(last_name), birthdate=VALUES(birthdate),
                 sex=VALUES(sex), last_test=VALUES(last_test)""",
            (p.blsc_id, p.patient_id, p.first_name, p.last_name,
             p.birthdate, p.sex, p.last_test),
        )
        patient_map[p.blsc_id] = cursor.lastrowid
    conn.commit()
    progress(f"  Pacientes: {len(patient_map)}")

    session_map: dict[tuple, int] = {}
    record_count = ep_data_count = stim_count = session_count = 0

    for p in data.patients:
        db_patient_id = patient_map[p.blsc_id]

        for sess in p.sessions:
            sess_key = (db_patient_id, str(sess.session_date))
            if sess_key not in session_map:
                cursor.execute(
                    """INSERT INTO sessions (patient_id, session_date, first_start)
                       VALUES (%s, %s, %s)""",
                    (db_patient_id, sess.session_date, sess.first_start),
                )
                session_map[sess_key] = cursor.lastrowid
                session_count += 1
            db_session_id = session_map[sess_key]

            for ex in sess.exams:
                # Record
                cursor.execute(
                    """INSERT INTO records
                       (session_id, record_id, blsc_id, test_id, test_type, test_type_name,
                        start_time, stop_time, comments, channels, epoch_ms, points,
                        pre_post_points, blocked_points, ad_bits, collection_rate_hz,
                        max_of_averages, u_v_per_count, data_hex)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                         test_type_name=VALUES(test_type_name),
                         start_time=VALUES(start_time),
                         data_hex=VALUES(data_hex)""",
                    (
                        db_session_id, ex.record_id, ex.blsc_id, ex.test_id,
                        ex.test_type, ex.test_type_name,
                        ex.start, ex.stop, ex.comments, ex.channels, ex.epoch_ms,
                        ex.points, ex.pre_post_points, ex.blocked_points, ex.ad_bits,
                        ex.collection_rate_hz, ex.max_of_averages, ex.u_v_per_count,
                        ex.data_hex,
                    ),
                )
                record_count += 1

                # EPData — todos os pares (channel, bank)
                chan_banks = data.chan_banks_by_record_id.get(ex.record_id, [])
                if not chan_banks and ex.channel_number > 0 and ex.bank_number > 0:
                    chan_banks = [(ex.channel_number, ex.bank_number)]

                for ch, bk in chan_banks:
                    meta = data.ep_meta_by_key.get(
                        ep_data_meta_key(ex.record_id, ch, bk), EpDataMeta()
                    )
                    avg = meta.averages if meta.averages >= 0 else None
                    rej = meta.rejected if meta.rejected >= 0 else None
                    low = meta.low_analysis_filter or ex.low_analysis_filter
                    high = meta.high_analysis_filter or ex.high_analysis_filter
                    cursor.execute(
                        """INSERT INTO ep_data
                           (record_id, channel_number, bank_number, averages, rejected,
                            low_analysis_filter, high_analysis_filter,
                            dc_offset_counts, has_dc_offset_counts)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON DUPLICATE KEY UPDATE
                             averages=VALUES(averages), rejected=VALUES(rejected),
                             low_analysis_filter=VALUES(low_analysis_filter),
                             high_analysis_filter=VALUES(high_analysis_filter),
                             dc_offset_counts=VALUES(dc_offset_counts),
                             has_dc_offset_counts=VALUES(has_dc_offset_counts)""",
                        (
                            ex.record_id, ch, bk, avg, rej, low, high,
                            meta.dc_offset_counts, meta.has_dc_offset_counts,
                        ),
                    )
                    ep_data_count += 1

                # Estímulo
                if ex.ear or ex.stimulus or ex.stim_rate or ex.stim_intensity or ex.insert_delay_ms:
                    cursor.execute(
                        """INSERT INTO stimulus_data
                           (record_id, ear, stimulus, stim_rate, stim_intensity, insert_delay_ms)
                           VALUES (%s,%s,%s,%s,%s,%s)
                           ON DUPLICATE KEY UPDATE
                             ear=VALUES(ear), stimulus=VALUES(stimulus),
                             stim_rate=VALUES(stim_rate), stim_intensity=VALUES(stim_intensity),
                             insert_delay_ms=VALUES(insert_delay_ms)""",
                        (
                            ex.record_id, ex.ear, ex.stimulus, ex.stim_rate,
                            ex.stim_intensity, ex.insert_delay_ms,
                        ),
                    )
                    stim_count += 1

    conn.commit()
    progress(f"  Sessões:   {session_count}")
    progress(f"  Records:   {record_count}")
    progress(f"  EPData:    {ep_data_count}  (pares canal/banco)")
    progress(f"  Estímulos: {stim_count}")

    return {
        "patients": len(patient_map),
        "sessions": session_count,
        "records": record_count,
        "ep_data": ep_data_count,
        "stimulus": stim_count,
    }
