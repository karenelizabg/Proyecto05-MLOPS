"""T15 · Lo que debe pasar en C1 a C10: formato, coherencia con el contrato y congelamiento.

No corre ningún caso: solo revisa casos/Cn/expectativa.yaml (eso es T17).
"""

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

RAIZ = Path(__file__).resolve().parents[1]
CASOS = RAIZ / "casos"
CONTRATO = RAIZ / "config" / "contrato"
ESQUEMA = json.loads((CASOS / "expectativa.v1.schema.json").read_text(encoding="utf-8"))
PLAZOS = yaml.safe_load((RAIZ / "config" / "control" / "plazos.yaml").read_text(encoding="utf-8"))
NOMBRES = [f"C{n}" for n in range(1, 11)]

ACCIONES = {"AVANZAR", "GIRAR_IZQ", "GIRAR_DER", "STOP"}
MOVIMIENTO = ACCIONES - {"STOP"}
REACCIONAR = {"STOP", "GIRAR_IZQ", "GIRAR_DER"}
# Desde dónde se puede medir el plazo según qué órdenes juzga el tramo.
PLAZO_DESDE_POR_ORIGEN = {
    "cuadros": {"captura", "llegada"},
    "clock": {"ultimo_cuadro"},
    "emergency": {"evento"},
    "rearm": {"evento"},
    "shutdown": {"evento"},
}


def esquema_de(nombre: str) -> dict:
    return json.loads((CONTRATO / nombre).read_text(encoding="utf-8"))


def cargar(caso: str) -> dict:
    return yaml.safe_load((CASOS / caso / "expectativa.yaml").read_text(encoding="utf-8"))


def tramos(caso: str) -> dict[str, dict]:
    return {t["nombre"]: t for t in cargar(caso)["tramos"]}


