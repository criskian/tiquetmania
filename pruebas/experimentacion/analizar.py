"""Resume los resultados de ejecutar.py en resultados/resumen.json.

Para cada escenario y repetición: estadísticas del reporte HTML (statistics.json),
errores y ventanas de tiempo del .jtl, y CPU/memoria de PerfMon.

Uso: python analizar.py
"""
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RES = AQUI / "resultados"


def leer_jtl(ruta):
    """Lee solo las columnas necesarias (los .jtl sin temporizador superan las 500.000 filas)."""
    filas = []
    with open(ruta, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ok = r["success"].lower() == "true"
            filas.append({"ts": int(r["timeStamp"]), "ms": int(r["elapsed"]), "label": r["label"], "ok": ok,
                          "responseCode": "" if ok else r["responseCode"],
                          "responseMessage": "" if ok else r["responseMessage"],
                          "failureMessage": "" if ok else r["failureMessage"],
                          "num_reserva": r.get("num_reserva") if r["label"] == "SeleccionTarifaYCantidad" else None})
    return filas


def p95(valores):
    if not valores:
        return None
    v = sorted(valores)
    return v[min(len(v) - 1, int(round(0.95 * len(v))) - 1)]


def ventana(filas, t0, desde, hasta, etiqueta=None):
    sel = [r for r in filas if desde * 1000 <= r["ts"] - t0 < hasta * 1000 and (etiqueta is None or r["label"] == etiqueta)]
    if not sel:
        return {"muestras": 0}
    ms = [r["ms"] for r in sel]
    return {"muestras": len(sel), "rendimiento": round(len(sel) / (hasta - desde), 2),
            "media": round(statistics.mean(ms), 1), "p95": p95(ms), "max": max(ms),
            "error_pct": round(100 * sum(not r["ok"] for r in sel) / len(sel), 2)}


def perfmon(ruta):
    if not ruta.exists():
        return {}
    series = defaultdict(list)
    with open(ruta, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            etiqueta = r["label"].replace("localhost ", "")
            etiqueta = (etiqueta.replace("ptql=State.Name.eq=python,Args.*.ct=ticketmania", "API")
                        .replace("ptql=State.Name.eq=java,Args.*.ct=ApacheJMeter", "JMeter"))
            series[etiqueta].append((int(r["timeStamp"]), int(r["elapsed"]) / 1000))
    out = {}
    for k, v in series.items():
        vals = [x for _, x in v]
        out[k] = {"muestras": len(vals), "media": round(statistics.mean(vals), 2), "max": round(max(vals), 2),
                  "min": round(min(vals), 2), "primero": round(vals[0], 2), "ultimo": round(vals[-1], 2),
                  "serie": [(t, round(x, 2)) for t, x in v]}
    return out


def analizar(carpeta):
    stats = json.loads((carpeta / "reporte" / "statistics.json").read_text(encoding="utf-8"))
    filas = leer_jtl(carpeta / "resultados.jtl")
    t0 = min(r["ts"] for r in filas)
    t1 = max(r["ts"] + r["ms"] for r in filas)
    errores = Counter(f'{r["label"]}: {r["responseCode"]} {r["responseMessage"] or r["failureMessage"]}'[:140]
                      for r in filas if not r["ok"])
    reservas = [r.get("num_reserva") for r in filas if r["label"] == "SeleccionTarifaYCantidad" and r["ok"]]
    reservas = [x for x in reservas if x and x != "num_reserva_not_found"]
    res = {
        "duracion_s": round((t1 - t0) / 1000, 1),
        "etiquetas": {k: {"muestras": v["sampleCount"], "error_pct": round(v["errorPct"], 2),
                          "media": round(v["meanResTime"], 1), "mediana": v["medianResTime"],
                          "p90": v["pct1ResTime"], "p95": v["pct2ResTime"], "p99": v["pct3ResTime"],
                          "max": v["maxResTime"], "min": v["minResTime"], "rendimiento": round(v["throughput"], 2)}
                      for k, v in stats.items()},
        "errores": errores.most_common(8),
        "reservas_creadas": len(reservas), "reservas_unicas": len(set(reservas)),
        # Total distinto con respuesta HTTP 2xx (un fallo real del cálculo), frente a aserciones que fallan por no haber respuesta
        "total_no_coincide": sum(1 for r in filas if not r["ok"] and r["responseCode"].startswith("2")
                                 and "total" in r["failureMessage"].lower()),
        "total_sin_respuesta": sum(1 for r in filas if not r["ok"] and not r["responseCode"].startswith("2")
                                   and "total" in r["failureMessage"].lower()),
        "perfmon": perfmon(carpeta / "perfmon.csv"),
        "entorno": json.loads((carpeta / "entorno.json").read_text(encoding="utf-8")),
    }
    codigo = carpeta.parent.name
    dur = res["duracion_s"]
    if codigo.startswith("P02"):
        res["inicio_10s"] = ventana(filas, t0, 0, 10)
        res["resto"] = ventana(filas, t0, 10, max(11, dur))
    if codigo == "P04":
        res["escalones"] = {n: ventana(filas, t0, a, b) for n, (a, b) in
                            {"50": (10, 60), "100": (70, 120), "250": (130, 180), "500": (190, 240)}.items()}
    if codigo.startswith("P05"):
        res["por_minuto"] = [ventana(filas, t0, m * 60, (m + 1) * 60) for m in range(int(dur // 60) or 1)]
    if codigo.startswith("P10"):
        res["estable"] = ventana(filas, t0, 40, max(41, dur - 5))
    return res


def main():
    resumen = {}
    for esc in sorted(p for p in RES.iterdir() if p.is_dir()):
        for rep in sorted(p for p in esc.iterdir() if (p / "reporte" / "statistics.json").exists()):
            resumen.setdefault(esc.name, {})[rep.name] = analizar(rep)
    (RES / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    for esc, reps in resumen.items():
        for rep, d in reps.items():
            t = d["etiquetas"]["Total"]
            print(f'{esc:6s} {rep}: n={t["muestras"]:6d} err={t["error_pct"]:6.2f}% media={t["media"]:7.1f} '
                  f'p95={t["p95"]:7.0f} max={t["max"]:6.0f} rend={t["rendimiento"]:7.2f}/s dur={d["duracion_s"]}s')


if __name__ == "__main__":
    main()
