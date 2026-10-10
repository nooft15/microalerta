# 🔬 MicroAlerta

**Monitoreo ciudadano de partículas tipo microplástico en el aire de Atacama y Copiapó.**

Integra **ciencia escolar, datos ambientales y tecnología**:
muestreo pasivo con placa Petri + agua destilada congelada (40 mL),
observación microscópica con tinción limitada (Lugol / azul de metileno),
control cerrado y réplicas, clima real y **recomendaciones de autocuidado** para la comunidad.

Es una **PWA móvil** (instalable en Android/iOS) servida por un backend **Python/Flask + SQLite**.

---

## 🚀 Cómo ejecutarla

```bash
cd microalerta
pip install -r requirements.txt
python app.py                 # → http://localhost:8000
```

> **Atajo en VS Code:** abre `run.py` (raíz del workspace) y pulsa **▶ Run
> Python File** — arranca el servidor sin escribir nada. Detenlo con el
> ícono de cuadrado □ en la terminal.

Para probar en tu celular (misma red Wi-Fi):
`python app.py --port 8000` y abre `http://<IP-de-tu-PC>:8000`.

### Cuentas demo (clave: `demo123`)
| Usuario    | Rol            | Para qué sirve |
|------------|----------------|----------------|
| `admin`    | Administración | Valida reportes, gestiona tinciones y puntos |
| `colegio`  | Equipo escolar | Sube muestras (rol escuela) |
| `ciudadano`| Vecino/a       | Sube muestras comunitarias |

### Pruebas y utilidades
```bash
python -m pytest tests -q          # 20 pruebas (ciencia + API)
python tools/gen_icons.py          # regenera los íconos de la PWA
python tools/smoke_test.py         # prueba del servidor HTTP real
python app.py --seed               # restablece datos demostrativos
```

---

## 🧪 Alineación con el protocolo

| Protocolo | Implementación |
|---|---|
| Recolección pasiva: placa Petri + **40 mL de agua destilada congelada** | Campos `volume_ml` (40), `medium`, placa `dish_id` |
| Observación microscópica y **tinción por eliminación (Lugol / azul de metileno)** | La app **solo ofrece las tinciones habilitadas por admins** (`PUT /api/stains`); el formulario las lista de forma limitada |
| **Control cerrado y réplicas** | `sample_type` (`muestra` / `replica` / `blanco`), grupo `replicate_group`; la ciencia valida blancos (tolerancia 2 partículas) y mínimo 3 platos por grupo |
| **Clima** (viento, humedad, temperatura) | Open-Meteo (primaria) + fallback **DGAC/METAR** (aviationweather, estación SCAT Copiapó). Capa de *adaptadores* para conmutar a otras fuentes |
| Fotos del campo | Subida con cámara del celular (`capture="environment"`), revisadas por admin antes de publicarse |

---

## 🗺️ Pantallas (vista móvil)

- **Inicio** — estado comunitario (semáforo), clima actual, últimos reportes aprobados.
- **Reportar** — flujo guiado: placa → microscopio/tinción → foto → envío a revisión.
- **Mapa** — puntos de la Región de Atacama coloreados por el semáforo del último dato aprobado.
- **Protocolo** — guía escolar paso a paso (acordeón).
- **Autocuidado** — recomendaciones según concentración + viento/humedad/temperatura, con simulador.
- **Perfil** — cuenta, cierre de sesión e instrucciones para instalar la PWA.
- **Admin** — cola de validación (aprobar/rechazar con comentario), control de tinciones permitidas, alta/activación de puntos de muestreo y estadísticas.

## 🧮 Métricas calculadas

- `conc_p_ml` (partículas / mL), `depo_p_cm²`, `depo_p/m²·día`.
- Semáforo (p/mL): 🟢 < 0.5 · 🟡 0.5–2.0 · 🟠 2.0–5.0 · 🔴 ≥ 5.0
- QC de blancos (tolerancia = 2) y advertencias de réplicas en el detalle de cada reporte.

## 📁 Estructura

```
microalerta/
├── app.py                  # entrypoint (python app.py)
├── requirements.txt
├── microalerta/            # paquete backend
│   ├── __init__.py         # app factory (Flask)
│   ├── config.py           # constantes del protocolo
│   ├── db.py               # schema SQLite
│   ├── science.py          # métricas, semáforo, QC, autocuidado
│   ├── weather.py          # adaptadores Open-Meteo + DGAC/METAR
│   ├── api.py              # REST (sesión, reportes, admin, comunidad)
│   └── seed.py             # datos demo (Atacama/Copiapó)
├── static/                 # PWA (sin build)
│   ├── index.html · app.css · app.js
│   ├── manifest.webmanifest · sw.js · icons/
│   └── uploads/            # fotos subidas
├── tools/gen_icons.py · smoke_test.py
└── tests/test_science.py · test_api.py
```

## 🎯 Roadmap sugerido

1. Autenticación robusta (registro con aprobación, tokens) y usuarios reales por comuna.
2. Histórico por punto (gráficos de tendencia) y exportación CSV para investigación escolar.
3. Validación de imágenes con IA (conteo asistido de partículas) como apoyo al conteo manual.
4. Despliegue en hosting gratuito (Render/Railway) con HTTPS para instalar la PWA.