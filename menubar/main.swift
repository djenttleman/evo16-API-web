// EVO 16 Remote — app de barra de menú (icono junto al reloj, sin ícono en el Dock).
//
// Es el único "siempre vivo" del sistema EVO y el único punto de control del ciclo de vida:
//   • muestra el estado real en la barra de menú (sondea /api/health del servicio),
//   • enciende / apaga el servicio del puerto 3000,
//   • y acepta pedidos de OTRAS apps por URL, sin exponer ningún endpoint propio:
//         open -g "evo16remote://start"      (o stop / status)
//
// No habla con el equipo: eso lo hace el servicio (y su API de control en :3000).
import AppKit

let kService = "http://127.0.0.1:3000"
let kAgent   = "com.david.evo16-remote"
let kRepo    = NSString(string: "~/dev/evo16-web").expandingTildeInPath
let kPython  = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

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

final class App: NSObject, NSApplicationDelegate {
    private var item: NSStatusItem!
    private var estadoItem: NSMenuItem!
    private var encenderItem: NSMenuItem!
    private var apagarItem: NSMenuItem!
    private var abrirItem: NSMenuItem!
    private var up = false
    private var ocupado = false
    private var detalle = "consultando…"

    func applicationDidFinishLaunching(_ notification: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let menu = NSMenu()

        estadoItem = NSMenuItem(title: "EVO 16", action: nil, keyEquivalent: "")
        estadoItem.isEnabled = false
        menu.addItem(estadoItem)
        menu.addItem(.separator())

        encenderItem = NSMenuItem(title: "Encender servicio", action: #selector(encender), keyEquivalent: "")
        apagarItem   = NSMenuItem(title: "Apagar servicio",  action: #selector(apagar),  keyEquivalent: "")
        abrirItem    = NSMenuItem(title: "Abrir interfaz",   action: #selector(abrir),   keyEquivalent: "")
        for i in [encenderItem!, apagarItem!, abrirItem!] { i.target = self; menu.addItem(i) }

        menu.addItem(.separator())
        let salir = NSMenuItem(title: "Salir", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        salir.target = NSApp
        menu.addItem(salir)

        item.menu = menu
        pintar()
        Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { _ in self.consultar() }
        consultar()
    }

    // MARK: - estado

    private func consultar() {
        guard !ocupado, let url = URL(string: kService + "/api/health") else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 3
        URLSession.shared.dataTask(with: req) { data, _, _ in
            var nuevoUp = false
            var det = "servicio apagado"
            if let d = data, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                let dev = (j["device"] as? [String: Any]) ?? [:]
                nuevoUp = (dev["connected"] as? Bool) ?? false
                if nuevoUp {
                    let mv = (dev["mainVolume"] as? NSNumber)?.doubleValue ?? 0
                    det = String(format: "equipo OK · main %.1f dB", mv)
                } else {
                    det = "servicio arriba · equipo no: \((dev["error"] as? String) ?? "?")"
                }
                if (j["audientAppRunning"] as? Bool) == true { det += " · ⚠️ app oficial abierta" }
            }
            DispatchQueue.main.async {
                self.up = nuevoUp
                self.detalle = det
                self.pintar()
            }
        }.resume()
    }

    private func pintar() {
        estadoItem.title = "EVO 16 · " + detalle
        encenderItem.isEnabled = !up && !ocupado
        apagarItem.isEnabled = !ocupado
        abrirItem.isEnabled = up
        let simbolo = up ? "waveform.circle.fill" : "waveform.circle"
        let img = NSImage(systemSymbolName: simbolo, accessibilityDescription: "EVO 16")
        img?.isTemplate = true
        item.button?.image = img
        item.button?.toolTip = "EVO 16 Remote · " + detalle
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

    // MARK: - acciones

    @objc private func encender() {
        ocupado = true; detalle = "encendiendo…"; pintar()
        let uid = getuid()
        DispatchQueue.global().async {
            _ = shell("launchctl kickstart gui/\(uid)/\(kAgent) 2>/dev/null")
            var espera = 0
            while !self.responde() && espera < 24 { Thread.sleep(forTimeInterval: 0.5); espera += 1 }
            if !self.responde() {                      // sin agente instalado: lo arrancamos nosotros
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
                _ = shell("launchctl kill SIGTERM gui/\(uid)/\(kAgent) 2>/dev/null")
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
