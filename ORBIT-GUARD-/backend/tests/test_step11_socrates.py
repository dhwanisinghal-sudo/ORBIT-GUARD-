"""
Step 11: SOCRATES validation script. Offline: the CSV below is a made-up fixture in the documented
SOCRATES layout (real data has to be downloaded on a machine that can reach CelesTrak), and TLE
lookups are faked. These tests check the script's mechanics, not what SOCRATES says.
"""
import csv
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ml_risk
import orbit_engine as engine
import validate_socrates as vs
from tle_factory import ISS_LINE1, _checksum, make_tle

HEADER = ("NORAD_CAT_ID_1,OBJECT_NAME_1,DSE_1,NORAD_CAT_ID_2,OBJECT_NAME_2,DSE_2,"
          "TCA,TCA_RANGE,TCA_RELATIVE_SPEED,MAX_PROB,DILUTION")


def line(i, rng, spd, pc, tca="2026 Oct 18 12:34:56.789"):
    return f"{40000 + i},SAT-A{i} [+],1.5,{50000 + i},DEBRIS-B{i} [-],2.5,{tca},{rng},{spd},{pc},0.5"


def write_csv(path, rows, header=HEADER):
    Path(path).write_text("\n".join([header, *rows]) + "\n")
    return path


def synthetic_rows(n=60, seed=3):
    """Closer and faster -> higher probability, plus noise, so the three reference classes all occur."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        dist = float(rng.uniform(0.05, 4.9))
        spd = float(rng.uniform(0.5, 14.0))
        log_pc = -2.0 - 1.2 * dist + 0.08 * spd + rng.normal(0, 0.4) - 1.0
        out.append(line(i, f"{dist:.3f}", f"{spd:.3f}", f"{10 ** log_pc:.3e}"))
    return out


@pytest.fixture(scope="module", autouse=True)
def model_ready():
    ml_risk.warm_up()


# ======================= reading the file =======================
def test_loads_documented_columns_and_scales_units(tmp_path):
    f = write_csv(tmp_path / "s.csv", [line(1, 1.5, 12.0, "1.0e-4"), line(2, 2500, 9000, "3.0e-6")])
    rows, dropped = vs.load_socrates_csv(f)
    assert len(rows) == 2 and not dropped
    assert rows[0]["range_km"] == 1.5 and rows[0]["speed_km_s"] == 12.0 and rows[0]["max_prob"] == 1e-4
    assert rows[0]["norad_1"] == 40001 and rows[0]["norad_2"] == 50001 and rows[0]["name_1"] == "SAT-A1 [+]"
    assert rows[0]["tca"] == datetime(2026, 10, 18, 12, 34, 56, 789000, tzinfo=timezone.utc)
    metres, _ = vs.load_socrates_csv(f, range_unit="m", speed_unit="m/s")
    assert metres[1]["range_km"] == pytest.approx(2.5) and metres[1]["speed_km_s"] == pytest.approx(9.0)


def test_header_is_case_and_space_insensitive(tmp_path):
    header = "norad_cat_id_1, tca_range , TCA_RELATIVE_SPEED,Max_Prob"
    f = write_csv(tmp_path / "s.csv", ["1,2.0,7.5,1e-5"], header=header)
    rows, _ = vs.load_socrates_csv(f)
    assert rows[0]["range_km"] == 2.0 and rows[0]["tca"] is None and rows[0]["norad_2"] is None


def test_unusable_rows_are_dropped_and_counted(tmp_path):
    f = write_csv(tmp_path / "s.csv", [
        line(1, 1.0, 10, "1e-4"),
        line(2, "abc", 10, "1e-4"),            # unreadable number
        line(3, 1.0, 10, "0"),                 # no probability to compare with
        line(4, -1.0, 10, "1e-4"),             # negative range
        line(5, 1.0, 10, "nan"),               # not finite
    ])
    rows, dropped = vs.load_socrates_csv(f)
    assert len(rows) == 1
    assert dropped == {"unreadable number": 2, "MAX_PROB is zero or negative": 1, "negative range or speed": 1}


def test_missing_columns_give_a_clear_error(tmp_path):
    f = write_csv(tmp_path / "s.csv", ["1,2,3"], header="A,B,C")
    with pytest.raises(SystemExit, match="TCA_RANGE.*legacy"):
        vs.load_socrates_csv(f)


@pytest.mark.parametrize("text,ok", [("2026-10-18T12:00:00.5Z", True), ("2026-10-18 12:00:00", True),
                                     ("2026 Oct 18 12:00:00", True), ("18/10/2026 noon", False), ("", False)])
def test_tca_formats(text, ok):
    assert (vs.parse_tca(text) is not None) is ok


def test_unit_sanity_warnings():
    metres = [{"range_km": 2500.0, "speed_km_s": 9.0}] * 3
    assert any("--range-unit m" in w for w in vs.check_units(metres))
    fast = [{"range_km": 2.0, "speed_km_s": 9000.0}]
    assert any("--speed-unit m/s" in w for w in vs.check_units(fast))
    assert vs.check_units([{"range_km": 2.0, "speed_km_s": 9.0}]) == []


# ======================= reference labels =======================
def test_reference_label_thresholds():
    assert vs.reference_label(1e-4, 1e-4, 1e-5) == 2
    assert vs.reference_label(9.99e-5, 1e-4, 1e-5) == 1
    assert vs.reference_label(1e-5, 1e-4, 1e-5) == 1
    assert vs.reference_label(9e-6, 1e-4, 1e-5) == 0


# ======================= altitudes =======================
def fresh_tle(norad, mean_motion=15.5):
    now = datetime.now(timezone.utc)
    doy = now.timetuple().tm_yday + (now.hour * 3600 + now.minute * 60 + now.second) / 86400
    l1 = ISS_LINE1[:18] + f"{now.year % 100:02d}{doy:012.8f}" + ISS_LINE1[32:68]
    base = make_tle(norad, f"S{norad}", 51.6, 10.0, 20.0, mean_motion=mean_motion)
    l1 = f"1 {norad:05d}" + l1[7:68]
    return {**base, "line1": l1 + str(_checksum(l1))}


def row(norad_1, norad_2, tca):
    return {"norad_1": norad_1, "norad_2": norad_2, "name_1": "", "name_2": "", "tca": tca,
            "range_km": 1.0, "speed_km_s": 10.0, "max_prob": 1e-4}


def test_altitudes_come_from_tles_propagated_to_the_tca():
    tca = datetime.now(timezone.utc) + timedelta(days=2)
    tles = {101: fresh_tle(101, 15.5), 102: fresh_tle(102, 14.0)}
    out = vs.estimate_altitudes([row(101, 102, tca)], fetch_fn=lambda n: tles[n])
    expected = [engine.propagate(tles[n], tca)["altitude_km"] for n in (101, 102)]
    assert out[0]["source"] == "tle_at_tca"
    assert out[0]["object_1"] == pytest.approx(expected[0]) and out[0]["object_2"] == pytest.approx(expected[1])
    assert out[0]["object_2"] > out[0]["object_1"]          # the slower orbit is higher


def test_altitude_falls_back_when_a_tle_is_missing_or_ids_are_absent():
    tca = datetime.now(timezone.utc) + timedelta(days=1)

    def fetch(n):
        if n == 202:
            raise engine.TLENotFound("gone")
        return fresh_tle(n)

    out = vs.estimate_altitudes([row(201, 202, tca), row(None, None, tca), row(201, 203, None)], fetch_fn=fetch)
    assert [o["source"] for o in out] == ["fallback", "fallback", "tle_at_now"]
    assert out[0]["object_1"] is None


# ======================= evaluation =======================
def test_clear_cases_agree_with_the_reference():
    rows = [row(1, 2, None) | {"range_km": 0.1, "speed_km_s": 12.0, "max_prob": 1e-3},
            row(3, 4, None) | {"range_km": 2.5, "speed_km_s": 5.0, "max_prob": 5e-5},
            row(5, 6, None) | {"range_km": 4.9, "speed_km_s": 3.0, "max_prob": 1e-9}]
    alts = [{"object_1": 800.0, "object_2": 800.0, "source": "tle_at_tca"}] * 3
    rep = vs.evaluate(rows, alts)
    assert rep["reference_class_counts"] == {"LOW": 1, "MEDIUM": 1, "HIGH": 1}
    assert rep["ml_model"]["accuracy"] == 1.0
    assert rep["rank_correlation_with_log10_max_prob"]["ml_score"]["rho"] == pytest.approx(1.0)
    assert rep["auc"]["ml_score_high_vs_rest"] == 1.0
    assert any("Only 3 conjunctions" in n for n in rep["notes"])
    json.dumps(rep)                                          # the whole report must be JSON-serialisable


def test_single_reference_class_is_called_out_and_auc_is_none():
    rows = [row(1, 2, None) | {"range_km": d, "max_prob": 1e-9} for d in (0.5, 1.0, 2.0, 3.0)]
    alts = [{"object_1": None, "object_2": None, "source": "fallback"}] * 4
    rep = vs.evaluate(rows, alts)
    assert rep["auc"]["ml_score_high_vs_rest"] is None and rep["auc"]["ml_score_medium_or_high_vs_low"] is None
    assert any("one reference class" in n for n in rep["notes"])
    assert any("4 of 4 rows used the 500 km altitude fallback" in n for n in rep["notes"])


def test_constant_inputs_do_not_crash_the_correlation():
    rows = [row(1, 2, None) | {"range_km": 1.0, "speed_km_s": 10.0, "max_prob": 1e-4}] * 5
    alts = [{"object_1": 700.0, "object_2": 700.0, "source": "tle_at_tca"}] * 5
    rep = vs.evaluate(rows, alts)
    assert rep["rank_correlation_with_log10_max_prob"]["ml_score"] is None


def test_baseline_comparison_note_names_the_winner(tmp_path):
    rows, _ = vs.load_socrates_csv(write_csv(tmp_path / "s.csv", synthetic_rows()))
    alts = [{"object_1": 700.0, "object_2": 720.0, "source": "tle_at_tca"}] * len(rows)
    rep = vs.evaluate(rows, alts)
    assert rep["n_rows"] == 60
    assert any("miss distance alone" in n for n in rep["notes"])
    assert math.isclose(sum(v["count"] for v in rep["max_prob_by_predicted_ml_level"].values()), 60)


# ======================= command line =======================
def test_cli_end_to_end_offline(tmp_path, capsys):
    f = write_csv(tmp_path / "s.csv", synthetic_rows())
    out, rows_out = tmp_path / "report.json", tmp_path / "rows.csv"
    assert vs.main([str(f), "--no-tle-lookup", "--out", str(out), "--rows-out", str(rows_out)]) == 0
    text = capsys.readouterr().out
    assert "SOCRATES check on 60 conjunctions" in text and "Caveats:" in text
    rep = json.loads(out.read_text())
    assert rep["n_rows"] == 60 and rep["altitude_source_counts"] == {"fallback": 60}
    assert rep["model_training_labels"].startswith("synthetic")
    lines = list(csv.reader(rows_out.open()))
    assert len(lines) == 61 and lines[0][:3] == ["norad_1", "norad_2", "tca_utc"]
    assert {r[10] for r in lines[1:]} <= {"LOW", "MEDIUM", "HIGH"} and {r[6] for r in lines[1:]} <= {"LOW", "MEDIUM", "HIGH"}


def test_cli_rejects_inconsistent_thresholds(tmp_path):
    f = write_csv(tmp_path / "s.csv", synthetic_rows(5))
    with pytest.raises(SystemExit) as e:
        vs.main([str(f), "--no-tle-lookup", "--high-pc", "1e-6", "--medium-pc", "1e-4"])
    assert e.value.code == 2


def test_cli_warns_about_metres_and_reports_dropped_rows(tmp_path, capsys):
    rows = [line(i, 2500 + i, 9.0, "1e-5") for i in range(4)] + [line(9, "x", 9.0, "1e-5")]
    f = write_csv(tmp_path / "s.csv", rows)
    assert vs.main([str(f), "--no-tle-lookup"]) == 0
    err = capsys.readouterr().err
    assert "--range-unit m" in err and "unreadable number" in err


def test_cli_with_no_usable_rows_exits_with_a_message(tmp_path):
    f = write_csv(tmp_path / "s.csv", [line(1, "x", 1, "1e-5")])
    with pytest.raises(SystemExit, match="No usable rows"):
        vs.main([str(f), "--no-tle-lookup"])
