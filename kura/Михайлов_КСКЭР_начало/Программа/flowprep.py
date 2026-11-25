"""Подготовка параметрического исследования заслонки. Python 3.10+, stdlib."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

VERSION = "0.1.0"


@dataclass(frozen=True)
class Parameters:
    """Все размерные параметры заданы в СИ. Значения по умолчанию — пример."""
    length_m: float = 0.4
    height_m: float = 0.04
    center_x_m: float = 0.14
    center_y_m: float = 0.02
    chord_m: float = 0.02
    thickness_m: float = 0.001
    angle_deg: float = 30.0
    mean_velocity_m_s: float = 0.1
    density_kg_m3: float = 1.204
    viscosity_pa_s: float = 1.81e-5
    minimum_gap_m: float = 0.002
    probe_x_m: float = 0.20
    target_angle_deg: float = 20.0
    angle_tolerance_deg: float = 5.0
    mass_tolerance: float = 0.001


def vertices(p: Parameters) -> list[tuple[float, float]]:
    a = math.radians(p.angle_deg)
    ex, ey = math.cos(a), math.sin(a)
    nx, ny = -ey, ex
    return [
        (p.center_x_m + s * p.chord_m / 2 * ex + t * p.thickness_m / 2 * nx,
         p.center_y_m + s * p.chord_m / 2 * ey + t * p.thickness_m / 2 * ny)
        for s, t in [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    ]


def validate(p: Parameters) -> None:
    for name, value in asdict(p).items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name}: требуется конечное число")
    positive = ("length_m", "height_m", "chord_m", "thickness_m",
                "mean_velocity_m_s", "density_kg_m3", "viscosity_pa_s",
                "minimum_gap_m", "angle_tolerance_deg", "mass_tolerance")
    for name in positive:
        if getattr(p, name) <= 0:
            raise ValueError(f"{name}: значение должно быть положительным")
    if p.thickness_m >= p.chord_m:
        raise ValueError("Толщина должна быть меньше длины заслонки")
    if not -90 <= p.angle_deg <= 90:
        raise ValueError("Угол заслонки должен лежать в диапазоне от −90 до 90 градусов")
    if not -89 < p.target_angle_deg < 89:
        raise ValueError("Целевой угол должен лежать внутри диапазона (−89; 89)")
    if p.mass_tolerance >= 1:
        raise ValueError("Допуск баланса массы должен быть меньше единицы")
    if p.angle_tolerance_deg >= 90:
        raise ValueError("Допуск угла должен быть меньше 90 градусов")
    vv = vertices(p)
    xmin, xmax = min(x for x, _ in vv), max(x for x, _ in vv)
    ymin, ymax = min(y for _, y in vv), max(y for _, y in vv)
    gaps = (xmin, p.length_m - xmax, ymin, p.height_m - ymax)
    if min(gaps) < p.minimum_gap_m - 1e-12:
        raise ValueError("Заслонка пересекает стенку или нарушает минимальный зазор")
    if not xmax < p.probe_x_m < p.length_m:
        raise ValueError("Контрольное сечение должно находиться за заслонкой и перед выходом")


def load_parameters(path: Path) -> Parameters:
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("Настройки должны быть объектом JSON")
    unknown = set(obj) - set(Parameters.__dataclass_fields__)
    if unknown:
        raise ValueError("Неизвестные параметры: " + ", ".join(sorted(unknown)))
    p = Parameters(**obj)
    validate(p)
    return p


def reference(p: Parameters) -> dict:
    """Точное решение для пустого плоского канала с развитым течением."""
    validate(p)
    h, u, mu, rho, length = (p.height_m, p.mean_velocity_m_s,
                             p.viscosity_pa_s, p.density_kg_m3, p.length_m)
    re = rho * u * (2 * h) / mu
    return {
        "model": "plane_poiseuille_empty_channel",
        "baffle_flow_computed": False,
        "hydraulic_diameter_m": 2 * h,
        "reynolds": re,
        "max_velocity_m_s": 1.5 * u,
        "flow_per_unit_span_m2_s": u * h,
        "mass_flow_per_unit_span_kg_s_m": rho * u * h,
        "pressure_drop_pa": 12 * mu * u * length / h**2,
        "wall_shear_pa": 6 * mu * u / h,
        "darcy_friction_factor": 96 / re,
        "approx_entrance_length_m": 0.05 * re * (2 * h),
        "warnings": (["Re >= 2000: ламинарный режим требует отдельного обоснования"]
                     if re >= 2000 else []),
    }


def profile(p: Parameters, intervals: int = 100) -> list[tuple[float, float]]:
    validate(p)
    if isinstance(intervals, bool) or not isinstance(intervals, int) or not 2 <= intervals <= 100000:
        raise ValueError("Число интервалов должно быть целым от 2 до 100000")
    return [(p.height_m * i / intervals,
             6 * p.mean_velocity_m_s * (i / intervals) * (1 - i / intervals))
            for i in range(intervals + 1)]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def svg_geometry(p: Parameters) -> str:
    validate(p)
    scale = 2100
    width, height = p.length_m * scale, p.height_m * scale
    pts = " ".join(f"{60+x*scale:.3f},{75+(p.height_m-y)*scale:.3f}" for x, y in vertices(p))
    probe = 60 + p.probe_x_m * scale
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="300" viewBox="0 0 1000 300">
<rect width="1000" height="300" fill="white"/>
<g font-family="Arial" font-size="16" fill="#15263b">
<text x="60" y="30">Параметрическая схема канала и заслонки</text>
<svg x="0" y="35" width="1000" height="180" viewBox="0 0 {max(1000, width+120)} {max(180, height+100)}">
<rect x="60" y="75" width="{width}" height="{height}" fill="#edf5fc" stroke="#202d3a" stroke-width="2"/>
<polygon points="{pts}" fill="#f5b65b" stroke="#8e5400" stroke-width="2"/>
<path d="M {probe} 75 V {75+height}" stroke="#168678" stroke-dasharray="5 4"/>
<path d="M 12 {75+height/2} H 48 l -9 -5 m 9 5 l -9 5" fill="none" stroke="#1756a1" stroke-width="2"/>
</svg>
<text x="60" y="245">L = {p.length_m:g} м; H = {p.height_m:g} м; c = {p.chord_m:g} м; α = {p.angle_deg:g}°</text>
<text x="60" y="275">Схема геометрии. Поле течения с заслонкой на этом этапе не вычисляется.</text>
</g></svg>'''


def case_id(p: Parameters) -> str:
    canonical = {key: (0.0 if value == 0 else float(value)) for key, value in asdict(p).items()}
    raw = json.dumps(canonical, sort_keys=True, allow_nan=False).encode()
    return "case_" + hashlib.sha256(raw).hexdigest()[:12]


RESULT_FIELDS = [
    "case_id", "converged", "mass_in_kg_s_m", "mass_out_kg_s_m",
    "momentum_x_n_m", "momentum_y_n_m",
    "total_pressure_in_pa", "total_pressure_out_pa", "mesh_cells", "solver",
]


def prepare(base: Parameters, out: Path, angles=(15., 30., 45., 60., 75.),
            chords=(0.012, 0.020, 0.028)) -> dict:
    validate(base)
    angles, chords = list(angles), list(chords)
    if not angles or not chords or len(angles) * len(chords) > 10000:
        raise ValueError("Нужно от 1 до 10000 сочетаний параметров")
    if len(set(angles)) != len(angles) or len(set(chords)) != len(chords):
        raise ValueError("Сетка вариантов содержит повторяющиеся значения")
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "settings.json", asdict(base))
    write_json(out / "reference.json", reference(base))
    (out / "geometry.svg").write_text(svg_geometry(base), encoding="utf-8")
    with (out / "reference_profile.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["y_m", "u_m_s"])
        w.writerows(profile(base))
    cases, rejected = [], []
    for angle in angles:
        for chord in chords:
            p = replace(base, angle_deg=angle, chord_m=chord)
            try:
                validate(p)
            except ValueError as exc:
                rejected.append({"angle_deg": angle, "chord_m": chord, "reason": str(exc)})
                continue
            cid = case_id(p)
            case_dir = out / cid
            case_dir.mkdir(exist_ok=True)
            data = {
                "case_id": cid, "status": "prepared_not_solved",
                "parameters": asdict(p), "vertices_m": vertices(p),
                "boundaries": {
                    "inlet": {"type": "fully_developed_velocity",
                              "ux": "6*Umean*(y/H)*(1-y/H)", "uy": 0},
                    "outlet": {"type": "pressure_outlet", "gauge_pressure_pa": 0},
                    "walls": {"type": "no_slip"},
                    "baffle": {"type": "stationary_no_slip"},
                    "probe_x_m": p.probe_x_m,
                },
                "ansys_execution": "not_implemented_in_this_release",
            }
            write_json(case_dir / "case.json", data)
            (case_dir / "geometry.svg").write_text(svg_geometry(p), encoding="utf-8")
            cases.append({"case_id": cid, "angle_deg": angle, "chord_m": chord,
                          "status": "prepared_not_solved"})
    write_json(out / "manifest.json", {
        "version": VERSION, "created_at": datetime.now().astimezone().isoformat(),
        "parameters": asdict(base), "cases": cases, "rejected": rejected,
        "note": "Расчёты течения с заслонкой и поиск оптимума ещё не выполнены",
    })
    with (out / "cases.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "angle_deg", "chord_m", "status"])
        w.writeheader()
        w.writerows(cases)
    with (out / "ansys_results_template.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writeheader()
        w.writerows({"case_id": c["case_id"]} for c in cases)
    return {"prepared": len(cases), "rejected": len(rejected), "path": str(out.resolve())}


def analyse_results(csv_path: Path, manifest_path: Path) -> dict:
    """Обработка экспортированных пользователем интегральных величин."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    p = Parameters(**manifest["parameters"])
    validate(p)
    known = {item["case_id"] for item in manifest["cases"]}
    if not known:
        raise ValueError("В манифесте отсутствуют подготовленные варианты")
    accepted, rejected, seen = [], [], set()
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if set(RESULT_FIELDS) - set(reader.fieldnames or []):
            raise ValueError("CSV должен содержать столбцы из ansys_results_template.csv")
        for line, row in enumerate(reader, start=2):
            cid = row["case_id"]
            if cid not in known or cid in seen:
                raise ValueError(f"Строка {line}: неизвестный или повторяющийся case_id")
            seen.add(cid)
            try:
                if row["converged"].strip().lower() not in {"1", "true", "yes"}:
                    raise ValueError("сходимость не подтверждена")
                values = {key: float(row[key]) for key in RESULT_FIELDS[2:8]}
                if not all(math.isfinite(x) for x in values.values()):
                    raise ValueError("нечисловое или бесконечное значение")
                mi, mo = values["mass_in_kg_s_m"], values["mass_out_kg_s_m"]
                if mi <= 0 or mo <= 0:
                    raise ValueError("расходы должны быть положительными модулями")
                balance = abs(mi - mo) / max(mi, mo)
                if balance > p.mass_tolerance:
                    raise ValueError("нарушен баланс массы")
                expected = reference(p)["mass_flow_per_unit_span_kg_s_m"]
                if abs(mi - expected) / expected > p.mass_tolerance:
                    raise ValueError("входной расход отличается от заданного")
                mx, my = values["momentum_x_n_m"], values["momentum_y_n_m"]
                if mx <= 0:
                    raise ValueError("продольный поток импульса должен быть положительным")
                dp = values["total_pressure_in_pa"] - values["total_pressure_out_pa"]
                if dp < 0:
                    raise ValueError("отрицательная потеря полного давления")
                cells = int(row["mesh_cells"])
                if cells <= 0 or not row["solver"].strip():
                    raise ValueError("нужны число ячеек и название решателя")
                theta = math.degrees(math.atan2(my, mx))
                error = abs(theta - p.target_angle_deg)
                accepted.append({"case_id": cid, "angle_deg": theta, "angle_error_deg": error,
                                 "pressure_loss_pa": dp, "mass_imbalance": balance,
                                 "target_met": error <= p.angle_tolerance_deg,
                                 "mesh_cells": cells, "solver": row["solver"]})
            except (ValueError, TypeError, OverflowError) as exc:
                rejected.append({"case_id": cid, "reason": str(exc)})
    accepted.sort(key=lambda x: (not x["target_met"], x["pressure_loss_pa"],
                                x["angle_error_deg"], x["case_id"]))
    feasible = [r for r in accepted if r["target_met"]]
    return {"source": str(csv_path.resolve()), "accepted": accepted, "rejected": rejected,
            "missing_case_ids": sorted(known - seen),
            "best_available_case": feasible[0]["case_id"] if feasible else None,
            "note": "Выбор только среди импортированных данных; независимая проверка сетки обязательна"}


