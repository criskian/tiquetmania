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

Ejecución local, desde `pruebas/jmeter/`:

```bash
jmeter -n -t Ticketmania.jmx -l resultados.jtl -e -o reporte
```

_Pendiente: descripción del workflow y enlace a la última ejecución._

## Ejercicio 2: experimentación "¿Qué pasaría si...?"

Diez preguntas de carga, estrés, concurrencia y recursos, con escenarios en `pruebas/experimentacion/`. El análisis y las evidencias se entregan aparte, en un documento.

_Pendiente: escenarios por pregunta._

## Limitaciones

- La API y JMeter comparten equipo, tanto en local como en el pipeline. En una prueba real la API correría en un equipo dedicado.
- La API guarda los datos en memoria: reiniciarla borra las reservas.
- Las pruebas son de camino feliz.
