import csv
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import tempfile
import unittest

from flowprep import (Parameters, RESULT_FIELDS, analyse_results, case_id,
                      load_parameters, prepare, profile, reference, validate,
                      vertices, write_json)


class GeometryTests(unittest.TestCase):
    def test_defaults(self):
        validate(Parameters())

    def test_horizontal_rectangle(self):
        p = replace(Parameters(), angle_deg=0)
        vv = vertices(p)
        self.assertAlmostEqual(max(x for x, _ in vv)-min(x for x, _ in vv), p.chord_m)
        self.assertAlmostEqual(max(y for _, y in vv)-min(y for _, y in vv), p.thickness_m)

    def test_rotated_area(self):
        p = Parameters()
        vv = vertices(p)
        area = abs(sum(vv[i][0]*vv[(i+1)%4][1]-vv[(i+1)%4][0]*vv[i][1] for i in range(4)))/2
        self.assertAlmostEqual(area, p.chord_m*p.thickness_m, places=12)

    def test_wall_intersection(self):
        with self.assertRaises(ValueError):
            validate(replace(Parameters(), center_y_m=0.001))

    def test_negative_or_nonfinite(self):
        for key, value in [("viscosity_pa_s", -1), ("density_kg_m3", 0),
                           ("angle_deg", float("nan")), ("length_m", float("inf")),
                           ("mean_velocity_m_s", True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(replace(Parameters(), **{key: value}))

    def test_probe_upstream(self):
        with self.assertRaises(ValueError):
            validate(replace(Parameters(), probe_x_m=0.10))

    def test_thickness(self):
        with self.assertRaises(ValueError):
            validate(replace(Parameters(), thickness_m=0.03))

    def test_id_changes_with_geometry(self):
        p = Parameters()
        self.assertNotEqual(case_id(p), case_id(replace(p, angle_deg=31)))
        self.assertEqual(case_id(p), case_id(Parameters()))

    def test_numeric_representation_keeps_same_id(self):
        p = Parameters()
        self.assertEqual(case_id(p), case_id(replace(p, angle_deg=30)))


class ReferenceTests(unittest.TestCase):
    def test_values(self):
        r = reference(Parameters())
        self.assertAlmostEqual(r["pressure_drop_pa"], 0.00543)
        self.assertAlmostEqual(r["reynolds"], 532.1546961325967)
        self.assertAlmostEqual(r["max_velocity_m_s"], 0.15)
        self.assertAlmostEqual(r["mass_flow_per_unit_span_kg_s_m"], 0.004816)

    def test_wall_boundary_and_symmetry(self):
        data = profile(Parameters())
        self.assertEqual(data[0][1], 0)
        self.assertEqual(data[-1][1], 0)
        for (_, u), (_, v) in zip(data, reversed(data)):
            self.assertAlmostEqual(u, v)

    def test_integrated_flow(self):
        p = Parameters()
        data = profile(p, 1000)
        q = sum((y1-y0)*(u0+u1)/2 for (y0, u0), (y1, u1) in zip(data, data[1:]))
        self.assertLess(abs(q-p.mean_velocity_m_s*p.height_m)/(p.mean_velocity_m_s*p.height_m), 2e-6)

    def test_pressure_gradient_equation(self):
        p = Parameters()
        data = profile(p, 100)
        dy = data[1][0]-data[0][0]
        second_derivative = (data[51][1]-2*data[50][1]+data[49][1])/dy**2
        self.assertAlmostEqual(p.viscosity_pa_s*second_derivative,
                               -reference(p)["pressure_drop_pa"]/p.length_m, places=9)

    def test_pressure_scales_with_viscosity(self):
        p = Parameters()
        self.assertAlmostEqual(reference(replace(p, viscosity_pa_s=2*p.viscosity_pa_s))["pressure_drop_pa"],
                               2*reference(p)["pressure_drop_pa"])

    def test_reference_independent_of_baffle_angle(self):
        p = Parameters()
        self.assertEqual(reference(p), reference(replace(p, angle_deg=60)))
        self.assertFalse(reference(p)["baffle_flow_computed"])

    def test_invalid_profile_resolution(self):
        with self.assertRaises(ValueError):
            profile(Parameters(), 1)


class ExportTests(unittest.TestCase):
    def test_config_roundtrip_and_unknown_field(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"settings.json"
            write_json(path, asdict(Parameters()))
            self.assertEqual(load_parameters(path), Parameters())
            write_json(path, {"unexpected": 1})
            with self.assertRaises(ValueError):
                load_parameters(path)

    def test_series_and_blank_results(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            r = prepare(Parameters(), out)
            self.assertEqual(r["prepared"], 15)
            self.assertEqual(r["rejected"], 0)
            manifest = json.loads((out/"manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len({c["case_id"] for c in manifest["cases"]}), 15)
            report = analyse_results(out/"ansys_results_template.csv", out/"manifest.json")
            self.assertEqual(report["accepted"], [])
            self.assertEqual(len(report["rejected"]), 15)
            self.assertIsNone(report["best_available_case"])

    def test_reject_geometry_in_series(self):
        with tempfile.TemporaryDirectory() as folder:
            r = prepare(Parameters(), Path(folder), angles=[90], chords=[0.1])
            self.assertEqual(r["prepared"], 0)
            self.assertEqual(r["rejected"], 1)

    def test_duplicate_grid(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            prepare(Parameters(), Path(folder), angles=[30, 30])


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name)
        prepare(Parameters(), self.out, angles=[30], chords=[0.02])
        self.cid = case_id(Parameters())
        self.row = dict(zip(RESULT_FIELDS, [self.cid, "true", "0.004816", "0.004816",
                        "0.001", str(0.001*math.tan(math.radians(20))),
                        "0.1", "0.03", "12000", "TEST_FIXTURE"]))

    def tearDown(self):
        self.temp.cleanup()

    def analyse(self, rows=None):
        path = self.out/"test_results.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
            writer.writeheader()
            writer.writerows(rows if rows is not None else [self.row])
        return analyse_results(path, self.out/"manifest.json")

    def test_angle_and_pressure_from_fixture(self):
        r = self.analyse()
        self.assertAlmostEqual(r["accepted"][0]["angle_deg"], 20)
        self.assertAlmostEqual(r["accepted"][0]["pressure_loss_pa"], 0.07)
        self.assertEqual(r["best_available_case"], self.cid)

    def test_mass_imbalance(self):
        self.row["mass_out_kg_s_m"] = "0.004"
        self.assertEqual(len(self.analyse()["rejected"]), 1)

    def test_wrong_inlet_flow(self):
        self.row["mass_in_kg_s_m"] = self.row["mass_out_kg_s_m"] = "0.009632"
        self.assertEqual(len(self.analyse()["rejected"]), 1)

    def test_no_convergence(self):
        self.row["converged"] = "false"
        self.assertEqual(len(self.analyse()["rejected"]), 1)

    def test_nan(self):
        self.row["momentum_y_n_m"] = "nan"
        self.assertEqual(len(self.analyse()["rejected"]), 1)

    def test_unknown_id(self):
        self.row["case_id"] = "other"
        with self.assertRaises(ValueError):
            self.analyse()

    def test_duplicate_id(self):
        with self.assertRaises(ValueError):
            self.analyse([self.row, self.row])

    def test_negative_loss(self):
        self.row["total_pressure_out_pa"] = "0.2"
        self.assertEqual(len(self.analyse()["rejected"]), 1)

    def test_target_not_met(self):
        self.row["momentum_y_n_m"] = "0"
        self.assertIsNone(self.analyse()["best_available_case"])

    def test_missing_cases(self):
        self.assertEqual(self.analyse([])["missing_case_ids"], [self.cid])


if __name__ == "__main__":
    unittest.main()
