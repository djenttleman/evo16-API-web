"""Tests del almacén de perfiles (backend/presets.py) — sólo archivos, sin dispositivo.

Corre con:  cd backend && python3 test_presets.py

Cubre guardar/leer/listar/borrar, sobrescritura, archivos corruptos y —lo más importante— que un
nombre con barras o ".." NO pueda escribir fuera de la carpeta de perfiles.
"""

import json
import tempfile
from pathlib import Path

import presets


def run() -> bool:
    ok = fail = 0

    def check(name, got, expected):
        nonlocal ok, fail
        if got == expected:
            ok += 1
            print(f"  ✅ {name}")
        else:
            fail += 1
            print(f"  ❌ {name}: obtuve {got!r}, esperaba {expected!r}")

    with tempfile.TemporaryDirectory() as td:
        presets.PRESETS_DIR = Path(td)

        canales = [
            {
                "channel": i,
                "gain": 10 + i,
                "phantom": i == 1,
                "mute": i == 24,
                "instrument": i in (1, 2, 9, 10, 17, 18),
                "linked": i in (1, 2),
                "linkPair": [1, 2] if i in (1, 2) else None,
            }
            for i in range(1, 25)
        ]

        print("── guardar / leer ──")
        d = presets.save("Escena 1", canales)
        check("devuelve el nombre", d["name"], "Escena 1")
        check("guarda la fecha", bool(d.get("savedAt")), True)
        check("archivo en disco", (Path(td) / "Escena 1.json").is_file(), True)
        check("listado", [p["name"] for p in presets.list_presets()], ["Escena 1"])
        check("canales que vuelven", len(presets.load("Escena 1")["channels"]), 24)
        check("gain del canal 1", presets.load("Escena 1")["channels"][0]["gain"], 11)
        check("phantom del canal 1", presets.load("Escena 1")["channels"][0]["phantom"], True)

        print("\n── sobrescribir ──")
        presets.save("Escena 1", canales[:2])
        check("reescribe el mismo archivo", len(presets.load("Escena 1")["channels"]), 2)
        check("sigue habiendo un solo perfil", len(presets.list_presets()), 1)

        print("\n── nombres inválidos (no deben salir de la carpeta) ──")
        for malo in ("../fuera", "a/b", "..", "", "x" * 65, "con;punto", "  ", "a\\b"):
            try:
                presets.save(malo, canales)
                res = "PERMITIDO"
            except presets.PresetError:
                res = "rechazado"
            except Exception as e:  # noqa: BLE001
                res = f"otra excepción: {type(e).__name__}"
            check(f"{malo!r}", res, "rechazado")
        check("no se creó nada fuera", sorted(p.name for p in Path(td).iterdir()), ["Escena 1.json"])

        print("\n── errores controlados ──")
        try:
            presets.load("No existe")
            res = "cargó"
        except presets.PresetError:
            res = "error controlado"
        check("leer inexistente", res, "error controlado")
        try:
            presets.delete("No existe")
            res = "borró"
        except presets.PresetError:
            res = "error controlado"
        check("borrar inexistente", res, "error controlado")

        print("\n── archivo corrupto ──")
        (Path(td) / "roto.json").write_text("{ esto no es json")
        listado = presets.list_presets()
        check("el listado lo marca", any(p.get("error") for p in listado), True)
        try:
            presets.load("roto")
            res = "cargó"
        except presets.PresetError:
            res = "error controlado"
        check("leerlo da error controlado", res, "error controlado")

        print("── borrar ──")
        check("delete devuelve True", presets.delete("Escena 1"), True)
        check("carpeta sin perfiles", [p for p in presets.list_presets() if not p.get("error")], [])

        print("\n── exportar / importar a ubicaciones personalizadas ──")
        presets.save("Sala chica", canales)
        fuera = Path(td) / "fuera" / "mi-perfil.json"          # carpeta que no existe todavía
        destino = presets.export_preset("Sala chica", str(fuera))
        check("export crea la carpeta destino", destino.is_file(), True)
        check("export escribe el mismo JSON", json.loads(destino.read_text())["name"], "Sala chica")
        try:
            presets.export_preset("Sala chica", str(fuera))
            res = "sobrescribió"
        except presets.PresetError:
            res = "rechazado"
        check("export no pisa sin overwrite", res, "rechazado")
        check("export con overwrite=True", presets.export_preset("Sala chica", str(fuera), True).is_file(), True)
        try:
            presets.export_preset("Sala chica", str(Path(td) / "sin-extension"))
            res = "permitido"
        except presets.PresetError:
            res = "rechazado"
        check("export exige .json", res, "rechazado")

        # importar con otro nombre
        otro = presets.import_preset(str(destino), "Sala grande")
        check("import guarda en el banco", otro["name"], "Sala grande")
        check("import conserva los canales", len(presets.load("Sala grande")["channels"]), 24)
        # importar sin nombre: usa el del archivo
        check("import usa el name del archivo", presets.import_preset(str(destino))["name"], "Sala chica")
        # rechazos
        malo = Path(td) / "no-es-perfil.json"
        malo.write_text(json.dumps({"hola": 1}))
        try:
            presets.import_preset(str(malo))
            res = "importó"
        except presets.PresetError:
            res = "rechazado"
        check("import rechaza un JSON ajeno", res, "rechazado")
        try:
            presets.import_preset(str(Path(td) / "no-existe.json"))
            res = "importó"
        except presets.PresetError:
            res = "rechazado"
        check("import rechaza archivo inexistente", res, "rechazado")

        print("\n── nombres reservados ──")
        for r in ("import", "export", "IMPORT"):
            try:
                presets.save(r, canales)
                res = "PERMITIDO"
            except presets.PresetError:
                res = "rechazado"
            check(f"nombre reservado {r!r}", res, "rechazado")

    print("\n========================================")
    print(f"  Results: {ok}/{ok + fail} passed, {fail} failed")
    print("  ✅ ALMACÉN DE PERFILES OK" if fail == 0 else "  ❌ HAY FALLOS")
    return fail == 0


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
