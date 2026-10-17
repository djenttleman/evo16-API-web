import AppKit
import Network
import Security

let servicePort = ProcessInfo.processInfo.environment["EVO16_PORT"] ?? "3000"
let lifecyclePort = UInt16(ProcessInfo.processInfo.environment["EVO16_LIFECYCLE_PORT"] ?? "3100") ?? 3100
let serviceURL = URL(string: "http://127.0.0.1:\(servicePort)")!
let dataURL = ProcessInfo.processInfo.environment["EVO16_DATA_DIR"].map { URL(fileURLWithPath: $0) } ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/EVO16Remote")
let tokenURL = dataURL.appendingPathComponent("api-token")
let prefsURL = dataURL.appendingPathComponent("prefs.json")
let stateURL = dataURL.appendingPathComponent("estado.json")
let logURL = CommandLine.arguments.contains("--preview") ? dataURL.appendingPathComponent("service.log") : FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/evo16-remote.log")
let appVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "2.0.0"

func credential() throws -> String {
    try FileManager.default.createDirectory(at: dataURL, withIntermediateDirectories: true,
                                            attributes: [.posixPermissions: 0o700])
    try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: dataURL.path)
    if !FileManager.default.fileExists(atPath: tokenURL.path) {
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
            throw NSError(domain: "EVO16", code: 1, userInfo: [NSLocalizedDescriptionKey: "No se pudo crear la credencial"])
        }
        let token = Data(bytes).base64EncodedString()
        try token.write(to: tokenURL, atomically: true, encoding: .utf8)
    }
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: tokenURL.path)
    let token = try String(contentsOf: tokenURL, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
    guard token.count >= 32 else { throw NSError(domain: "EVO16", code: 2,
        userInfo: [NSLocalizedDescriptionKey: "La credencial API no es válida"] ) }
    return token
}

// Optional native-client lifecycle API. One owner, bounded requests, no browser access.
final class LifecycleAPI {
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "evo16.lifecycle")
    private var connections = 0
    private let token: String
    private let handler: (String, String) -> (Int, [String: Any])
    var changed: ((String) -> Void)?

    init(token: String, handler: @escaping (String, String) -> (Int, [String: Any])) {
        self.token = token
        self.handler = handler
    }

    func start() {
        guard listener == nil else { return }
        let params = NWParameters.tcp
        params.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: NWEndpoint.Port(rawValue: lifecyclePort)!)
        do {
            let l = try NWListener(using: params)
            l.stateUpdateHandler = { [weak self] state in
                let text: String
                switch state {
                case .ready: text = "API de encendido y apagado disponible en 127.0.0.1:\(lifecyclePort)"
                case .failed: text = "No se pudo abrir el puerto 3100. Revisa si otra app lo utiliza."
                default: return
                }
                DispatchQueue.main.async { self?.changed?(text) }
            }
            l.newConnectionHandler = { [weak self] connection in
                guard let self, self.connections < 16 else { connection.cancel(); return }
                self.connections += 1
                var finished = false
                let finish: () -> Void = {
                    if !finished { finished = true; self.connections -= 1; connection.cancel() }
                }
                connection.start(queue: self.queue)
                self.queue.asyncAfter(deadline: .now() + 5) { finish() }
                self.receive(connection, Data(), finish)
            }
            l.start(queue: queue)
            listener = l
        } catch { changed?("No se pudo abrir la API de encendido y apagado") }
    }

    func stop() { listener?.cancel(); listener = nil; changed?("API de encendido y apagado desactivada") }

    private func receive(_ conn: NWConnection, _ previous: Data, _ finish: @escaping () -> Void) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, done, error in
            guard let self else { finish(); return }
            var buffer = previous
            buffer.append(data ?? Data())
            guard buffer.count <= 16384, error == nil else { finish(); return }
            if let text = String(data: buffer, encoding: .utf8), text.contains("\r\n\r\n") {
                let lines = text.components(separatedBy: "\r\n")
                let request = lines[0].split(separator: " ").map(String.init)
                var headers = [String: String]()
                for line in lines.dropFirst() {
                    if line.isEmpty { break }
                    guard let colon = line.firstIndex(of: ":") else { finish(); return }
                    let key = line[..<colon].lowercased()
                    guard headers[key] == nil else { finish(); return }
                    headers[key] = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
                }
                guard request.count == 3 else { finish(); return }
                let result: (Int, [String: Any])
                if headers["origin"] != nil || headers["sec-fetch-site"] != nil {
                    result = (403, ["detail": "API reservada a clientes nativos"])
                } else if !["127.0.0.1:\(lifecyclePort)", "localhost:\(lifecyclePort)"].contains(headers["host"] ?? "") {
                    result = (400, ["detail": "Host no permitido"])
                } else if !self.matches(headers["authorization"] ?? "") {
                    result = (401, ["detail": "Autenticación requerida"])
                } else {
                    result = self.handler(request[0], request[1])
                }
                let body = (try? JSONSerialization.data(withJSONObject: result.1, options: [.sortedKeys])) ?? Data()
                let header = "HTTP/1.1 \(result.0) Result\r\nContent-Type: application/json\r\nContent-Length: \(body.count)\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n"
                var response = Data(header.utf8); response.append(body)
                conn.send(content: response, completion: .contentProcessed { _ in self.queue.async { finish() } })
            } else if done { finish() }
            else { self.receive(conn, buffer, finish) }
        }
    }

    private func matches(_ authorization: String) -> Bool {
        let expected = Array("Bearer \(token)".utf8), supplied = Array(authorization.utf8)
        guard expected.count == supplied.count else { return false }
        return zip(expected, supplied).reduce(UInt8(0)) { $0 | ($1.0 ^ $1.1) } == 0
    }
}

