"""Настольный интерфейс FlowPrep на Tkinter."""
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from flowprep import (Parameters, analyse_results, load_parameters, prepare,
                      reference, validate, vertices, write_json)

LABELS = {
    "length_m": "Длина канала L, м",
    "height_m": "Высота канала H, м",
    "center_x_m": "Центр заслонки x, м",
    "center_y_m": "Центр заслонки y, м",
    "chord_m": "Длина заслонки c, м",
    "thickness_m": "Толщина заслонки t, м",
    "angle_deg": "Угол заслонки α, град",
    "mean_velocity_m_s": "Средняя скорость U, м/с",
    "density_kg_m3": "Плотность ρ, кг/м³",
    "viscosity_pa_s": "Вязкость μ, Па·с",
    "minimum_gap_m": "Минимальный зазор, м",
    "probe_x_m": "Контрольное сечение x, м",
    "target_angle_deg": "Целевой угол потока, град",
    "angle_tolerance_deg": "Допуск угла, град",
    "mass_tolerance": "Допуск баланса массы, доля",
}


class FlowPrepApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=16)
        self.pack(fill="both", expand=True)
        master.title("FlowPrep 0.1 — Михайлов Е. В. — КСКЭР")
        master.geometry("1160x800")
        master.minsize(1060, 760)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Заслонка в ламинарном потоке газа",
                  font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        inputs = ttk.LabelFrame(self, text="Исходные данные в СИ", padding=12)
        inputs.grid(row=1, column=0, sticky="nsw", padx=(0, 16))
        self.values = {}
        for i, (key, value) in enumerate(asdict(Parameters()).items()):
            ttk.Label(inputs, text=LABELS[key]).grid(row=i, column=0, sticky="w", pady=4)
            variable = tk.StringVar(value=str(value))
            self.values[key] = variable
            ttk.Entry(inputs, textvariable=variable, width=15).grid(row=i, column=1, padx=(12, 0), pady=4)
        for i, (label, command) in enumerate([
            ("Проверить и рассчитать эталон", self.calculate),
            ("Сохранить настройки", self.save_config),
            ("Загрузить настройки", self.load_config),
            ("Подготовить 15 вариантов", self.export),
            ("Импортировать результаты", self.import_results),
        ], start=len(LABELS)):
            ttk.Button(inputs, text=label, command=command).grid(row=i, column=0, columnspan=2,
                                                               sticky="ew", pady=4)
        panel = ttk.Frame(self)
        panel.grid(row=1, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        self.canvas = tk.Canvas(panel, height=220, bg="#f4f8fc", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="ew")
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.text = tk.Text(panel, wrap="word", font=("Consolas", 11), padx=12, pady=12)
        self.text.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.status = tk.StringVar(value="Готово")
        ttk.Label(self, textvariable=self.status, wraplength=1100).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.last_parameters = Parameters()
        self.calculate()

    def get_parameters(self):
        p = Parameters(**{key: float(var.get().replace(",", ".")) for key, var in self.values.items()})
        validate(p)
        return p

    def show(self, text):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")

    def error(self, exc):
        self.status.set(f"Ошибка: {exc}")
        messagebox.showerror("Проверьте исходные данные", str(exc), parent=self.master)

    def calculate(self):
        try:
            p = self.get_parameters()
            self.last_parameters = p
            r = reference(p)
            self.show(
                "ЭТАЛОН ПУСТОГО ПЛОСКОГО КАНАЛА\n\n"
                f"Число Рейнольдса по Dh = 2H:  {r['reynolds']:.6g}\n"
                f"Максимальная скорость:        {r['max_velocity_m_s']:.6g} м/с\n"
                f"Расход на единицу ширины:     {r['flow_per_unit_span_m2_s']:.6g} м²/с\n"
                f"Массовый расход на 1 м:       {r['mass_flow_per_unit_span_kg_s_m']:.6g} кг/(с·м)\n"
                f"Перепад статического давления: {r['pressure_drop_pa']:.6g} Па\n"
                f"Касательное напряжение:       {r['wall_shear_pa']:.6g} Па\n"
                f"Коэффициент Дарси:            {r['darcy_friction_factor']:.6g}\n\n"
                "Профиль на входе: u(y) = 6U(y/H)(1 − y/H).\n"
                "Эталон предполагает развитое течение между\n"
                "бесконечно широкими параллельными пластинами.\n\n"
                "ТЕКУЩИЙ ЭТАП\n"
                "Проверка геометрии, расчёт эталона, экспорт серии.\n"
                "Поле течения с заслонкой ещё не рассчитано.\n"
                "Запуск ANSYS будет подключён следующим этапом.\n\n"
                "Численные значения по умолчанию — демонстрационный\n"
                "набор, который нужно согласовать с руководителем.\n"
                + ("\n" + "\n".join(r["warnings"]) if r["warnings"] else "")
            )
            self.redraw()
            self.status.set("Параметры проверены. Эталон рассчитан для канала без заслонки.")
        except (ValueError, TypeError) as exc:
            self.error(exc)

    def redraw(self):
        p = self.last_parameters
        c = self.canvas
        c.delete("all")
        scale = min((max(c.winfo_width(), 400) - 70) / p.length_m, 100 / p.height_m)
        x0, y0 = 35, 70
        c.create_text(20, 22, text="Геометрия заслонки и контрольное сечение",
                      anchor="w", font=("Segoe UI", 12, "bold"), fill="#172b40")
        c.create_rectangle(x0, y0, x0+p.length_m*scale, y0+p.height_m*scale,
                           fill="#e2f0fc", outline="#244763", width=2)
        pts = [coord for x, y in vertices(p) for coord in (x0+x*scale, y0+(p.height_m-y)*scale)]
        c.create_polygon(pts, fill="#edb35c", outline="#7d4d0b", width=2)
        xp = x0+p.probe_x_m*scale
        c.create_line(xp, y0-12, xp, y0+p.height_m*scale+12, fill="#168678", dash=(5, 4))
        c.create_text(x0, 190, text=f"α = {p.angle_deg:g}°   c = {p.chord_m:g} м   H = {p.height_m:g} м",
                      anchor="w", font=("Segoe UI", 11))

    def save_config(self):
        try:
            p = self.get_parameters()
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
            if path:
                write_json(Path(path), asdict(p))
                self.status.set(f"Настройки сохранены: {path}")
        except (ValueError, OSError) as exc:
            self.error(exc)

    def load_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            p = load_parameters(Path(path))
            for key, value in asdict(p).items():
                self.values[key].set(str(value))
            self.calculate()
        except (ValueError, TypeError, OSError) as exc:
            self.error(exc)

    def export(self):
        try:
            p = self.get_parameters()
            parent = filedialog.askdirectory(title="Папка для новой серии вариантов")
            if parent:
                path = Path(parent) / ("FlowPrep_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
                r = prepare(p, path)
                self.show(json.dumps(r, ensure_ascii=False, indent=2) +
                          "\n\nВарианты подготовлены. ANSYS ещё не запускался.\n"
                          "Имена файлов и единицы измерения описаны в README.md.")
                self.status.set(f"Создано вариантов: {r['prepared']}; отклонено: {r['rejected']}. Папка: {path}")
        except (ValueError, OSError, TypeError) as exc:
            self.error(exc)

    def import_results(self):
        manifest = filedialog.askopenfilename(title="Выберите manifest.json серии", filetypes=[("JSON", "*.json")])
        if not manifest:
            return
        csv_path = filedialog.askopenfilename(title="CSV результатов из решателя", filetypes=[("CSV", "*.csv")])
        if not csv_path:
            return
        try:
            r = analyse_results(Path(csv_path), Path(manifest))
            self.show(json.dumps(r, ensure_ascii=False, indent=2))
            self.status.set(f"Принято: {len(r['accepted'])}; отклонено: {len(r['rejected'])}. "
                            "Сеточную независимость нужно проверить отдельно.")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.error(exc)


def run():
    root = tk.Tk()
    ttk.Style(root).theme_use("clam")
    FlowPrepApp(root)
    root.mainloop()
