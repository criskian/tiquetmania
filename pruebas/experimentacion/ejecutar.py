"""Ejecuta los escenarios de Experimentacion.jmx en modo no-GUI, uno a la vez.

Para cada escenario y repetición:
  1. Reinicia la API (memoria limpia) y espera a /api/salud.
  2. Copia el plan habilitando SOLO el Grupo de Hilos del escenario.
  3. Ejecuta JMeter sin interfaz y guarda .jtl, reporte HTML, PerfMon y entorno.

Uso (desde cualquier carpeta):
  python ejecutar.py --puerto 9000 --repeticiones 2            # todos los escenarios
  python ejecutar.py --puerto 9000 --escenarios P01-A P01-B    # solo algunos
  python ejecutar.py --puerto 9000 --repeticion-inicial 2 --escenarios P04 P05-A   # retomar la repetición 2

Requisitos: JMeter 5.6.3 con jpgc Standard Set y PerfMon; ServerAgent en localhost:4444 (opcional).
Resultados: resultados/<escenario>/r<n>/ (no se suben al repositorio).
"""
import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
PLAN = AQUI / "Experimentacion.jmx"
TEMP = AQUI / "_ejecucion.jmx"
API = RAIZ / "api" / "ticketmania_simple.py"
CLASES_GRUPO = {"ThreadGroup", "kg.apc.jmeter.threads.UltimateThreadGroup"}
# Escenarios sin temporizador dejan muchas conexiones en TIME_WAIT: se espera más antes del siguiente.
ENFRIAMIENTO_LARGO = {"P03-B", "P10-C"}


def jmeter_por_defecto():
    home = os.environ.get("JMETER_HOME")
    if home:
        return str(Path(home) / "bin" / ("jmeter.bat" if os.name == "nt" else "jmeter"))
    candidato = Path.home() / "apache-jmeter-5.6.3" / "bin" / ("jmeter.bat" if os.name == "nt" else "jmeter")
    return str(candidato) if candidato.exists() else "jmeter"


def escenarios_del_plan():
    arbol = ET.parse(PLAN)
    return [e.get("testname").split(" | ")[0] for e in arbol.iter() if e.get("testclass") in CLASES_GRUPO]


def preparar_plan(codigo):
    arbol = ET.parse(PLAN)
    encontrado = False
    for e in arbol.iter():
        if e.get("testclass") in CLASES_GRUPO:
            activo = e.get("testname").split(" | ")[0] == codigo
            e.set("enabled", "true" if activo else "false")
            encontrado |= activo
    if not encontrado:
        sys.exit(f"No existe el escenario {codigo}")
    arbol.write(TEMP, encoding="utf-8", xml_declaration=True)


def esperar_api(puerto, segundos=30):
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/salud", timeout=2) as r:
                if json.loads(r.read()).get("estado") == "OK":
                    return True
        except OSError:
            time.sleep(0.5)
    return False


def agente_disponible():
    try:
        with socket.create_connection(("127.0.0.1", 4444), timeout=2) as s:
            s.sendall(b"test\n")
            return s.recv(16).startswith(b"Yep")
    except OSError:
        return False


def version_java():
    try:
        r = subprocess.run(["java", "-version"], capture_output=True, text=True)
        return (r.stderr or r.stdout).splitlines()[0]
    except OSError:
        return "desconocida"


def ejecutar(codigo, rep, args):
    salida = AQUI / "resultados" / codigo / f"r{rep}"
    if salida.exists():
        shutil.rmtree(salida)
    salida.mkdir(parents=True)
    preparar_plan(codigo)

    api = subprocess.Popen([sys.executable, str(API), "--puerto", str(args.puerto)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not esperar_api(args.puerto):
            sys.exit("La API no respondió")
        inicio = datetime.now()
        cmd = [args.jmeter, "-n", "-t", TEMP.name,
               "-l", str(salida / "resultados.jtl"), "-e", "-o", str(salida / "reporte"),
               "-j", str(salida / "jmeter.log"),
               f"-Jpuerto={args.puerto}", "-Jsample_variables=num_reserva",
               f"-Jperfmon_file={salida / 'perfmon.csv'}"]
        print(f"[{inicio:%H:%M:%S}] {codigo} r{rep}: ejecutando...", flush=True)
        r = subprocess.run(cmd, cwd=AQUI, capture_output=True, text=True)
        fin = datetime.now()
        (salida / "consola.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
        resumen = [l for l in r.stdout.splitlines() if l.startswith("summary =")]
        print(f"[{fin:%H:%M:%S}] {codigo} r{rep}: {resumen[-1] if resumen else 'sin resumen (revisa consola.txt)'}", flush=True)
    finally:
        api.terminate()
        api.wait(timeout=10)

    (salida / "entorno.json").write_text(json.dumps({
        "escenario": codigo, "repeticion": rep,
        "inicio": inicio.isoformat(timespec="seconds"), "fin": fin.isoformat(timespec="seconds"),
        "equipo": platform.node(), "so": platform.platform(), "procesador": platform.processor(),
        "java": version_java(), "python_api": platform.python_version(),
        "api_en_mismo_equipo": True, "puerto": args.puerto, "perfmon": agente_disponible(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--escenarios", nargs="*", help="Códigos (P01-A, P04, ...). Por defecto, todos.")
    ap.add_argument("--repeticiones", type=int, default=2)
    ap.add_argument("--repeticion-inicial", type=int, default=1, help="Para retomar una tanda: 2 salta la repetición 1")
    ap.add_argument("--puerto", type=int, default=8080)
    ap.add_argument("--enfriamiento", type=int, default=20, help="Segundos de pausa entre ejecuciones")
    ap.add_argument("--jmeter", default=jmeter_por_defecto())
    args = ap.parse_args()

    codigos = args.escenarios or escenarios_del_plan()
    if not agente_disponible():
        print("Aviso: ServerAgent no responde en localhost:4444; PerfMon quedará vacío.", flush=True)
    try:
        # Repeticiones intercaladas: r1 de todos, luego r2 de todos (reduce el efecto de la deriva del equipo).
        for rep in range(args.repeticion_inicial, args.repeticiones + 1):
            for codigo in codigos:
                ejecutar(codigo, rep, args)
                time.sleep(120 if codigo in ENFRIAMIENTO_LARGO else args.enfriamiento)
    finally:
        TEMP.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