def comma_numbers(text: str) -> list[float]:
    try:
        values = [float(s.strip()) for s in text.split(",")]
    except ValueError as exc:
        raise ValueError("Ожидается список чисел через запятую") from exc
    if not values or not all(math.isfinite(v) for v in values):
        raise ValueError("Ожидаются конечные числа")
    return values


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="FlowPrep — начало курсового проекта КСКЭР")
    sub = parser.add_subparsers(dest="command")
    ref = sub.add_parser("reference", help="Эталон пустого канала")
    ref.add_argument("--config", type=Path)
    prep = sub.add_parser("prepare", help="Подготовить варианты без запуска ANSYS")
    prep.add_argument("--config", type=Path)
    prep.add_argument("--out", type=Path, default=Path("export"))
    prep.add_argument("--angles", default="15,30,45,60,75")
    prep.add_argument("--chords", default="0.012,0.020,0.028")
    imp = sub.add_parser("import-results", help="Обработать реальный экспорт решателя")
    imp.add_argument("csv", type=Path)
    imp.add_argument("--manifest", required=True, type=Path)
    imp.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if not args.command:
            from gui import run
            run()
            return 0
        if args.command == "reference":
            result = reference(load_parameters(args.config) if args.config else Parameters())
        elif args.command == "prepare":
            result = prepare(load_parameters(args.config) if args.config else Parameters(),
                             args.out, comma_numbers(args.angles), comma_numbers(args.chords))
        else:
            result = analyse_results(args.csv, args.manifest)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.out, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