final class App: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var stateItem: NSMenuItem!
    private var powerItem: NSMenuItem!
    private var openItem: NSMenuItem!
    private var preferences: NSWindowController?
    private var httpCheck: NSButton!
    private var networkCheck: NSButton!
    private var diagnostics: NSTextField!
    private var reconnectButton: NSButton!
    private var apiDescription: NSTextField!
    private var token = ""
    private var api: LifecycleAPI?
    private var process: Process?
    private var desiredRunning = false
    private var restarting = false
    private var terminating = false
    private var httpEnabled = false
    private var exposeNetwork = false
    private var serviceUp = false
    private var deviceOK = false
    private var polling = false
    private var detail = "Servicio apagado"
    private var lastPayload: [String: Any] = [:]
    private var apiDetail = "API de encendido y apagado desactivada"
    private var testSession = CommandLine.arguments.contains("--preview")
    private var retryDelay: TimeInterval = 2
    private var retryWork: DispatchWorkItem?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Avoid two independent controllers for the same service.
        let id = Bundle.main.bundleIdentifier ?? "app.local.evo16-remote-menubar"
        if !CommandLine.arguments.contains("--preview") && NSRunningApplication.runningApplications(withBundleIdentifier: id).count > 1 { NSApp.terminate(nil); return }
        do { token = try credential() } catch {
            let alert = NSAlert(error: error); alert.runModal(); NSApp.terminate(nil); return
        }
        if let data = try? Data(contentsOf: prefsURL),
           let prefs = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            httpEnabled = prefs["apiHttp"] as? Bool ?? false
            exposeNetwork = prefs["exponerRed"] as? Bool ?? false
        }
        if !CommandLine.arguments.contains("--preview") { migrateLegacyAgents() }
        buildMenu()
        api = LifecycleAPI(token: token) { [weak self] method, path in
            var response: (Int, [String: Any]) = (503, [:])
            DispatchQueue.main.sync { response = self?.handle(method, path) ?? response }
            return response
        }
        api?.changed = { [weak self] text in self?.apiDetail = text; self?.render() }
        if httpEnabled { api?.start() }
        render()
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.poll() }
        poll()
        if CommandLine.arguments.contains("--preferences") { showPreferences() }
    }

    private func buildMenu() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let menu = NSMenu()
        stateItem = NSMenuItem(title: "Desconectado", action: nil, keyEquivalent: "")
        stateItem.isEnabled = false; menu.addItem(stateItem); menu.addItem(.separator())
        openItem = NSMenuItem(title: "Abrir interfaz", action: #selector(openUI), keyEquivalent: "")
        powerItem = NSMenuItem(title: "Encender servicio", action: #selector(togglePower), keyEquivalent: "")
        let settings = NSMenuItem(title: "Preferencias…", action: #selector(showPreferences), keyEquivalent: ",")
        for item in [openItem!, powerItem!, settings] { item.target = self; menu.addItem(item) }
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "Salir", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        quit.target = NSApp; menu.addItem(quit)
        statusItem.menu = menu
        // Native shortcuts also work while the preferences window is active.
        let mainMenu = NSMenu()
        let applicationItem = NSMenuItem()
        let applicationMenu = NSMenu()
        let shortcut = NSMenuItem(title: "Preferencias…", action: #selector(showPreferences), keyEquivalent: ",")
        shortcut.target = self
        applicationMenu.addItem(shortcut)
        let quitShortcut = NSMenuItem(title: "Salir", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        quitShortcut.target = NSApp
        applicationMenu.addItem(quitShortcut)
        applicationItem.submenu = applicationMenu
        mainMenu.addItem(applicationItem)
        NSApp.mainMenu = mainMenu
    }

    private func savePreferences() {
        let data = try? JSONSerialization.data(withJSONObject: ["apiHttp": httpEnabled, "exponerRed": exposeNetwork], options: [.sortedKeys])
        do { try data?.write(to: prefsURL, options: .atomic) }
        catch { detail = "No se pudieron guardar las preferencias" }
    }

    private func label(_ text: String, bold: Bool = false) -> NSTextField {
        let field = NSTextField(wrappingLabelWithString: text)
        field.font = bold ? .boldSystemFont(ofSize: 13) : .systemFont(ofSize: 12)
        field.textColor = bold ? .labelColor : .secondaryLabelColor
        field.isSelectable = true
        field.preferredMaxLayoutWidth = 460
        return field
    }

    @objc private func showPreferences() {
        if preferences == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 540, height: 510),
                                  styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
            window.title = testSession ? "Preferencias de EVO 16 Remote · Prueba" : "Preferencias de EVO 16 Remote"
            window.isReleasedWhenClosed = false
            let content = NSStackView()
            content.orientation = .vertical; content.alignment = .leading; content.spacing = 12
            content.translatesAutoresizingMaskIntoConstraints = false
            window.contentView!.addSubview(content)
            NSLayoutConstraint.activate([
                content.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 28),
                content.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -28),
                content.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 24),
                content.bottomAnchor.constraint(lessThanOrEqualTo: window.contentView!.bottomAnchor, constant: -24)
            ])
            content.addArrangedSubview(label("Conexión", bold: true))
            networkCheck = NSButton(checkboxWithTitle: "Permitir conexiones desde la red", target: self, action: #selector(toggleNetwork))
            content.addArrangedSubview(networkCheck)
            content.addArrangedSubview(label("Por defecto, solo este Mac puede conectarse. Cambiar esta opción reinicia el servicio. Para acceder desde otro equipo necesitas la credencial API; usa una red privada o Tailscale."))
            content.addArrangedSubview(label("Integración con otras apps", bold: true))
            content.addArrangedSubview(label("API de control: http://127.0.0.1:\(servicePort)\nLa app debe permanecer abierta para controlar el equipo."))
            httpCheck = NSButton(checkboxWithTitle: "Permitir encender y apagar por HTTP", target: self, action: #selector(toggleHTTP))
            content.addArrangedSubview(httpCheck)
            apiDescription = label(apiDetail); content.addArrangedSubview(apiDescription)
            let copy = NSButton(title: "Copiar credencial API", target: self, action: #selector(copyToken))
            let folder = NSButton(title: "Abrir carpeta de integración", target: self, action: #selector(openData))
            let integrationButtons = NSStackView(views: [copy, folder]); integrationButtons.spacing = 10
            content.addArrangedSubview(integrationButtons)
            content.addArrangedSubview(label("Diagnóstico", bold: true))
            diagnostics = label(detail); content.addArrangedSubview(diagnostics)
            reconnectButton = NSButton(title: "Reconectar equipo", target: self, action: #selector(reconnectDevice))
            let logs = NSButton(title: "Abrir registro", target: self, action: #selector(openLog))
            let diagnosticButtons = NSStackView(views: [reconnectButton!, logs]); diagnosticButtons.spacing = 10
            content.addArrangedSubview(diagnosticButtons)
            content.addArrangedSubview(label(testSession ? "Prueba de software · Sin verificación física de la interfaz" : "EVO 16 Remote \(appVersion) · Protocolo verificado el 15–16 de octubre de 2026"))
            preferences = NSWindowController(window: window)
            window.center()
        }
        render()
        NSApp.activate(ignoringOtherApps: true)
        preferences?.showWindow(nil)
        preferences?.window?.makeKeyAndOrderFront(nil)
    }

    @objc private func copyToken() { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(token, forType: .string) }
    @objc private func openData() { NSWorkspace.shared.open(dataURL) }
    @objc private func openLog() { NSWorkspace.shared.open(logURL) }
    @objc private func openUI() { NSWorkspace.shared.open(serviceURL) }
    @objc private func togglePower() { desiredRunning ? stop() : start() }
    @objc private func toggleHTTP() { httpEnabled = httpCheck.state == .on; savePreferences(); httpEnabled ? api?.start() : api?.stop(); render() }
    @objc private func toggleNetwork() {
        exposeNetwork = networkCheck.state == .on; savePreferences()
        if desiredRunning { restarting = true; stop(keepDesired: true) }
        render()
    }

    private func launchConfiguration() throws -> (URL, [String], URL?) {
        let resources = Bundle.main.resourceURL!
        let bundled = resources.appendingPathComponent("service/EVO16Service")
        if FileManager.default.isExecutableFile(atPath: bundled.path) { return (bundled, [], nil) }
        let data = try Data(contentsOf: resources.appendingPathComponent("Development.plist"))
        let config = try PropertyListSerialization.propertyList(from: data, format: nil) as! [String: String]
        guard let python = config["python"], let repo = config["repo"] else {
            throw NSError(domain: "EVO16", code: 3, userInfo: [NSLocalizedDescriptionKey: "Falta el servicio incluido en la app"])
        }
        return (URL(fileURLWithPath: python), [repo + "/backend/main.py"], URL(fileURLWithPath: repo))
    }

    private func start() {
        guard process == nil, !terminating else { return }
        desiredRunning = true; retryWork?.cancel()
        do {
            let (executable, arguments, directory) = try launchConfiguration()
            try FileManager.default.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            if !FileManager.default.fileExists(atPath: logURL.path) { FileManager.default.createFile(atPath: logURL.path, contents: nil) }
            let log = try FileHandle(forWritingTo: logURL)
            try log.seekToEnd()
            let p = Process()
            p.executableURL = executable; p.arguments = arguments; p.currentDirectoryURL = directory
            var environment = ProcessInfo.processInfo.environment
            environment["EVO16_PARENT_PID"] = String(getpid())
            environment["EVO16_HOST"] = exposeNetwork ? "0.0.0.0" : "127.0.0.1"
            environment["EVO16_DATA_DIR"] = dataURL.path
            environment.removeValue(forKey: "EVO16_API_TOKEN")
            environment["PYTHONUNBUFFERED"] = "1"
            p.environment = environment; p.standardOutput = log; p.standardError = log
            p.terminationHandler = { [weak self] ended in
                DispatchQueue.main.async {
                    guard let self, self.process === ended else { return }
                    self.process = nil; self.serviceUp = false; self.deviceOK = false
                    if self.restarting { self.restarting = false; self.start() }
                    else if self.desiredRunning && !self.terminating {
                        self.detail = "El servicio se cerró (\(ended.terminationStatus)). Reintentando…"
                        let work = DispatchWorkItem { [weak self] in self?.start() }
                        self.retryWork = work
                        DispatchQueue.main.asyncAfter(deadline: .now() + self.retryDelay, execute: work)
                        self.retryDelay = min(30, self.retryDelay * 2)
                    } else { self.detail = "Servicio apagado" }
                    self.render()
                }
            }
            process = p
            do { try p.run() } catch { process = nil; throw error }
            try? log.close()
            detail = "Encendiendo servicio…"; render()
            poll()
        } catch { desiredRunning = false; detail = "No se pudo iniciar: \(error.localizedDescription)"; render() }
    }

    private func stop(keepDesired: Bool = false) {
        desiredRunning = keepDesired; retryWork?.cancel()
        guard let owned = process else {
            if restarting { restarting = false; start() }
            else { detail = "Servicio apagado"; render() }
            return
        }
        detail = "Apagando servicio…"; render()
        owned.terminate()
        DispatchQueue.global().asyncAfter(deadline: .now() + 5) {
            if owned.isRunning { kill(owned.processIdentifier, SIGKILL) }
        }
    }

    private func request(_ path: String, method: String = "GET", completion: @escaping (Data?, HTTPURLResponse?) -> Void) {
        var req = URLRequest(url: serviceURL.appendingPathComponent(path))
        req.httpMethod = method; req.timeoutInterval = 3
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        URLSession.shared.dataTask(with: req) { data, response, _ in completion(data, response as? HTTPURLResponse) }.resume()
    }

    @objc private func reconnectDevice() {
        guard serviceUp else { return }
        request("api/reconnect", method: "POST") { [weak self] _, _ in DispatchQueue.main.async { self?.poll() } }
    }

    private func poll() {
        guard !polling else { return }
        polling = true
        request("api/health") { [weak self] data, response in
            DispatchQueue.main.async {
                guard let self else { return }
                self.polling = false
                self.serviceUp = response?.statusCode == 200
                if self.serviceUp, let data,
                   let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    self.testSession = self.testSession || payload["testMode"] as? Bool == true
                    self.lastPayload = payload; self.deviceOK = payload["ok"] as? Bool ?? false
                    self.detail = payload["stateDetail"] as? String ?? "Esperando equipo"
                    self.retryDelay = 2
                } else {
                    self.lastPayload = [:]; self.deviceOK = false
                    if self.process != nil { self.detail = "Esperando respuesta del servicio…" }
                }
                self.render()
            }
        }
    }

    private func snapshot() -> [String: Any] {
        return ["app": "EVO 16 Remote", "appVersion": appVersion, "testMode": testSession,
                "service": serviceUp ? "running" : "stopped",
                "state": serviceUp ? lastPayload["state"] ?? "not_ready" : desiredRunning ? "not_ready" : "offline",
                "ok": serviceUp && deviceOK, "stateDetail": detail,
                "device": lastPayload["device"] ?? NSNull(),
                "serviceVersion": lastPayload["version"] ?? NSNull(),
                "audientAppRunning": lastPayload["audientAppRunning"] ?? false,
                "updatedAtEpoch": Date().timeIntervalSince1970,
                "apiHttp": httpEnabled, "exponerRed": exposeNetwork,
                "urls": ["loopback": serviceURL.absoluteString],
                "integration": ["tokenFile": tokenURL.path, "urlScheme": "evo16remote://start|stop|status",
                                "lifecycle": httpEnabled ? "http://127.0.0.1:\(lifecyclePort)" : NSNull()]]
    }

    private func render() {
        guard statusItem != nil else { return }
        let connectionStatus = serviceUp && deviceOK ? "Conectado" : "Desconectado"
        stateItem.title = connectionStatus
        powerItem.title = desiredRunning ? "Apagar servicio" : "Encender servicio"
        openItem.isEnabled = serviceUp
        statusItem.button?.image = NSImage(systemSymbolName: deviceOK ? "waveform.circle.fill" : "waveform.circle", accessibilityDescription: "EVO 16: \(connectionStatus)")
        statusItem.button?.image?.isTemplate = true
        statusItem.button?.toolTip = connectionStatus
        httpCheck?.state = httpEnabled ? .on : .off
        networkCheck?.state = exposeNetwork ? .on : .off
        diagnostics?.stringValue = (testSession ? "PRUEBA · " : "") + detail
        reconnectButton?.isEnabled = serviceUp
        apiDescription?.stringValue = apiDetail
        if let data = try? JSONSerialization.data(withJSONObject: snapshot(), options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: stateURL, options: .atomic)
        }
    }

    private func handle(_ method: String, _ path: String) -> (Int, [String: Any]) {
        switch (method, path.split(separator: "?").first.map(String.init) ?? path) {
        case ("GET", "/api/status"): return (200, snapshot())
        case ("POST", "/api/start"): start(); return (202, snapshot())
        case ("POST", "/api/stop"): stop(); return (202, snapshot())
        default: return (404, ["detail": "Ruta no encontrada"])
        }
    }

    private func migrateLegacyAgents() {
        // These labels belong to this project. Unload them without broad process-name matching.
        for label in ["com.david.evo16-web", "com.david.evo16-remote", "com.david.evo16-launcher"] {
            let plist = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/\(label).plist")
            if FileManager.default.fileExists(atPath: plist.path) {
                let p = Process(); p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
                p.arguments = ["bootout", "gui/\(getuid())/\(label)"]
                p.standardOutput = FileHandle.nullDevice; p.standardError = FileHandle.nullDevice
                do { try p.run(); p.waitUntilExit() } catch { continue }
                // Preserve a backup, prevent RunAtLoad from resurrecting it at next login.
                try? FileManager.default.moveItem(at: plist, to: plist.appendingPathExtension("deprecated"))
            }
        }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls where url.scheme == "evo16remote" {
            switch url.host {
            case "start": start()
            case "stop": stop()
            case "preferences": showPreferences()
            default: poll()
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        terminating = true; desiredRunning = false; retryWork?.cancel(); api?.stop()
        if let owned = process, owned.isRunning {
            owned.terminate()
            let until = Date().addingTimeInterval(5)
            while owned.isRunning && Date() < until { Thread.sleep(forTimeInterval: 0.05) }
            if owned.isRunning { kill(owned.processIdentifier, SIGKILL) }
        }
        serviceUp = false; deviceOK = false; detail = "App cerrada"; render()
    }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
