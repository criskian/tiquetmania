# Tiquetmania: pruebas de rendimiento con JMeter

**Autor:** Cristian Camilo Molina Vides
**Curso:** Automatización de pruebas asistidas con IA, Universidad Icesi

Monorepo del taller de rendimiento: la API de Tiquetmania y sus pruebas de JMeter viven juntas, y un pipeline de GitHub Actions ejecuta la prueba de carga en cada cambio.

## Estructura

```
tiquetmania/
├── api/
│   ├── ticketmania_simple.py      # API simulada (Python 3.8+, sin dependencias)
│   └── README.md
├── pruebas/
│   ├── jmeter/                    # Ejercicio 1: lo ejecuta el pipeline
│   │   ├── Ticketmania.jmx
│   │   └── datos.csv              # misma carpeta que el .jmx (ruta relativa)
│   └── experimentacion/           # Ejercicio 2: local, el pipeline NO lo ejecuta
│       └── Experimentacion.jmx
└── .github/workflows/             # pipeline (en la raíz del repositorio)
```

## Requisitos locales

| Herramienta | Versión |
|---|---|
| Java | 17 o superior |
| Apache JMeter | 5.6.3 |
| Python | 3.8 o superior |
| Plugins (solo experimentación) | jpgc Standard Set y jpgc PerfMon |
| ServerAgent (solo experimentación) | 2.2.1, puerto 4444 |

## Ejecutar la API

```bash
python api/ticketmania_simple.py                 # http://127.0.0.1:8080
python api/ticketmania_simple.py --puerto 9000   # otro puerto
```

Verificación: `GET /api/salud` responde `{"estado": "OK"}`.

> **Nota del entorno local (Windows):** en el equipo de desarrollo el puerto 8080 está dentro de un rango reservado por Windows (WinNAT/Hyper-V, `netsh interface ipv4 show excludedportrange protocol=tcp`), así que la API local corre en el puerto 9000. El pipeline usa 8080.

## Ejercicio 1: prueba de carga en el pipeline

Escenario fijo del despliegue: Grupo de Hilos estándar, 200 usuarios, subida de 300 s, contador del bucle en 1 y Temporizador Aleatorio Uniforme de 500 a 1500 ms.

Ejecución local, desde `pruebas/jmeter/` (en el equipo de desarrollo, con la API en el puerto 9000):

```bash
jmeter -n -t Ticketmania.jmx -Jpuerto=9000 -l resultados.jtl -e -o reporte
```

### Pipeline (`.github/workflows/rendimiento.yml`)

Se ejecuta con cada `push` a `main` y a mano con `workflow_dispatch`. Un solo job en `ubuntu-latest`:

1. Descarga el repositorio.
2. Instala Java 17 (Temurin).
3. Instala JMeter 5.6.3 y agrega su `bin` a `$GITHUB_PATH`.
4. Levanta la API en el puerto 8080 en segundo plano.
5. Espera a que `/api/salud` responda (hasta 60 s).
6. Ejecuta el plan en modo no-GUI desde `pruebas/jmeter/` y genera `.jtl` y reporte HTML.
7. Revisa el `.jtl` y deja el job en rojo si hay peticiones fallidas (JMeter no lo hace por sí solo).
8. Sube el reporte como artefacto `reporte-rendimiento` con `if: always()`.

Última ejecución verificada: 600 muestras, 0 % de error ([ver en Actions](https://github.com/criskian/tiquetmania/actions/workflows/rendimiento.yml)).

## Ejercicio 2: experimentación "¿Qué pasaría si...?"

Diez preguntas de carga, estrés, concurrencia y recursos. Es local e individual, y el pipeline **no** lo ejecuta. El análisis completo, con capturas, se entrega en un documento aparte.

| Archivo | Para qué |
|---|---|
| `Experimentacion.jmx` | Un Grupo de Hilos por escenario (P01-A … P10-C); los elementos comunes, incluido PerfMon, van en el Plan de Pruebas |
| `datos.csv` | `tarifa,cantidad,total_esperado` (la última columna valida el total cobrado en P9) |
| `ejecutar.py` | Ejecuta cada escenario en no-GUI: reinicia la API, habilita solo su Grupo de Hilos y guarda `.jtl`, reporte, PerfMon y entorno |
| `analizar.py` | Resume todas las ejecuciones en `resultados/resumen.json` |

```bash
# ServerAgent para PerfMon (en este equipo SIGAR solo funciona con Java 8 de 32 bits)
startAgent.bat
# Todos los escenarios, dos repeticiones
python ejecutar.py --puerto 9000 --repeticiones 2
python analizar.py
```

| Pregunta | Escenarios | Tipo |
|---|---|---|
| 1. De 20 a 500 usuarios | P01-A, P01-B | Carga |
| 2. Ramp-up de 1 s frente a 60 s | P02-A, P02-B | Carga |
| 3. Sin temporizadores | P03-A, P03-B | Carga |
| 4. Escalones 50/100/250/500 | P04 (Ultimate Thread Group) | Estrés |
| 5. 10 minutos frente a 1 | P05-A, P05-B | Estrés |
| 6. Costo de tarifas frente a selección | P06 | Estrés |
| 7. 500 reservas simultáneas | P07 (Temporizador Sincronizado) | Concurrencia |
| 8. Sincronizados frente a distribuidos | P08-A, P08-B | Concurrencia |
| 9. Total cobrado = precio × cantidad | P09 (Aserciones JSON contra el CSV) | Concurrencia |
| 10. CPU y memoria con 500 usuarios | P10-A, P10-B, P10-C (PerfMon) | Recursos |

Hallazgo principal: el límite de la API no es la CPU ni la memoria, sino la cola de conexiones del `ThreadingHTTPServer` de Python (5 conexiones en espera). Con usuarios que hacen pausas escala casi linealmente hasta 500 usuarios, pero cuando muchos llegan al mismo tiempo la mayoría de las conexiones son rechazadas.

## Limitaciones

- La API y JMeter comparten equipo, tanto en local como en el pipeline. En una prueba real la API correría en un equipo dedicado.
- La API guarda los datos en memoria: reiniciarla borra las reservas.
- Las pruebas son de camino feliz.
