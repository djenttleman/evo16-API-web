// EVO 16 Remote — app de barra de menú (icono junto al reloj, sin ícono en el Dock).
//
// Es el único "siempre vivo" del sistema EVO y hace tres cosas:
//   1. muestra el estado real (sondea /api/health del servicio),
//   2. enciende / apaga el servicio del puerto 3000,
//   3. y **sirve la API del puerto 3100** para otras apps — incluido el estado `offline`, que sólo
//      puede reportar quien vive fuera del servicio (o sea: esta app). Misma forma de respuesta que
//      el launcher `launcher.py`, para que un cliente no tenga que saber quién contesta.
//
// Además, si falta el agente de launchd del servicio, lo instala sola: no hay que correr nada en la
// Terminal; con la app y el repo alcanza.
//
// Canales para otras apps:
//   open -g "evo16remote://start"          (o stop / status)     ← URL scheme
//   curl -s http://127.0.0.1:3100/api/status                     ← API local (sólo loopback)
import AppKit
import Network

let kService      = "http://127.0.0.1:3000"
let kAgente       = "com.david.evo16-remote"
let kRepo         = NSString(string: "~/dev/evo16-web").expandingTildeInPath
let kPython       = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
let kAgentePath   = NSString(string: "~/Library/LaunchAgents/\(kAgente).plist").expandingTildeInPath
let kAgenteOrigen = "\(kRepo)/bin/\(kAgente).plist"
let kLogPath      = NSString(string: "~/Library/Logs/evo16-remote.log").expandingTildeInPath
let kPuertoAPI: UInt16 = 3100

@discardableResult
func shell(_ cmd: String) -> Int32 {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/bash")
    p.arguments = ["-c", cmd]
    p.standardOutput = Pipe()
    p.standardError = Pipe()
    do { try p.run() } catch { return -1 }
    p.waitUntilExit()
    return p.terminationStatus
}

// ── Servidor HTTP mínimo, sólo loopback ─────────────────────────────────────────────────────────
// No pretende ser un servidor completo: atiende un pedido por conexión, responde y cierra. Es para
// clientes locales (una extensión de REAPER, un curl, otro agente).
final class ServidorAPI {
    private var listener: NWListener?
    private let cola = DispatchQueue(label: "evo16.api.net")
    private let manejar: (String, String) -> (Int, String)      // (método, ruta) → (código, JSON)
    private(set) var disponible = false
    private(set) var motivo = "arrancando…"

    init(manejar: @escaping (String, String) -> (Int, String)) { self.manejar = manejar }

    func arrancar(puerto: UInt16) {
        let params = NWParameters.tcp
        params.requiredLocalEndpoint = NWEndpoint.hostPort(host: "127.0.0.1",
                                                           port: NWEndpoint.Port(rawValue: puerto)!)
        params.allowLocalEndpointReuse = true
        do {
            let l = try NWListener(using: params)
            l.newConnectionHandler = { [weak self] conn in self?.atender(conn) }
            l.stateUpdateHandler = { [weak self] estado in
                switch estado {
                case .ready:
                    self?.disponible = true
                    self?.motivo = "escuchando en http://127.0.0.1:\(puerto)"
                case .failed(let e):
                    self?.disponible = false
                    self?.motivo = "no pude abrir el puerto \(puerto) (\(e)) — ¿lo tiene otro proceso?"
                default:
                    break
                }
            }
            l.start(queue: cola)
            listener = l
        } catch {
            disponible = false
            motivo = "no pude abrir el puerto \(puerto): \(error)"
        }
    }

    private func atender(_ conn: NWConnection) {
        // sólo loopback: si el pedido viene de la red, se ignora
        if case let .hostPort(host, _) = conn.endpoint {
            let h = String(describing: host)
            if h != "127.0.0.1" && h != "::1" && h != "localhost" { conn.cancel(); return }
        }
        conn.start(queue: cola)
        recibir(conn, acumulado: Data())
    }