def sha256_lf(ruta: Path) -> str:
    """SHA-256 con finales de línea LF, como los guarda el repo (.gitattributes)."""
    return hashlib.sha256(ruta.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def assert_reacciona(tramo: dict) -> None:
    """Frena o gira dentro de un plazo y nunca sigue de frente."""
    assert set(tramo["acciones_permitidas"]) == REACCIONAR
    assert "AVANZAR" in tramo["acciones_prohibidas"]
    assert tramo["plazo_reaccion_ms"] is not None


def assert_solo_stop(tramo: dict) -> None:
    assert tramo["acciones_permitidas"] == ["STOP"]
    assert set(tramo["acciones_prohibidas"]) == MOVIMIENTO


# --- formato --------------------------------------------------------------------


def test_hay_una_carpeta_por_caso_con_su_expectativa():
    carpetas = sorted(
        (p.name for p in CASOS.iterdir() if p.is_dir() and p.name.startswith("C")),
        key=lambda n: int(n[1:]),
    )
    assert carpetas == NOMBRES
    for caso in NOMBRES:
        assert (CASOS / caso / "expectativa.yaml").is_file()


def test_el_esquema_de_expectativas_es_valido():
    Draft202012Validator.check_schema(ESQUEMA)


@pytest.mark.parametrize("caso", NOMBRES)
def test_cumple_el_esquema(caso):
    errores = [e.message for e in Draft202012Validator(ESQUEMA).iter_errors(cargar(caso))]
    assert errores == []


@pytest.mark.parametrize("caso", NOMBRES)
def test_el_campo_caso_coincide_con_la_carpeta(caso):
    assert cargar(caso)["caso"] == caso


def test_acciones_y_eventos_salen_del_contrato_de_comando():
    comando = esquema_de("comando.v1.schema.json")["properties"]
    tramo = ESQUEMA["$defs"]["tramo"]["properties"]
    assert set(ESQUEMA["$defs"]["accion"]["enum"]) == set(comando["action"]["enum"]) == ACCIONES
    eventos = set(comando["event"]["enum"])
    assert set(tramo["origen"]["enum"]) - {"cuadros"} <= eventos
    assert set(ESQUEMA["properties"]["stop_con_evento"]["items"]["enum"]) <= eventos


def test_el_esquema_rechaza_un_campo_inventado():
    expectativa = cargar("C1")
    expectativa["tramos"][0]["acciones_obligatorias"] = ["AVANZAR"]
    assert list(Draft202012Validator(ESQUEMA).iter_errors(expectativa))


def test_el_esquema_pide_plazo_desde_cuando_hay_plazo():
    expectativa = cargar("C2")
    expectativa["tramos"][0]["plazo_desde"] = None
    assert list(Draft202012Validator(ESQUEMA).iter_errors(expectativa))


# --- coherencia de cada tramo ---------------------------------------------------


@pytest.mark.parametrize("caso", NOMBRES)
def test_los_tramos_son_coherentes(caso):
    nombres = [t["nombre"] for t in cargar(caso)["tramos"]]
    assert len(nombres) == len(set(nombres)), "nombres de tramo repetidos"
    for tramo in cargar(caso)["tramos"]:
        donde = f"{caso}/{tramo['nombre']}"
        permitidas = set(tramo["acciones_permitidas"])
        prohibidas = set(tramo["acciones_prohibidas"])
        assert not permitidas & prohibidas, f"{donde}: una acción permitida y prohibida a la vez"
        if tramo["plazo_desde"] is not None:
            assert tramo["plazo_desde"] in PLAZO_DESDE_POR_ORIGEN[tramo["origen"]], donde
        if "mantener_accion_cuadros" in tramo:
            assert tramo["origen"] == "cuadros", donde
        if tramo["origen"] != "cuadros":
            assert tramo["acciones_permitidas"] == ["STOP"], f"{donde}: un evento sin cuadro frena"


@pytest.mark.parametrize("caso", NOMBRES)
def test_cada_stop_con_evento_tiene_su_tramo(caso):
    expectativa = cargar(caso)
    origenes = {t["origen"] for t in expectativa["tramos"]}
    for evento in expectativa["stop_con_evento"]:
        assert evento in origenes


@pytest.mark.parametrize("caso", NOMBRES)
def test_avanzar_permitido_pide_velocidad(caso):
    for tramo in cargar(caso)["tramos"]:
        if tramo["acciones_permitidas"] == ["AVANZAR"]:
            assert "avanzar_con_velocidad" in tramo.get("condiciones", []), tramo["nombre"]


@pytest.mark.parametrize("caso", NOMBRES)
def test_todo_giro_permitido_va_hacia_zona_libre(caso):
    for tramo in cargar(caso)["tramos"]:
        if set(tramo["acciones_permitidas"]) & {"GIRAR_IZQ", "GIRAR_DER"}:
            assert "giro_hacia_zona_libre" in tramo.get("condiciones", []), tramo["nombre"]


def test_los_plazos_de_b_no_son_mas_holgados_que_las_expectativas():
    """Si B sube un plazo en plazos.yaml, podría reaccionar tarde y fallar el caso."""
    for caso in NOMBRES:
        for tramo in cargar(caso)["tramos"]:
            if tramo["plazo_desde"] == "captura" and "AVANZAR" in tramo["acciones_prohibidas"]:
                assert tramo["plazo_reaccion_ms"] >= PLAZOS["max_frame_age_ms"], tramo["nombre"]
    assert tramos("C8")["hueco"]["plazo_reaccion_ms"] >= PLAZOS["watchdog_ms"]


# --- lo que pide el ticket para cada caso -----------------------------------------


def test_c1_via_libre_avanza():
    [libre] = tramos("C1").values()
    assert libre["acciones_permitidas"] == ["AVANZAR"]
    assert set(libre["acciones_prohibidas"]) == REACCIONAR
    assert libre["plazo_reaccion_ms"] is not None


def test_c2_obstaculo_central_frena_o_gira():
    [obstaculo] = tramos("C2").values()
    assert_reacciona(obstaculo)


@pytest.mark.parametrize(("caso", "nunca"), [("C3", "GIRAR_IZQ"), ("C4", "GIRAR_DER")])
def test_c3_c4_nunca_gira_hacia_el_obstaculo(caso, nunca):
    for tramo in cargar(caso)["tramos"]:
        assert nunca in tramo["acciones_prohibidas"]
        assert nunca not in tramo["acciones_permitidas"]


def test_c5_sin_zona_libre_solo_stop():
    [sin_zona] = tramos("C5").values()
    assert_solo_stop(sin_zona)


def test_c6_debajo_del_umbral_avanza_y_encima_reacciona():
    t = tramos("C6")
    assert list(t) == ["bajo_umbral", "sobre_umbral"]
    assert t["bajo_umbral"]["acciones_permitidas"] == ["AVANZAR"]
    assert "STOP" in t["bajo_umbral"]["acciones_prohibidas"]
    assert_reacciona(t["sobre_umbral"])


def test_c7_reacciona_reanuda_y_un_cuadro_no_cambia_la_decision():
    t = tramos("C7")
    assert list(t) == ["libre", "bloqueo", "un_cuadro_libre", "bloqueo_otra_vez", "libre_otra_vez"]
    assert_reacciona(t["bloqueo"])
    assert_reacciona(t["bloqueo_otra_vez"])
    assert t["un_cuadro_libre"]["mantener_accion_cuadros"] >= 1
    assert "AVANZAR" in t["un_cuadro_libre"]["acciones_prohibidas"]
    assert t["libre_otra_vez"]["acciones_permitidas"] == ["AVANZAR"]
    assert t["libre_otra_vez"]["plazo_reaccion_ms"] is not None
    assert t["libre_otra_vez"]["mantener_accion_cuadros"] >= 1


def test_c8_sin_cuadros_stop_de_reloj_y_cuadro_viejo_rechazado():
    expectativa, t = cargar("C8"), tramos("C8")
    assert "clock" in expectativa["stop_con_evento"]
    assert t["hueco"]["origen"] == "clock"
    assert t["hueco"]["plazo_desde"] == "ultimo_cuadro"
    assert_solo_stop(t["hueco"])
    assert_solo_stop(t["cuadro_viejo"])
    assert "error_registrado" in t["cuadro_viejo"]["condiciones"]


def test_c9_cada_error_code_del_contrato_da_stop_registrado():
    percepcion = esquema_de("percepcion.v1.schema.json")
    codigos = percepcion["$defs"]["error"]["properties"]["code"]["enum"]
    t = tramos("C9")
    assert set(t) == set(codigos)
    for tramo in t.values():
        assert_solo_stop(tramo)
        assert "error_registrado" in tramo["condiciones"]


def test_c10_emergencia_enclavada_rearme_con_cuadro_fresco_y_stop_al_cerrar():
    expectativa, t = cargar("C10"), tramos("C10")
    assert {"emergency", "shutdown"} <= set(expectativa["stop_con_evento"])
    assert list(t) == [
        "antes_de_la_emergencia",
        "emergencia",
        "enclavada",
        "rearme",
        "rearme_con_cuadro_viejo",
        "rearme_con_cuadro_fresco",
        "cierre",
    ]
    for nombre in ("emergencia", "enclavada", "rearme", "rearme_con_cuadro_viejo", "cierre"):
        assert_solo_stop(t[nombre])
    assert t["emergencia"]["origen"] == "emergency"
    assert t["rearme"]["origen"] == "rearm"
    assert t["rearme_con_cuadro_fresco"]["acciones_permitidas"] == ["AVANZAR"]
    assert t["cierre"]["origen"] == "shutdown"
    assert "es_el_ultimo_comando" in t["cierre"]["condiciones"]


# --- congeladas: no se cambian para que un caso pase --------------------------------


def leer_hashes() -> dict[str, str]:
    lineas = (CASOS / "expectativas.sha256").read_text(encoding="utf-8").splitlines()
    return {ruta: sha for sha, ruta in (linea.split(maxsplit=1) for linea in lineas if linea)}


def test_las_expectativas_estan_congeladas():
    """Cambiar una expectativa pide actualizar el hash en un PR aparte (casos/README.md)."""
    hashes = leer_hashes()
    esperadas = {f"{caso}/expectativa.yaml" for caso in NOMBRES} | {"expectativa.v1.schema.json"}
    assert set(hashes) == esperadas
    cambiadas = [ruta for ruta, sha in hashes.items() if sha256_lf(CASOS / ruta) != sha]
    assert cambiadas == [], f"cambiaron sin actualizar casos/expectativas.sha256: {cambiadas}"


def test_el_readme_explica_cada_campo_y_valor():
    readme = (CASOS / "README.md").read_text(encoding="utf-8")
    tramo = ESQUEMA["$defs"]["tramo"]["properties"]
    nombres = [
        *ESQUEMA["properties"],
        *tramo,
        *tramo["origen"]["enum"],
        *(v for v in tramo["plazo_desde"]["enum"] if v),
        *tramo["condiciones"]["items"]["enum"],
    ]
    faltan = [n for n in nombres if f"`{n}`" not in readme]
    assert faltan == []
