# Cómo contribuir

Guía corta para trabajar los dos grupos sin pisarnos. Lo que aquí se pide lo revisa el CI
(`.github/workflows/`), así que si algo se pone en rojo, casi siempre el mensaje dice qué
corregir.

## Flujo en cinco pasos

1. **Un ticket = una rama = un PR.** No mezcles tickets en una misma rama salvo que el
   propio ticket los agrupe.
2. **Parte de `main` actualizado:**
   ```bash
   git fetch origin
   git checkout -b p5-NN-descripcion origin/main     # grupo A
   git checkout -b p5-tNN-descripcion origin/main    # grupo B
   ```
3. **Haz commits pequeños** con el formato de abajo.
4. **Corre en local lo mismo que el CI** (tabla más abajo) antes de subir.
5. **Abre el PR** con el título en formato y la plantilla completa. Si el CI está en rojo,
   no se mergea.

## Ramas

Todo en minúsculas y con guiones.

| Caso | Ejemplo |
|---|---|
| Ticket del grupo A (`P5-NN`) | `p5-01-repo-base`, `p5-13-metricas` |
| Ticket del grupo B (`TNN`) | `p5-t01-plazos`, `p5-t13-contrato-comando` |
| Varios tickets | `p5-13-15-metricas-bench`, `p5-t04-t05-fallas` |
| Sin ticket | `fix/contrato-typo`, `docs/readme-comandos` |

Los prefijos válidos para ramas sin ticket son `feat`, `fix`, `test`, `chore`, `docs`,
`refactor`, `ci`, `build`, `perf` y `style`.

## Commits

```
P5-NN: qué cambia, en una línea
TNN: qué cambia, en una línea
fix: qué se arregla, en una línea
```

- Primera línea de unos 72 caracteres, sin punto final. Español o inglés, como prefieras.
- Si hace falta, deja una línea en blanco y explica **por qué** en el cuerpo: el qué ya
  lo dice el diff.
- Un commit = un cambio con sentido. Evita `wip`, `arreglos` o `cambios varios`.
- **Nunca** subas `.env`, claves ni tokens: `.env` está ignorado.

Esta guía no se verifica commit por commit; sí se verifica el nombre de la rama y el título
del PR (siguiente sección).

## Pull requests

- **Título** con el mismo formato que un commit: `P5-01: repo base`, `T01: Declarar los plazos`,
  `P5-13 P5-15: métricas y benchmark`, `P5-13/15: ...`, `T04 T05: ...` o `fix: ...`.
  Ojo con `T13 · texto`, `P5-01 - texto` o `P5-01 texto`: no cumplen.
- **Descripción:** completa la plantilla. Di qué probaste **y qué no pudiste probar**.
- **Cierra el issue** con `Cierra #NN` en la descripción.
- Si tu PR **depende de otro sin mergear**, apúntalo a la rama de ese ticket en vez de
  `main`, y cuando el padre se mergee, reapunta el tuyo a `main`.
- Antes de mergear, actualiza tu rama con `main` si otro PR entró mientras trabajabas, y
  espera a que el CI vuelva a pasar: dos PR que pasan por separado pueden romper `main` juntos.
- Si cambias `config/contrato/`, el PR lo aprueban ambos PM (ver `CONTRATO.md`).

Si el título o la rama no cumplen, el job **Nombre de rama y título del PR** falla. Para el
título basta editarlo en GitHub: el job se vuelve a correr solo. Para comprobarlo antes de
abrir el PR:

```bash
bash .github/scripts/check-naming.sh "$(git branch --show-current)" "P5-NN: mi título"
```

## Qué corre el CI

Se ejecuta en cada PR (contra cualquier rama base) y en cada push a `main`. Son los mismos
comandos que puedes correr en tu máquina, desde la raíz del repo:

```bash
uv sync --locked --no-build
uv run --locked --no-build ruff check .
uv run --locked --no-build ruff format --check .
uv run --locked --no-build pytest -q
```

- `--locked` falla si `uv.lock` no corresponde a `pyproject.toml`: si agregas una dependencia,
  usa `uv add` y sube los dos archivos.
- `--no-build` solo acepta wheels ya publicadas, sin ejecutar scripts de compilación de terceros.
  Si una dependencia nueva solo existe como código fuente, el CI fallará a propósito para que el
  equipo lo revise y decida.
- No se aceptan paquetes de GPU (`nvidia-*`, `onnxruntime-gpu`, ...): el entregable se evalúa en CPU
  y `tests/test_humo.py` lo revisa en `uv.lock`.

Para arreglar de golpe lo que Ruff puede corregir solo: `uv run ruff check --fix .` y
`uv run ruff format .`.

`CI OK` es el check que resume a todos los demás. Si un job falla, `CI OK` también falla.

### Ruff

La configuración vive en `pyproject.toml`. Reglas activas: `E`, `F` (errores y pyflakes),
`I` (orden de imports), `B` (bugbear: bugs probables), `SIM` (simplificaciones), `C4`
(comprensiones y literales) y `RUF` (reglas propias de Ruff). Si de verdad necesitas silenciar
una regla en una línea, usa `# noqa: CODIGO` con el motivo al lado.

## Código en `src/`

Cada paquete vive en su carpeta dentro de `src/` (`src/contrato/`, `src/control/`, ...).
`uv sync` instala el proyecto en modo editable, así que un paquete nuevo se importa sin
tocar `pyproject.toml` y se corre con `uv run python -m paquete`. Las pruebas van en `tests/`.

## Finales de línea en Windows

El repo guarda LF y `.gitattributes` lo pide también en tu carpeta de trabajo (un `.sh`
con CRLF no corre en bash). Si tu copia tiene archivos con CRLF de antes, con todo
commiteado o guardado:

```bash
git add --renormalize .
git status   # no debería mostrar cambios de contenido
```

## Para quien administra el repositorio

Estos ajustes se hacen en *Settings → Branches → Branch protection rules* para `main` y
requieren permisos de administración; el código por sí solo no puede activarlos:

- **Require a pull request before merging.**
- **Require status checks to pass**, marcando `CI OK`. Opcionalmente también
  `Nombre de rama y título del PR`.
- **Require branches to be up to date before merging.**

Mientras eso no esté activado, los checks en rojo avisan pero no bloquean el botón de merge.
