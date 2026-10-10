# Desplegar MicroAlerta en Render (gratis, con HTTPS)

Esta guía deja tu app en una **URL pública** (ej. `https://microalerta.onrender.com`)
para que tu amigo la abra desde cualquier dispositivo y la instale como app
(PWA). Render es gratis, no pide tarjeta para el plan Free y **permite las
llamadas salientes a Open-Meteo / met.no** que usa tu clima.

> Nota importante del plan Free: el disco es **efímero**. Las imágenes y las
> muestras que creen los usuarios se borran cuando el servicio se "duerme"
> (15 min sin tráfico) o al redesplegar. Los **datos demo** (usuarios, puntos,
> reportes de ejemplo) se reconstruyen solos en cada arranque porque la siembra
> es idempotente. Si más adelante quieres que los datos reales no se pierdan,
> monta un *Render Disk* (de pago) o usa PostgreSQL con `DATABASE_URL`.

---

## Requisito previo: subir el código a GitHub

Render despliega desde un repositorio de GitHub.

1. Crea una cuenta en https://github.com (si no tienes) y una en
   https://render.com (puedes entrar "con GitHub").
2. Crea un **nuevo repositorio** en GitHub (público o privado, da igual), por
   ejemplo `microalerta`. No inicialices con README.
3. En tu PC, dentro de la carpeta del proyecto `c:\python123\microalerta`,
   abre una terminal y ejecuta (la primera vez):

   ```powershell
   git init
   git add .
   git commit -m "MicroAlerta listo para produccion"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/microalerta.git
   git push -u origin main
   ```

   El `.gitignore` ya excluye `microalerta.db`, `static/uploads/*` y
   `data/*.xlsx`, así que **no** se sube tu base de datos local ni tus imágenes.

> Si no tienes `git` instalado: descárgalo en https://git-scm.com/download/win

---

## Crear el servicio web en Render

1. En https://dashboard.render.com pulsa **New + → Web Service**.
2. Conecta tu cuenta de GitHub y elige el repositorio `microalerta`.
3. Rellena así:

   | Campo | Valor |
   |---|---|
   | **Name** | `microalerta` (definirá la URL) |
   | **Region** | la más cercana (Oregon / Ohio) |
   | **Branch** | `main` |
   | **Root Directory** | *(vacío — los archivos están en la raíz del repo)* |
   | **Runtime** | `Python 3` |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | *(déjalo vacío: Render detecta el `Procfile` y usa `waitress`)* |
   | **Instance Type** | `Free` |

4. Despliega con **Create Web Service**.

   Los archivos `runtime.txt` (Python 3.12.7), `requirements.txt` y `Procfile`
   ya están en el repo, así que Render detecta todo automáticamente.

### Variable de entorno recomendada (seguridad de sesiones)

En **Environment → Add Environment Variable**:

| Key | Value |
|---|---|
| `MICROALERTA_SECRET` | una frase larga y secreta que inventes |

Esto firma las cookies de sesión. Si no la pones, Render usa la de desarrollo
(funciona, pero es menos seguro). Guarda los cambios.

---

## Probar la app

1. Cuando el estado diga **Live**, abre la URL que Render te asigna
   (arriba, tipo `https://microalerta.onrender.com`).
2. **Primera apertura tarda ~30-60 s** si el servicio estaba dormido
   (plan Free). Las siguientes son rápidas.
3. Entra con las cuentas demo (clave `demo123` para todas):
   - `admin` → panel de administración
   - `colegio` / `ciudadano` → crear reportes

### Instalarla como app en el celular

Al ser HTTPS, la PWA se instala igual que en local:
- **Android (Chrome):** menú ⋮ → *Instalar aplicación / Añadir a pantalla de inicio*.
- **iPhone (Safari):** botón Compartir → *Añadir a la pantalla de inicio*.

---

## Actualizar la app tras cambiar código

Cada vez que hagas cambios y los subas a GitHub, Render redespliega solo:

```powershell
git add .
git commit -m "descripcion del cambio"
git push
```

Render reconstruye y reinicia. Verás el progreso en la pestaña *Logs*.

---

## Si algo falla (diagnóstico)

- **Error 502 / servicio caído:** revisa la pestaña **Logs** en Render. Casi
  siempre es una dependencia; confirma que `waitress` esté en `requirements.txt`
  (ya lo está).
- **Página en blanco o sin estilos:** espera a que el build termine (el status
  debe decir *Live*), luego recarga con Ctrl+F5.
- **El clima no carga:** revisa que Render permita salida a internet (el plan
  Free sí lo permite; por eso elegimos Render y no PythonAnywhere).
- **Cambios en la base de datos se "pierden":** es el disco efímero del plan
  Free (ver nota arriba). Para persistencia real, añade PostgreSQL o un Disk.
