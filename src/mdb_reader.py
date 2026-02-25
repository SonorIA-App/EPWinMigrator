# -*- coding: utf-8 -*-
"""
MDB Reader: lê EPWinData.mdb e BLPatients.mdb via mdbtools (mdb-export) e
retorna uma estrutura hierárquica (LoadResult) com todos os dados.

Baseado na lógica do EPWinReader C++ (mdbbackend.cpp).
Requer mdbtools instalado: brew install mdbtools (macOS) / apt install mdbtools (Linux).
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional


def _norm_header(h: str) -> str:
    return h.strip().lower().replace(" ", "").replace("_", "")


def _col(norm_headers: list[str], names: list[str]) -> int:
    for i, nh in enumerate(norm_headers):
        for n in names:
            if nh == n or (n in nh):
                return i
    return -1


def _run_capture(cmd: list[str], timeout_ms: int = 300000) -> tuple[bool, str, str]:
    """Executa comando e retorna (ok, stdout, stderr)."""
    try:
        env = os.environ.copy()
        for extra in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
            if extra not in env.get("PATH", ""):
                env["PATH"] = f"{extra}:{env.get('PATH', '')}"
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_ms // 1000) if timeout_ms > 0 else None,
            env=env,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        return (r.returncode == 0, out, err)
    except FileNotFoundError:
        return (False, "", f"Comando não encontrado: {cmd[0]}")
    except subprocess.TimeoutExpired:
        return (False, "", f"Timeout ao executar {cmd[0]}")


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1].replace('""', '"')
    return s


def _read_next_record(text: str, pos: int) -> tuple[int, str]:
    """Lê próxima linha (respeitando aspas em campos com newline)."""
    if pos >= len(text):
        return len(text), ""
    i = pos
    in_quotes = False
    while i < len(text):
        c = text[i]
        if c == '"':
            if i + 1 < len(text) and text[i + 1] == '"':
                i += 1
            else:
                in_quotes = not in_quotes
        elif c in "\n\r" and not in_quotes:
            end = i
            if c == "\r" and i + 1 < len(text) and text[i + 1] == "\n":
                i += 1
            return i + 1, text[pos:end]
        i += 1
    return len(text), text[pos:]


def _split_row(row: str) -> list[str]:
    out = []
    cur = []
    in_quotes = False
    i = 0
    while i < len(row):
        c = row[i]
        if c == '"':
            cur.append(c)
            if i + 1 < len(row) and row[i + 1] == '"':
                cur.append('"')
                i += 1
        elif c == "\t" and not in_quotes:
            out.append(_unquote("".join(cur)))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append(_unquote("".join(cur)))
    return out


def _norm_guid(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    if len(s) >= 32 and len(s) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in s):
        try:
            b = bytes.fromhex(s).decode("latin-1", errors="ignore").strip()
            if "{" in b and "-" in b and "}" in b:
                s = b
        except Exception:
            pass
    return s.upper()


def _parse_datetime(s: str) -> Optional[datetime]:
    s = s.strip()
    if not s:
        return None
    for fmt in (
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%y %I:%M:%S %p",
        "%m/%d/%Y %I:%M:%S %p",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.year < 1970:
                dt = dt.replace(year=dt.year + 100)
            return dt
        except ValueError:
            continue
    return None


def _parse_date(s: str) -> Optional[date]:
    s = s.strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%y %H:%M:%S", "%m/%d/%Y", "%m/%d/%y"):
        try:
            if " " in fmt:
                dt = datetime.strptime(s, fmt)
                d = dt.date()
            else:
                d = datetime.strptime(s, fmt).date()
            if d.year < 1970:
                d = d.replace(year=d.year + 100)
            return d
        except ValueError:
            continue
    return None


def _to_int(s: str, default: int = 0) -> int:
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        return default


def _to_double(s: str, default: float = 0.0) -> float:
    try:
        return float(s.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return default


# ---------------------------------------------------------------------------
# Modelos de dados (espelho do MdbBackend C++)
# ---------------------------------------------------------------------------


@dataclass
class EpDataMeta:
    averages: int = -1
    rejected: int = -1
    amplifier_gain: int = 0
    has_dc_offset_counts: bool = False
    dc_offset_counts: int = 0
    low_analysis_filter: str = ""
    high_analysis_filter: str = ""


@dataclass
class ExamInfo:
    blsc_id: str = ""
    record_id: str = ""
    test_id: str = ""
    test_type: int = -1
    test_type_name: str = ""
    start: Optional[datetime] = None
    stop: Optional[datetime] = None
    comments: str = ""
    epoch_ms: float = 0.0
    points: int = 0
    channels: int = 0
    pre_post_points: int = 0
    blocked_points: int = 0
    ad_bits: int = 16
    collection_rate_hz: float = 0.0
    max_of_averages: int = 0
    u_v_per_count: float = 0.0
    data_hex: str = ""
    channel_number: int = 0
    bank_number: int = 0
    averages: str = ""
    rejected: str = ""
    low_analysis_filter: str = ""
    high_analysis_filter: str = ""
    ear: str = ""
    stimulus: str = ""
    stim_rate: str = ""
    stim_intensity: str = ""
    insert_delay_ms: float = 0.0


@dataclass
class SessionInfo:
    session_date: Optional[date] = None
    first_start: Optional[datetime] = None
    exams: list[ExamInfo] = field(default_factory=list)


@dataclass
class PatientInfo:
    blsc_id: str = ""
    patient_id: str = ""
    first_name: str = ""
    last_name: str = ""
    birthdate: Optional[date] = None
    sex: str = ""
    last_test: Optional[datetime] = None
    sessions: list[SessionInfo] = field(default_factory=list)


@dataclass
class LoadResult:
    error: str = ""
    epwin_path: str = ""
    blpatients_path: str = ""
    epwin_tables: list[str] = field(default_factory=list)
    patients: list[PatientInfo] = field(default_factory=list)
    chan_banks_by_record_id: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    ep_meta_by_key: dict[str, EpDataMeta] = field(default_factory=dict)
    ep_data_hex_by_key: dict[str, str] = field(default_factory=dict)
    ep_data_points_by_key: dict[str, int] = field(default_factory=dict)
    ep_data_dc_offset_counts_by_key: dict[str, int] = field(default_factory=dict)


def ep_data_meta_key(record_id: str, channel: int, bank: int) -> str:
    return f"{record_id}|{channel}|{bank}"


# ---------------------------------------------------------------------------
# Carregamento BLPatients
# ---------------------------------------------------------------------------


def _load_bl_patients(path: str) -> tuple[dict[str, dict], str]:
    """Retorna (map blsc_id -> {patient_id, first, last, birth, sex}, error)."""
    ok, out, err = _run_capture(["mdb-export", "-d", "\t", path, "Patients"], 240000)
    if not ok:
        return {}, err or "Falha ao exportar Patients"
    pos = 0
    line_pos, rec = _read_next_record(out, pos)
    pos = line_pos
    if not rec:
        return {}, ""
    header = _split_row(rec)
    nh = [_norm_header(h) for h in header]
    i_blsc = _col(nh, ["blscid"])
    if i_blsc < 0:
        return {}, "Coluna BLSCID não encontrada em Patients"
    i_pid = _col(nh, ["patientid"])
    i_first = _col(nh, ["firstname"])
    i_last = _col(nh, ["lastname"])
    i_birth = _col(nh, ["birthdate", "dob"])
    i_sex = _col(nh, ["sex", "gender"])

    dem_map = {}
    while pos < len(out):
        line_pos, rec = _read_next_record(out, pos)
        pos = line_pos
        if not rec.strip():
            continue
        row = _split_row(rec)
        if len(row) <= i_blsc:
            continue
        blsc = _norm_guid(row[i_blsc])
        if not blsc:
            continue
        dem = {
            "patient_id": row[i_pid].strip() if i_pid >= 0 and len(row) > i_pid else "",
            "first": row[i_first].strip() if i_first >= 0 and len(row) > i_first else "",
            "last": row[i_last].strip() if i_last >= 0 and len(row) > i_last else "",
            "sex": row[i_sex].strip() if i_sex >= 0 and len(row) > i_sex else "",
            "birth": None,
        }
        if i_birth >= 0 and len(row) > i_birth:
            bd = row[i_birth].strip()
            dt = _parse_datetime(bd)
            if dt:
                dem["birth"] = dt.date()
            else:
                d = _parse_date(bd) if bd else None
                if d:
                    if d.year < 1970:
                        d = d.replace(year=d.year + 100)
                    dem["birth"] = d
        dem_map[blsc] = dem
    return dem_map, ""


# ---------------------------------------------------------------------------
# Carregamento EPData (metadata por RecordID / Channel / Bank)
# ---------------------------------------------------------------------------


def _load_ep_data(epwin_path: str) -> tuple[dict, dict[str, EpDataMeta], str]:
    """Retorna (map rid -> {ch, bk, avg, rej, low, high}, ep_meta_by_key, error)."""
    ok, out, err = _run_capture(["mdb-export", "-d", "\t", epwin_path, "EPData"], 240000)
    if not ok:
        return {}, {}, err or "Falha ao exportar EPData"
    pos = 0
    line_pos, rec = _read_next_record(out, pos)
    pos = line_pos
    if not rec:
        return {}, {}, ""
    header = _split_row(rec)
    nh = [_norm_header(h) for h in header]
    i_rid = _col(nh, ["recordid"])
    i_ch = _col(nh, ["channelnumber"])
    i_bk = _col(nh, ["banknumber"])
    i_avg = _col(nh, ["averages"])
    i_rej = _col(nh, ["artifactsrejected", "rejected"])
    i_low = _col(nh, ["lowanalysisfilter", "lowfilter"])
    i_high = _col(nh, ["highanalysisfilter", "highfilter"])
    i_off = _col(nh, ["dcoffset", "dcoffsetcounts", "dcoffsetvalue", "baselineoffset", "offset"])
    if i_off < 0:
        for i, h in enumerate(nh):
            if "offset" in h and "insert" not in h and "delay" not in h:
                i_off = i
                break
    if i_rid < 0:
        return {}, {}, ""

    ep_map = {}
    meta_by_key = {}
    while pos < len(out):
        line_pos, rec = _read_next_record(out, pos)
        pos = line_pos
        if not rec.strip():
            continue
        row = _split_row(rec)
        if len(row) <= i_rid:
            continue
        rid = _norm_guid(row[i_rid])
        if not rid:
            continue
        is_first = rid not in ep_map
        ch = _to_int(row[i_ch]) if i_ch >= 0 and len(row) > i_ch else 0
        bk = _to_int(row[i_bk]) if i_bk >= 0 and len(row) > i_bk else 0
        avg = row[i_avg].strip() if i_avg >= 0 and len(row) > i_avg else ""
        rej = row[i_rej].strip() if i_rej >= 0 and len(row) > i_rej else ""
        low = row[i_low].strip() if i_low >= 0 and len(row) > i_low else ""
        high = row[i_high].strip() if i_high >= 0 and len(row) > i_high else ""
        key = ep_data_meta_key(rid, ch, bk)
        dm = EpDataMeta(
            averages=_to_int(avg, -1),
            rejected=_to_int(rej, -1),
            low_analysis_filter=low,
            high_analysis_filter=high,
        )
        if i_off >= 0 and len(row) > i_off:
            off_s = row[i_off].strip()
            if off_s and off_s != "0":
                try:
                    dv = float(off_s.replace(",", "."))
                    dm.has_dc_offset_counts = True
                    dm.dc_offset_counts = int(round(dv))
                except ValueError:
                    pass
        meta_by_key[key] = dm
        if is_first:
            ep_map[rid] = {"ch": ch, "bk": bk, "avg": avg, "rej": rej, "low": low, "high": high}
    return ep_map, meta_by_key, ""


def _load_ep_chan_banks(epwin_path: str) -> dict[str, list[tuple[int, int]]]:
    ok, out, err = _run_capture(["mdb-export", "-d", "\t", epwin_path, "EPData"], 240000)
    if not ok:
        return {}
    pos = 0
    line_pos, rec = _read_next_record(out, pos)
    pos = line_pos
    if not rec:
        return {}
    header = _split_row(rec)
    nh = [_norm_header(h) for h in header]
    i_rid = _col(nh, ["recordid"])
    i_ch = _col(nh, ["channelnumber"])
    i_bk = _col(nh, ["banknumber"])
    if i_rid < 0 or i_ch < 0 or i_bk < 0:
        return {}
    result = {}
    while pos < len(out):
        line_pos, rec = _read_next_record(out, pos)
        pos = line_pos
        if not rec.strip():
            continue
        row = _split_row(rec)
        need = max(i_rid, i_ch, i_bk)
        if len(row) <= need:
            continue
        rid = _norm_guid(row[i_rid])
        if not rid:
            continue
        ch = _to_int(row[i_ch])
        bk = _to_int(row[i_bk])
        pair = (ch, bk)
        if rid not in result:
            result[rid] = []
        if pair not in result[rid]:
            result[rid].append(pair)
    for rid in result:
        result[rid] = sorted(result[rid], key=lambda x: (x[0], x[1]))
    return result


# ---------------------------------------------------------------------------
# Amplifiers (calibração uV/count)
# ---------------------------------------------------------------------------


def _default_uv_per_count_from_ad_bits(ad_bits: int) -> float:
    if ad_bits <= 0 or ad_bits > 40:
        return 0.0
    denom = 2.0 ** (ad_bits - 1)
    return (1000.0 / denom) if denom > 0 else 0.0


def _load_amplifier_calibration(epwin_path: str) -> dict[str, dict]:
    mdb = epwin_path if epwin_path.lower().endswith(".mdb") else str(Path(epwin_path) / "EPWinData.mdb")
    if not os.path.isfile(mdb):
        return {}
    ok, out, err = _run_capture(["mdb-export", "-d", "\t", mdb, "Amplifiers"], 20000)
    if not ok:
        return {}
    pos = 0
    line_pos, rec = _read_next_record(out, pos)
    pos = line_pos
    if not rec:
        return {}
    header = _split_row(rec)
    nh = [_norm_header(h) for h in header]
    i_rid = _col(nh, ["recordid", "recordguid", "records_id"])
    i_uv = _col(nh, ["uvpercount", "uv_per_count", "microvoltspercount", "vpercount", "voltspercount"])
    i_fs = _col(nh, ["fullscale", "full_scale", "fullscaleuv", "range", "inputrange"])
    i_gain = _col(nh, ["amplifiergain", "ampgain", "gain"])
    if i_rid < 0:
        return {}
    cal_map = {}
    while pos < len(out):
        line_pos, rec = _read_next_record(out, pos)
        pos = line_pos
        if not rec.strip():
            continue
        row = _split_row(rec)
        if len(row) <= i_rid:
            continue
        rid = _norm_guid(row[i_rid])
        if not rid:
            continue
        cal = {"uv_per_count": 0.0, "full_scale_uV": 0.0, "amplifier_gain": 0}
        if i_uv >= 0 and len(row) > i_uv:
            v = _to_double(row[i_uv], 0.0)
            if 0 < v < 1e-3:
                v *= 1e6
            if 0 < v < 100:
                cal["uv_per_count"] = v
        if i_fs >= 0 and len(row) > i_fs:
            fs = _to_double(row[i_fs], 0.0)
            if 0 < fs < 1.0:
                fs *= 1e6
            if 0 < fs < 1e7:
                cal["full_scale_uV"] = fs
        if i_gain >= 0 and len(row) > i_gain:
            g = _to_int(row[i_gain], 0)
            if 0 < g < 1000000000:
                cal["amplifier_gain"] = g
        if cal["uv_per_count"] > 0 or cal["full_scale_uV"] > 0 or cal["amplifier_gain"] > 0:
            cal_map[rid] = cal
    return cal_map


# ---------------------------------------------------------------------------
# Tabelas de estímulo (ear, stimulus, rate, insert delay)
# ---------------------------------------------------------------------------

STIM_TABLES = ["P300Stim", "VEMPStim", "SABRStim", "ABRStim", "AEPStim", "CalculatedStim"]
TYPE_NAMES = {"P300Stim": "P300", "VEMPStim": "VEMP", "SABRStim": "ABR", "AEPStim": "AEP", "CalculatedStim": "Calculated"}

# Records.TestType numérico → nome (fallback quando o record não está em nenhuma tabela Stim)
# Bio-Logic EPWin: 0=AEP, 1=VEMP, 2=P300, 3=SABR, 4=ABR, 9=Other
TEST_TYPE_MAP = {0: "AEP", 1: "VEMP", 2: "P300", 3: "SABR", 4: "ABR", 9: "Other"}


def _load_stim_ear(epwin_path: str, table: str) -> dict[str, str]:
    ok, out, err = _run_capture(["mdb-export", "-d", "\t", epwin_path, table], 240000)
    if not ok:
        return {}
    pos = 0
    line_pos, rec = _read_next_record(out, pos)
    pos = line_pos
    if not rec:
        return {}
    header = _split_row(rec)
    nh = [_norm_header(h) for h in header]
    i_rid = _col(nh, ["recordid"])
    i_ear = _col(nh, ["stimear", "ear"])
    if i_rid < 0 or i_ear < 0:
        return {}
    result = {}
    while pos < len(out):
        line_pos, rec = _read_next_record(out, pos)
        pos = line_pos
        if not rec.strip():
            continue
        row = _split_row(rec)
        if len(row) <= max(i_rid, i_ear):
            continue
        rid = _norm_guid(row[i_rid])
        if not rid:
            continue
        ear = row[i_ear].strip()
        if ear and rid not in result:
            result[rid] = ear
    return result


def _load_stimulus_table(epwin_path: str, table: str) -> dict[str, str]:
    ok, out, err = _run_capture(["mdb-export", "-d", "\t", epwin_path, table], 240000)
    if not ok:
        return {}
    pos = 0
    line_pos, rec = _read_next_record(out, pos)
    pos = line_pos
    if not rec:
        return {}
    header = _split_row(rec)
    nh = [_norm_header(h) for h in header]
    i_rid = _col(nh, ["recordid"])
    i_stim = _col(nh, ["stimulusname", "stimuluslabel", "stimulus", "stimtypename"])
    if i_rid < 0:
        return {}
    result = {}
    while pos < len(out):
        line_pos, rec = _read_next_record(out, pos)
        pos = line_pos
        if not rec.strip():
            continue
        row = _split_row(rec)
        if len(row) <= max(i_rid, i_stim) if i_stim >= 0 else i_rid:
            continue
        rid = _norm_guid(row[i_rid])
        if not rid:
            continue
        val = row[i_stim].strip() if i_stim >= 0 and len(row) > i_stim else ""
        if val and rid not in result:
            result[rid] = val
    return result


def _load_stim_rate(epwin_path: str, table: str) -> dict[str, str]:
    ok, out, err = _run_capture(["mdb-export", "-d", "\t", epwin_path, table], 240000)
    if not ok:
        return {}
    pos = 0
    line_pos, rec = _read_next_record(out, pos)
    pos = line_pos
    if not rec:
        return {}
    header = _split_row(rec)
    nh = [_norm_header(h) for h in header]
    i_rid = _col(nh, ["recordid"])
    i_rate = _col(nh, ["stimrate", "stimulationrate", "repetitionrate", "rate"])
    if i_rid < 0 or i_rate < 0:
        return {}
    result = {}
    while pos < len(out):
        line_pos, rec = _read_next_record(out, pos)
        pos = line_pos
        if not rec.strip():
            continue
        row = _split_row(rec)
        if len(row) <= max(i_rid, i_rate):
            continue
        rid = _norm_guid(row[i_rid])
        if not rid:
            continue
        val = row[i_rate].strip()
        if val and rid not in result:
            result[rid] = val
    return result


def _load_insert_delay_ms(epwin_path: str, table: str) -> dict[str, float]:
    ok, out, err = _run_capture(["mdb-export", "-d", "\t", epwin_path, table], 240000)
    if not ok:
        return {}
    pos = 0
    line_pos, rec = _read_next_record(out, pos)
    pos = line_pos
    if not rec:
        return {}
    header = _split_row(rec)
    nh = [_norm_header(h) for h in header]
    i_rid = _col(nh, ["recordid"])
    i_delay = _col(nh, ["insertdelay", "insertdelayms", "tubedelay", "delay"])
    if i_rid < 0 or i_delay < 0:
        return {}
    result = {}
    while pos < len(out):
        line_pos, rec = _read_next_record(out, pos)
        pos = line_pos
        if not rec.strip():
            continue
        row = _split_row(rec)
        if len(row) <= max(i_rid, i_delay):
            continue
        rid = _norm_guid(row[i_rid])
        if not rid:
            continue
        try:
            v = _to_double(row[i_delay], 0.0)
            if v != 0.0 and rid not in result:
                result[rid] = v
        except Exception:
            pass
    return result


def _load_stim_intensity(epwin_path: str, table: str) -> dict[str, str]:
    ok, out, err = _run_capture(["mdb-export", "-d", "\t", epwin_path, table], 240000)
    if not ok:
        return {}
    pos = 0
    line_pos, rec = _read_next_record(out, pos)
    pos = line_pos
    if not rec:
        return {}
    header = _split_row(rec)
    nh = [_norm_header(h) for h in header]
    i_rid = _col(nh, ["recordid"])
    i_int = _col(nh, ["stimintensity", "intensity", "intensitydb", "stimdb", "stimulusintensity", "stimulationintensity"])
    if i_rid < 0 or i_int < 0:
        return {}
    result = {}
    while pos < len(out):
        line_pos, rec = _read_next_record(out, pos)
        pos = line_pos
        if not rec.strip():
            continue
        row = _split_row(rec)
        if len(row) <= max(i_rid, i_int):
            continue
        rid = _norm_guid(row[i_rid])
        if not rid:
            continue
        val = row[i_int].strip()
        if val and rid not in result:
            result[rid] = val
    return result


def _normalize_ear(s: str) -> str:
    t = s.strip().lower()
    if t == "1" or t == "l":
        return "Left"
    if t == "2" or t == "r":
        return "Right"
    return s.strip()


# ---------------------------------------------------------------------------
# Load principal
# ---------------------------------------------------------------------------


def load(epwin_mdb_path: str, bl_patients_mdb_path: str) -> LoadResult:
    res = LoadResult()
    res.epwin_path = epwin_mdb_path
    res.blpatients_path = bl_patients_mdb_path

    if not os.path.isfile(epwin_mdb_path):
        res.error = "EPWinData.mdb não encontrado."
        return res
    if not os.path.isfile(bl_patients_mdb_path):
        res.error = "BLPatients.mdb não encontrado."
        return res

    # Listar tabelas EPWin
    ok, out, err = _run_capture(["mdb-tables", epwin_mdb_path], 60000)
    if not ok:
        res.error = err or "Falha ao listar tabelas"
        return res
    res.epwin_tables = re.split(r"\s+", out.strip())

    dem_map, dem_err = _load_bl_patients(bl_patients_mdb_path)
    if dem_err and not dem_map:
        res.error = dem_err
        return res

    ep_map, ep_meta_by_key, _ = _load_ep_data(epwin_mdb_path)
    res.ep_meta_by_key = ep_meta_by_key
    res.ep_data_dc_offset_counts_by_key = {
        k: v.dc_offset_counts for k, v in ep_meta_by_key.items() if v.has_dc_offset_counts
    }
    res.chan_banks_by_record_id = _load_ep_chan_banks(epwin_mdb_path)
    amp_cal = _load_amplifier_calibration(epwin_mdb_path)

    ear_by_rid = {}
    type_by_rid = {}
    stimulus_by_rid = {}
    stim_rate_by_rid = {}
    stim_intensity_by_rid = {}
    insert_delay_by_rid = {}
    for t in STIM_TABLES:
        if t not in res.epwin_tables:
            continue
        ear_map = _load_stim_ear(epwin_mdb_path, t)
        for rid, ear in ear_map.items():
            if rid not in ear_by_rid:
                ear_by_rid[rid] = ear
        stim_map = _load_stimulus_table(epwin_mdb_path, t)
        for rid, val in stim_map.items():
            if rid not in stimulus_by_rid:
                stimulus_by_rid[rid] = val
        rate_map = _load_stim_rate(epwin_mdb_path, t)
        for rid, val in rate_map.items():
            if rid not in stim_rate_by_rid:
                stim_rate_by_rid[rid] = val
        tname = TYPE_NAMES.get(t, t)
        for rid in ear_map:
            if rid not in type_by_rid:
                type_by_rid[rid] = tname
    # Insert delay e intensidade (qualquer tabela que tenha)
    for t in STIM_TABLES:
        if t not in res.epwin_tables:
            continue
        delay_map = _load_insert_delay_ms(epwin_mdb_path, t)
        for rid, val in delay_map.items():
            if rid not in insert_delay_by_rid:
                insert_delay_by_rid[rid] = val
        int_map = _load_stim_intensity(epwin_mdb_path, t)
        for rid, val in int_map.items():
            if rid not in stim_intensity_by_rid:
                stim_intensity_by_rid[rid] = val
    # Records com --bin=hex
    ok, rec_text, err = _run_capture(
        ["mdb-export", "-d", "\t", "-e", "--bin=hex", epwin_mdb_path, "Records"],
        300000,
    )
    if not ok:
        res.error = err or "Falha ao exportar Records (hex)"
        return res

    pos = 0
    line_pos, line = _read_next_record(rec_text, pos)
    pos = line_pos
    if not line:
        res.error = "Records export vazio"
        return res
    header = _split_row(line)
    nh = [_norm_header(h) for h in header]
    i_blsc = _col(nh, ["blscid"])
    i_test = _col(nh, ["testid"])
    i_rid = _col(nh, ["recordid"])
    i_type = _col(nh, ["testtype"])
    i_start = _col(nh, ["starttime"])
    i_stop = _col(nh, ["stoptime"])
    i_com = _col(nh, ["comments"])
    i_ch = _col(nh, ["numberofchannels"])
    i_epoch = _col(nh, ["epochtime"])
    i_pts = _col(nh, ["numberofpoints"])
    i_pre = _col(nh, ["prepostpoints"])
    i_blk = _col(nh, ["blockedpoints"])
    i_ad_bits = _col(nh, ["adbits"])
    i_data = _col(nh, ["data"])
    if i_blsc < 0 or i_rid < 0 or i_data < 0:
        res.error = "Records sem colunas BLSCID/RecordID/Data"
        return res

    p_index = {}

    def get_patient(blsc: str) -> PatientInfo:
        if blsc in p_index:
            return res.patients[p_index[blsc]]
        p = PatientInfo(blsc_id=blsc)
        if blsc in dem_map:
            d = dem_map[blsc]
            p.patient_id = d.get("patient_id", "")
            p.first_name = d.get("first", "")
            p.last_name = d.get("last", "")
            p.sex = d.get("sex", "")
            b = d.get("birth")
            if b is not None:
                p.birthdate = b
        res.patients.append(p)
        p_index[blsc] = len(res.patients) - 1
        return res.patients[-1]

    def get_session(p: PatientInfo, d: Optional[date]) -> SessionInfo:
        for s in p.sessions:
            if s.session_date == d:
                return s
        s = SessionInfo(session_date=d)
        p.sessions.append(s)
        return p.sessions[-1]

    while pos < len(rec_text):
        line_pos, line = _read_next_record(rec_text, pos)
        pos = line_pos
        if not line.strip():
            continue
        row = _split_row(line)
        if len(row) <= i_data:
            continue
        blsc = _norm_guid(row[i_blsc])
        rid = _norm_guid(row[i_rid])
        if not blsc or not rid:
            continue
        ex = ExamInfo(
            blsc_id=blsc,
            record_id=rid,
            test_id=row[i_test].strip() if i_test >= 0 and len(row) > i_test else "",
            test_type=_to_int(row[i_type], -1) if i_type >= 0 else -1,
            start=_parse_datetime(row[i_start]) if i_start >= 0 and len(row) > i_start else None,
            stop=_parse_datetime(row[i_stop]) if i_stop >= 0 and len(row) > i_stop else None,
            comments=row[i_com].strip() if i_com >= 0 and len(row) > i_com else "",
            channels=_to_int(row[i_ch], 0) if i_ch >= 0 else 0,
            epoch_ms=_to_double(row[i_epoch], 0.0) if i_epoch >= 0 else 0.0,
            points=_to_int(row[i_pts], 0) if i_pts >= 0 else 0,
            pre_post_points=_to_int(row[i_pre], 0) if i_pre >= 0 else 0,
            blocked_points=_to_int(row[i_blk], 0) if i_blk >= 0 else 0,
            ad_bits=_to_int(row[i_ad_bits], 16) if i_ad_bits >= 0 else 16,
            data_hex=row[i_data].strip(),
        )
        cal = amp_cal.get(rid, {})
        if cal:
            if cal.get("uv_per_count", 0) > 0:
                ex.u_v_per_count = cal["uv_per_count"]
            elif cal.get("amplifier_gain", 0) > 0 and ex.ad_bits > 0:
                base = _default_uv_per_count_from_ad_bits(ex.ad_bits)
                v = base * (5000.0 / cal["amplifier_gain"])
                if 0 < v < 100:
                    ex.u_v_per_count = v
            elif cal.get("full_scale_uV", 0) > 0 and 0 < ex.ad_bits < 40:
                denom = 2.0 ** (ex.ad_bits - 1)
                v = cal["full_scale_uV"] / denom if denom > 0 else 0
                if 0 < v < 100:
                    ex.u_v_per_count = v
        ep_first = ep_map.get(rid, {})
        ex.channel_number = ep_first.get("ch", 0)
        ex.bank_number = ep_first.get("bk", 0)
        ex.averages = ep_first.get("avg", "")
        ex.rejected = ep_first.get("rej", "")
        ex.low_analysis_filter = ep_first.get("low", "")
        ex.high_analysis_filter = ep_first.get("high", "")
        ex.ear = _normalize_ear(ear_by_rid.get(rid, ""))
        ex.test_type_name = type_by_rid.get(rid) or TEST_TYPE_MAP.get(ex.test_type) or (str(ex.test_type) if ex.test_type >= 0 else "")
        ex.stimulus = stimulus_by_rid.get(rid, "")
        ex.stim_rate = stim_rate_by_rid.get(rid, "")
        ex.insert_delay_ms = insert_delay_by_rid.get(rid, 0.0)
        p = get_patient(blsc)
        if ex.start and (p.last_test is None or ex.start > p.last_test):
            p.last_test = ex.start
        sd = ex.start.date() if ex.start else None
        sess = get_session(p, sd)
        if ex.start and (sess.first_start is None or ex.start < sess.first_start):
            sess.first_start = ex.start
        sess.exams.append(ex)

    res.patients.sort(key=lambda a: (a.patient_id or a.blsc_id))
    for p in res.patients:
        p.sessions.sort(key=lambda s: (s.session_date or date.min, s.first_start or datetime.min))
        for s in p.sessions:
            s.exams.sort(
                key=lambda e: (
                    e.start or datetime.min,
                    e.bank_number,
                    e.record_id,
                )
            )
    return res