    private func recibir(_ conn: NWConnection, acumulado: Data) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, fin, error in
            guard let self else { return }
            var buf = acumulado
            if let d = data { buf.append(d) }
            if fin || error != nil || buf.count > 65536 { conn.cancel(); return }
            guard let texto = String(data: buf, encoding: .utf8) else { conn.cancel(); return }
            if let finCabecera = texto.range(of: "\r\n\r\n") {
                let primera = texto[texto.startIndex..<finCabecera.lowerBound]
                    .split(separator: "\r\n").first.map(String.init) ?? ""
                let campos = primera.split(separator: " ")
                let metodo = campos.count > 0 ? String(campos[0]).uppercased() : "GET"
                let ruta = campos.count > 1 ? String(campos[1]) : "/"
                DispatchQueue.global().async {                 // no bloquear la cola de red
                    let (codigo, cuerpo) = self.manejar(metodo, ruta)
                    self.responder(conn, codigo: codigo, json: cuerpo)
                }
            } else {
                self.recibir(conn, acumulado: buf)
            }
        }
    }

    private func responder(_ conn: NWConnection, codigo: Int, json: String) {
        let cuerpo = Data(json.utf8)
        let cabecera = "HTTP/1.1 \(codigo) \(codigo == 200 ? "OK" : "Error")\r\n"
            + "Content-Type: application/json; charset=utf-8\r\n"
            + "Content-Length: \(cuerpo.count)\r\n"
            + "Connection: close\r\n\r\n"
        var salida = Data(cabecera.utf8)
        salida.append(cuerpo)
        conn.send(content: salida, completion: .contentProcessed { _ in conn.cancel() })
    }
}

// ── La app ──────────────────────────────────────────────────────────────────────────────────────
final class App: NSObject, NSApplicationDelegate {
    private var item: NSStatusItem!
    private var estadoItem: NSMenuItem!
    private var apiItem: NSMenuItem!
    private var agenteItem: NSMenuItem!
    private var encenderItem: NSMenuItem!
    private var apagarItem: NSMenuItem!
    private var abrirItem: NSMenuItem!
    private var api: ServidorAPI!

    // estado compartido entre la UI y la API (siempre tocado desde el main queue)
    private var servicioArriba = false
    private var ultimo: [String: Any] = [:]
    private var up = false
    private var ocupado = false
    private var detalle = "consultando…"

