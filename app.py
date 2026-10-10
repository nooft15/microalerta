"""
MicroAlerta — servidor PWA móvil.
Uso:
    python app.py             # corre en http://localhost:8000
    python app.py --seed      # reinicia los datos demostrativos
    python app.py --port 8080
"""
import argparse
import os

from microalerta import api, create_app
from microalerta import excel
from microalerta.seed import seed_db

app = create_app()


def main():
    parser = argparse.ArgumentParser(description="MicroAlerta (PWA móvil + Flask)")
    parser.add_argument("--seed", action="store_true",
                        help="Fuerza la siembra de datos demostrativos")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--no-excel-open", action="store_true",
                        help="No abre automáticamente el Excel al arrancar")
    parser.add_argument("--no-clima-backfill", action="store_true",
                        help="No completa el clima de las muestras que aún no lo tienen")
    args = parser.parse_args()

    seed_db(app, force=args.seed)
    excel_path = app.config.get("EXCEL_PATH")
    if not args.no_clima_backfill:
        # Completa el histórico meteorológico de las muestras existentes
        # (temperatura, humedad, viento, ráfaga, dirección, presión,
        # precipitación y fuente) para que el Excel quede actualizado.
        try:
            resumen = api.backfill_weather_history(app)
            extra = (" · %s snapshot(s) huérfano(s) borrados"
                     % resumen["snapshots_huerfanos_borrados"]) \
                if resumen["snapshots_huerfanos_borrados"] else ""
            print("  Clima histórico : %s muestra(s) completadas · %s sin datos%s"
                  % (resumen["rellenadas"], resumen["sin_datos"], extra))
        except Exception as exc:                      # noqa: BLE001
            print("  Clima histórico : no se pudo completar (%s)" % exc)
    try:
        excel.sync(app)                  # Excel de datos listo al arrancar
    except Exception:
        pass
    if not args.no_excel_open:
        # Abre el MISMO Excel de datos en la app Excel del equipo.
        opened = excel.open_in_excel(excel_path)
        print("  Excel abierto    : %s" % ("sí" if opened else "no (sin entorno gráfico)"))

    print("=" * 60)
    print("  MicroAlerta · Atacama · partículas tipo microplástico en el aire")
    print(f"  Dirección local  : http://localhost:{args.port}")
    print("  Desde tu celular : http://<IP-de-esta-PC>:%d  (misma red Wi-Fi)" % args.port)
    print("  Cuentas demo     : admin / colegio / ciudadano · clave: demo123")
    print("  Excel de datos   : data/MicroAlerta_datos.xlsx (se actualiza solo)")
    print("=" * 60)
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()