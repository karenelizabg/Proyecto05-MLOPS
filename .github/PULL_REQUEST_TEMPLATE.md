## Qué cambia

<!-- Resume en pocas líneas qué hace este PR y por qué. -->

Cierra #

## Cómo lo verifiqué

<!-- Qué corriste y qué viste. Sé explícito con lo que NO pudiste probar. -->

## Checklist

- [ ] La rama es `p5-NN-descripcion` / `p5-tNN-descripcion` (o `tipo/descripcion`) y el título es `P5-NN: descripción` / `TNN: descripción` (o `tipo: descripción`). Ver [CONTRIBUTING.md](../CONTRIBUTING.md).
- [ ] Corrí en local lo mismo que el CI (`uv sync --locked`, `ruff check`, `ruff format --check`, `pytest`), o expliqué arriba por qué no.
- [ ] No subí secretos: `.env`, claves ni tokens.
- [ ] Si agregué una dependencia, usé `uv add` y subí `uv.lock` en este mismo PR.
- [ ] Actualicé README o docs si cambia el comportamiento, un comando o la configuración.
- [ ] Si toco archivos compartidos (`pyproject.toml`, `uv.lock`, `config/contrato/`), lo avisé en la descripción.