    func applicationDidFinishLaunching(_ notification: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let menu = NSMenu()

        estadoItem = NSMenuItem(title: "EVO 16", action: nil, keyEquivalent: "")
        apiItem    = NSMenuItem(title: "API :\(kPuertoAPI)", action: nil, keyEquivalent: "")
        agenteItem = NSMenuItem(title: "Agente del servicio", action: nil, keyEquivalent: "")
        for i in [estadoItem!, apiItem!, agenteItem!] { i.isEnabled = false; menu.addItem(i) }
        menu.addItem(.separator())

        encenderItem = NSMenuItem(title: "Encender servicio", action: #selector(encender), keyEquivalent: "")
        apagarItem   = NSMenuItem(title: "Apagar servicio",  action: #selector(apagar),  keyEquivalent: "")
        abrirItem    = NSMenuItem(title: "Abrir interfaz",   action: #selector(abrir),   keyEquivalent: "")
        for i in [encenderItem!, apagarItem!, abrirItem!] { i.target = self; menu.addItem(i) }

        let instalar = NSMenuItem(title: "Instalar o actualizar el agente del servicio",
                                  action: #selector(instalarAgenteDesdeMenu), keyEquivalent: "")
        instalar.target = self
        menu.addItem(instalar)
        menu.addItem(.separator())

        let salir = NSMenuItem(title: "Salir", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        salir.target = NSApp
        menu.addItem(salir)

        item.menu = menu

        // 1) la API local: es lo que le da a otras apps el estado, incluido "offline"
        api = ServidorAPI { [weak self] metodo, ruta in
            guard let self else { return (500, "{\"error\":\"app sin estado\"}") }
            return self.atenderAPI(metodo: metodo, ruta: ruta)
        }
        api.arrancar(puerto: kPuertoAPI)

        // 2) si falta el agente de launchd del servicio, lo deja instalado (sin Terminal)
        asegurarAgente()

        pintar()
        Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { _ in self.consultar() }
        consultar()
    }

    // MARK: - estado del servicio

    private func textoDeEstado(_ payload: [String: Any]) -> String {
        let dev = (payload["device"] as? [String: Any]) ?? [:]
        var det: String
        switch (payload["state"] as? String) ?? "" {
        case "connected":
            let mv = (dev["mainVolume"] as? NSNumber)?.doubleValue ?? 0
            det = String(format: "equipo OK · main %.1f dB", mv)
        case "usb_busy":           det = "USB ocupado por la app oficial"
        case "helper_down":        det = "helper caído · reconectar"
        case "device_unreachable": det = "equipo no contesta"
        case "reconnecting":       det = "reconectando…"
        default:                   det = "servicio arriba · equipo no: \((dev["error"] as? String) ?? "?")"
        }
        if (payload["audientAppRunning"] as? Bool) == true && (payload["state"] as? String) != "usb_busy" {
            det += " · ⚠️ app oficial abierta"
        }
        return det
    }

    /// Sondeo normal (cada 2 s) — actualiza lo que ven la UI y la API.
    private func consultar() {
        guard !ocupado, let url = URL(string: kService + "/api/health") else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 3
        URLSession.shared.dataTask(with: req) { data, _, _ in
            var payload: [String: Any] = [:]
            var arriba = false
            if let d = data, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                payload = j
                arriba = true
            }
            DispatchQueue.main.async {
                self.servicioArriba = arriba
                self.ultimo = payload
                if arriba {
                    let dev = (payload["device"] as? [String: Any]) ?? [:]
                    self.up = (payload["ok"] as? Bool) ?? ((dev["connected"] as? Bool) ?? false)
                    self.detalle = self.textoDeEstado(payload)
                } else {
                    self.up = false
                    self.detalle = "servicio apagado"
                }
                self.pintar()
            }
        }.resume()
    }

    /// Lectura síncrona (para responder la API con datos frescos, no los de hace 2 s).
    @discardableResult
    private func refrescarAhora(timeout: TimeInterval = 4) -> Bool {
        guard let url = URL(string: kService + "/api/health") else { return false }
        var req = URLRequest(url: url)
        req.timeoutInterval = timeout
        let sem = DispatchSemaphore(value: 0)
        var payload: [String: Any] = [:]
        var arriba = false
        URLSession.shared.dataTask(with: req) { data, _, _ in
            if let d = data, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                payload = j
                arriba = true
            }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + timeout + 1)
        DispatchQueue.main.sync {
            self.servicioArriba = arriba
            self.ultimo = payload
            let dev = (payload["device"] as? [String: Any]) ?? [:]
            self.up = arriba && ((payload["ok"] as? Bool) ?? ((dev["connected"] as? Bool) ?? false))
            self.detalle = arriba ? self.textoDeEstado(payload) : "servicio apagado"
            self.pintar()
        }
        return arriba
    }

    private func pintar() {
        estadoItem.title = "EVO 16 · " + detalle
        apiItem.title = "API :\(kPuertoAPI) · " + ((api?.disponible ?? false) ? "activa" : (api?.motivo ?? "—"))
        if FileManager.default.fileExists(atPath: kAgentePath) {
            agenteItem.title = "Agente del servicio · instalado"
        } else if FileManager.default.fileExists(atPath: kAgenteOrigen) {
            agenteItem.title = "Agente del servicio · falta (menú de abajo)"
        } else {
            agenteItem.title = "Agente del servicio · falta el repo en ~/dev/evo16-web"
        }
        encenderItem.isEnabled = !up && !ocupado
        apagarItem.isEnabled = !ocupado
        abrirItem.isEnabled = up
        let simbolo = up ? "waveform.circle.fill" : "waveform.circle"
        let img = NSImage(systemSymbolName: simbolo, accessibilityDescription: "EVO 16")
        img?.isTemplate = true
        item.button?.image = img
        item.button?.toolTip = "EVO 16 Remote · \(detalle) · API :\(kPuertoAPI)"
        // el mismo estado que sirve la API, en un archivo (para clientes locales sin HTTP)
        escribirArchivoDeEstado(estadoDesde(servicioArriba, ultimo))
    }

    // MARK: - agente de launchd del servicio

    @objc private func instalarAgenteDesdeMenu() {
        asegurarAgente(forzar: true)
        pintar()
    }

    /// Deja el plist del servicio en ~/Library/LaunchAgents y lo carga en launchd.
    private func asegurarAgente(forzar: Bool = false) {
        let fm = FileManager.default
        if fm.fileExists(atPath: kAgentePath) && !forzar { return }
        guard fm.fileExists(atPath: kAgenteOrigen) else { return }
        try? fm.removeItem(atPath: kAgentePath)
        try? fm.copyItem(atPath: kAgenteOrigen, toPath: kAgentePath)
        let dominio = "gui/\(getuid())"
        _ = shell("launchctl bootout \(dominio)/\(kAgente) 2>/dev/null")
        _ = shell("launchctl bootstrap \(dominio) '\(kAgentePath)' 2>/dev/null")
    }

    // MARK: - acciones

    @objc private func encender() {
        ocupado = true; detalle = "encendiendo…"; pintar()
        let uid = getuid()
        DispatchQueue.global().async {
            _ = shell("launchctl kickstart gui/\(uid)/\(kAgente) 2>/dev/null")
            var espera = 0
            while !self.responde() && espera < 24 { Thread.sleep(forTimeInterval: 0.5); espera += 1 }
            if !self.responde() {                      // sin agente: lo arrancamos nosotros
                let p = Process()
                p.currentDirectoryURL = URL(fileURLWithPath: kRepo)
                p.executableURL = URL(fileURLWithPath: kPython)
                p.arguments = ["backend/main.py"]
                try? p.run()
                for _ in 0..<30 { if self.responde() { break }; Thread.sleep(forTimeInterval: 0.5) }
            }
            DispatchQueue.main.async { self.ocupado = false; self.consultar() }
        }
    }

    @objc private func apagar() {
        ocupado = true; detalle = "apagando…"; pintar()
        let uid = getuid()
        var req = URLRequest(url: URL(string: kService + "/api/service/stop")!)
        req.httpMethod = "POST"
        req.timeoutInterval = 4
        URLSession.shared.dataTask(with: req) { _, _, _ in
            DispatchQueue.global().async {
                Thread.sleep(forTimeInterval: 1.0)
                _ = shell("launchctl kill SIGTERM gui/\(uid)/\(kAgente) 2>/dev/null")
                _ = shell("pkill -f 'backend/main.py' 2>/dev/null")
                Thread.sleep(forTimeInterval: 1.5)
                _ = shell("pkill -f mac-evo16 2>/dev/null")
                DispatchQueue.main.async { self.ocupado = false; self.consultar() }
            }
        }.resume()
    }

    @objc private func abrir() {
        if let u = URL(string: kService) { NSWorkspace.shared.open(u) }
    }

    private func responde() -> Bool {
        guard let url = URL(string: kService + "/api/health") else { return false }
        var req = URLRequest(url: url)
        req.timeoutInterval = 2
        let sem = DispatchSemaphore(value: 0)
        var ok = false
        URLSession.shared.dataTask(with: req) { data, _, _ in ok = (data != nil); sem.signal() }.resume()
        _ = sem.wait(timeout: .now() + 3)
        return ok
    }

    // MARK: - API del puerto 3100 (para otras apps)

    private func atenderAPI(metodo: String, ruta: String) -> (Int, String) {
        let camino = ruta.split(separator: "?").first.map(String.init) ?? ruta
        switch (metodo, camino) {
        case ("GET", "/"):
            return (200, json(["name": "EVO 16 Remote (app de barra de menú)",
                               "purpose": "encender/apagar el servicio y reportar su estado, incluso caído",
                               "api": api?.motivo ?? "—",
                               "endpoints": ["GET /api/status", "POST /api/start",
                                             "POST /api/stop", "GET /api/logs?n=80"]]))

        case ("GET", "/api/status"), ("GET", "/api/state"):
            return (200, json(estadoAPI()))

        case ("POST", "/api/start"):
            DispatchQueue.main.async { self.encender() }
            for _ in 0..<60 {                                   // hasta ~30 s
                if self.refrescarAhora() { break }
                Thread.sleep(forTimeInterval: 0.5)
            }
            return (200, json(estadoAPI()))

        case ("POST", "/api/stop"):
            DispatchQueue.main.async { self.apagar() }
            for _ in 0..<40 {
                if !self.refrescarAhora(timeout: 1.5) { break }
                Thread.sleep(forTimeInterval: 0.4)
            }
            return (200, json(estadoAPI()))

        case ("GET", "/api/logs"):
            return (200, json(["file": kLogPath, "lines": colaDeLog(pedirN(ruta))]))

        default:
            return (404, json(["error": "ruta no encontrada",
                               "paths": ["/api/status", "/api/start", "/api/stop", "/api/logs"]]))
        }
    }

    private func pedirN(_ ruta: String) -> Int {
        guard let r = ruta.range(of: "n=") else { return 80 }
        let valor = ruta[r.upperBound...].prefix { $0.isNumber }
        return max(1, min(500, Int(valor) ?? 80))
    }

    private func estadoAPI() -> [String: Any] {
        var snap: (Bool, [String: Any]) = (false, [:])
        DispatchQueue.main.sync { snap = (self.servicioArriba, self.ultimo) }
        return estadoDesde(snap.0, snap.1)
    }

    /// Construye el estado a partir de un snapshot (función pura: se puede llamar ya estando en el
    /// main queue, sin el `sync` que haría deadlock).
    private func estadoDesde(_ arriba: Bool, _ payload: [String: Any]) -> [String: Any] {
        let estado = arriba ? ((payload["state"] as? String) ?? "connected") : "offline"
        return [
            "launcher": "app",
            "service": arriba ? "running" : "stopped",
            "state": estado,
            "ok": arriba && ((payload["ok"] as? Bool) ?? false),
            "stateDetail": arriba ? ((payload["stateDetail"] as? String) ?? "")
                                  : "el servicio no está corriendo: POST /api/start",
            "agentInstalled": FileManager.default.fileExists(atPath: kAgentePath),
            "device": payload["device"] ?? NSNull(),
            "audientAppRunning": payload["audientAppRunning"] ?? NSNull(),
            "serviceVersion": payload["version"] ?? NSNull(),
            "apiPort": Int(kPuertoAPI),
            "urls": payload["urls"] ?? ["loopback": kService],
        ]
    }

    /// El mismo estado, en un archivo, para clientes LOCALES que no quieran usar HTTP (un ReaScript
    /// lo lee con `io.open`). Incluye `updatedAtEpoch`: si está viejo, la app no está corriendo.
    private func escribirArchivoDeEstado(_ obj: [String: Any]) {
        var conMarca = obj
        let ahora = Date()
        conMarca["updatedAt"] = ISO8601DateFormatter().string(from: ahora)
        conMarca["updatedAtEpoch"] = ahora.timeIntervalSince1970
        conMarca["app"] = "EVO 16 Remote"
        guard let datos = try? JSONSerialization.data(withJSONObject: conMarca,
                                                      options: [.prettyPrinted, .sortedKeys]) else { return }
        let carpeta = NSString(string: "~/Library/Application Support/EVO16Remote").expandingTildeInPath
        try? FileManager.default.createDirectory(atPath: carpeta, withIntermediateDirectories: true)
        try? datos.write(to: URL(fileURLWithPath: "\(carpeta)/estado.json"), options: .atomic)
    }

    private func colaDeLog(_ n: Int) -> [String] {
        guard let texto = try? String(contentsOfFile: kLogPath, encoding: .utf8) else { return [] }
        return texto.split(separator: "\n").suffix(n).map(String.init)
    }

    private func json(_ obj: [String: Any]) -> String {
        guard let d = try? JSONSerialization.data(withJSONObject: obj,
                                                  options: [.prettyPrinted, .sortedKeys]),
              let s = String(data: d, encoding: .utf8) else { return "{}" }
        return s
    }

    // Pedidos de otras apps por URL: evo16remote://start | stop | status
    func application(_ application: NSApplication, open urls: [URL]) {
        for u in urls {
            let bruto = (u.host ?? "").isEmpty ? u.path : (u.host ?? "")
            switch bruto.replacingOccurrences(of: "/", with: "").lowercased() {
            case "start", "encender": encender()
            case "stop", "apagar":    apagar()
            default:                  consultar()
            }
        }
    }
}

let app = NSApplication.shared
let delegado = App()
app.delegate = delegado
app.setActivationPolicy(.accessory)
app.run()
