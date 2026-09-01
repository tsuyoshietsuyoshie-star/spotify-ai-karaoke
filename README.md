# 🎤 Spotify AI Karaoke & Cosmic Visualizer (v8.6)

> **Die modernste Echtzeit-Karaoke- & Visualizer-App für Spotify mit 48kHz-DSP-Audio-Uhr, prosodischer Silbenberechnung und lokaler elastischer Synchronisation!**

---

## 🌟 Was macht diese App so besonders?

Klassische Karaoke-Programme scrollen Liedtexte oft nur mit einer starren Stoppuhr herunter. Diese App nutzt **echte digitale Signalverarbeitung (DSP)** und **physiologische Gesangsberechnung**, um den Text perfekt an die Musik und den Sänger anzupassen:

* 🎵 **3-Stufige Master-Lyrics-Hierarchie:**
  1. **Tier 1 (Enhanced Karaoke):** Echte Silben-Zeiten (`<mm:ss.xx>`) aus weltweiten Karaoke-Datenbanken.
  2. **Tier 2 (Offizielle Spotify Studio-Lyrics):** $100\,\%$ farbsynchrone Studio-Texte direkt aus deinem Spotify-Account.
  3. **Tier 3 (LRCLIB Global Sync):** Sekunden- und zeilengenaue Fallback-Datenbank.
* ⚡ **Ultra-Fast Parallel Race Engine:** Liedtexte laden bei jedem Songwechsel in **unter 0,3 bis 0,5 Sekunden**!
* ⏱️ **17-Phasen DSP Audio-Uhr:** Greift das 48kHz-Windows-Audio direkt ab, gleicht Bluetooth-/Hardware-Verzögerungen in Echtzeit aus und schützt vor Werbe- und Pausen-Hängern.
* 🧠 **Prosodische Silben- & Wortdehnungs-Engine:** Erkennt Hook-Wörter wie *„Ceeeleeebraaate“* und dehnt sie musikalisch ($2{,}5\text{s}$), während Füllwörter (*„on“, „to“*) blitzschnell komprimiert werden.
* 🛡️ **Phrase-Lock & 5-Sensor-Voting (Michael-Jackson-Schutz):** Erkennt echte Gesangsstimmen und ignoriert Atemgeräusche (*„Hoo!“*), Schnipsen oder Beckenschläge. Die Zeilengrenzen bleiben wie feste Brückenpfeiler im Takt.
* 🎛️ **Hardware-Latenz-Entkopplung:** Kalibrierte Profile für Windows PC (WASAPI $+400\text{ms}$), Raspberry Pi 5 (ALSA $+80\text{ms}$) und USB-Studio-Interfaces ($+35\text{ms}$).
* 🌌 **60 FPS Sci-Fi Cosmic Visualizer:** Flüssige Shader-Animationen mit Live-DSP-Telemetrie-HUD (<kbd>D</kbd>).

---

## 🚀 Schnellstart (In 2 Minuten startklar)

### 1. Voraussetzungen
* **Windows 10 / 11**
* **Python 3.10 oder neuer**
* **Spotify Desktop App** (muss auf dem PC laufen)

### 2. Installation
1. Lade das Projekt herunter oder klone es mit Git:
   ```bash
   git clone https://github.com/tsuyoshietsuyoshie-star/spotify-ai-karaoke.git
   cd spotify-ai-karaoke
   ```
2. Installiere die benötigten Python-Pakete:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Starten
Starte einfach die Datei **[`Spotify/start_spotify_karaoke.bat`](file:///c:/Users/Hermeling/Desktop/Karaoke/Spotify/start_spotify_karaoke.bat)** per Doppelklick!

---

## 🍪 Spotify Cookie (`sp_dc`) einrichten (Für Dummies)

> [!NOTE]
> **Warum brauche ich den `sp_dc`-Cookie?**  
> Mit diesem Cookie kann die App die **offiziellen, farbcodierten Studio-Texte von Spotify** direkt für deinen Account abrufen.  
> *(Wenn du keinen Cookie einträgst, nutzt die App automatisch die kostenlose LRCLIB-Datenbank).* Bedenke aber das Timing der Absätze von Spotify genauer sind.

### 📁 Schritt 1: Konfigurationsdatei vorbereiten
1. Gehe in den Ordner `Spotify`.
2. Du findest dort die Datei `spotify_config.example.json`.
3. Erstelle eine Kopie dieser Datei und benenne sie um in:  
   👉 **`spotify_config.json`**

---

### 🔍 Schritt 2: Deinen `sp_dc`-Cookie im Browser kopieren

Wähle deinen Browser aus und folge der einfachen Anleitung:

#### 🌐 In Google Chrome / Microsoft Edge / Brave:
1. Öffne deinen Browser und gehe auf: **[open.spotify.com](https://open.spotify.com)**
2. Melde dich mit deinem normalen Spotify-Konto an.
3. Drücke auf deiner Tastatur die Taste **<kbd>F12</kbd>** *(oder mache einen Rechtsklick auf die Seite ➔ „Untersuchen“)*.
4. Oben in der Entwicklerleiste klickst du auf den Reiter **`Anwendung`** *(bzw. `Application`)*.  
   *(Falls du den Reiter nicht siehst, klicke ganz rechts auf die zwei kleinen Pfeile `>>`)*.
5. Links im Menü klappst du **`Cookies`** auf und klickst auf **`https://open.spotify.com`**.
6. In der Liste suchst du nach dem Namen **`sp_dc`**.
7. Doppelklicke in die Spalte **`Wert`** *(Value)* und kopiere den langen Code (beginnt meist mit `AQB...`).

---

#### 🦊 In Mozilla Firefox:
1. Gehe auf **[open.spotify.com](https://open.spotify.com)** und logge dich ein.
2. Drücke **<kbd>F12</kbd>** *(oder Rechtsklick ➔ „Untersuchen“)*.
3. Klicke oben auf den Reiter **`Web-Speicher`** *(Storage)*.
4. Klappe links **`Cookies`** auf und wähle **`https://open.spotify.com`** aus.
5. Suche nach **`sp_dc`**, doppelklicke auf den Wert und kopiere ihn.

---

#### 🧭 In Apple Safari (Mac):
1. Öffne in Safari die **Einstellungen** ➔ **Erweitert** ➔ Setze ein Häkchen bei *„Menü ‚Entwickler‘ in der Menüleiste anzeigen“*.
2. Gehe auf **[open.spotify.com](https://open.spotify.com)** und logge dich ein.
3. Mache einen Rechtsklick ➔ **Element Informationen**.
4. Gehe auf **Speicher** ➔ **Cookies** ➔ Kopiere den Wert von **`sp_dc`**.

---

### 💾 Schritt 3: Cookie in die Datei einfügen

Öffne deine Datei `Spotify/spotify_config.json` mit dem Windows-Editor (Notepad) und füge deinen Cookie ein:

```json
{
  "sp_dc": "AQBrvH2P9tCmVCODWq1nkR0BPAUDbQXgcd0SQDIhBd8h..."
}
```

Speichere die Datei ab – **fertig!** 🎉

---

## ⌨️ Tastatur-Shortcuts & Steuerung

Du kannst die App während der Musikwiedergabe komplett über die Tastatur steuern:

| Taste | Aktion | Beschreibung |
| :---: | :--- | :--- |
| **<kbd>F11</kbd>** | **Vollbildmodus** | Schaltet zwischen Fenster und randlosem Vollbild-Kino um. |
| **<kbd>H</kbd>** | **UI Ausblenden** | Versteckt alle Buttons oben rechts für ein $100\,\%$ sauberes Bild. |
| **<kbd>D</kbd>** | **DSP-Diagnose-HUD** | Blendet das Live-Telemetriefenster mit Latenz, Onsets & Confidence ein. |
| **<kbd>T</kbd>** oder **<kbd>S</kbd>** | **⚡ Tap-Sync Anchor** | Erzeugt beim ersten gesungenen Wort einen festen Timing-Ankerpunkt. |
| **<kbd>◀</kbd> / <kbd>▶</kbd>** | **Feineinstellung** | Verschiebt das globale Timing um $\pm 0{,}1\text{ Sekunden}$. |
| **<kbd>Shift</kbd> + <kbd>◀</kbd> / <kbd>▶</kbd>** | **Schnelleinstellung** | Verschiebt das globale Timing um $\pm 0{,}5\text{ Sekunden}$. |
| **<kbd>R</kbd>** | **Reset** | Setzt den Offset auf den Standard deines Hardware-Profils zurück. |

---

## 🎛️ Hardware-Latenz-Profile (`hardware_profiles.json`)

Die App trennt Anzeigelatenz sauber von der musikalischen Logik:

* **`windows_pc_wasapi` ($+0{,}400\text{s}$):** Optimiert für Windows PC mit GPU-Beschleunigung und WebView2.
* **`raspberry_pi_alsa` ($+0{,}080\text{s}$):** Ultra-Low-Latency für Raspberry Pi 5 über ALSA & HDMI.
* **`usb_studio_interface` ($+0{,}035\text{s}$):** Nahezu verzögerungsfrei für externe ASIO/USB-Audio-Interfaces.

---

## ❓ FAQ & Fehlerbehebung

<details>
<summary><b>1. Die App findet keine Lyrics für meinen Song?</b></summary>
Manche brandneue oder sehr unbekannte Songs haben noch keine synchronisierten Texte in Spotify oder LRCLIB. Die App zeigt dann den Live-Cosmic-Visualizer an, bis der nächste Song startet.
</details>

<details>
<summary><b>2. Wie aktualisiere ich meinen Cookie, wenn er abläuft?</b></summary>
Spotify-Cookies halten in der Regel viele Monate. Sollte er einmal ablaufen, kopierst du dir einfach wie oben beschrieben einen neuen <code>sp_dc</code>-Wert und ersetzt ihn in deiner <code>spotify_config.json</code>.
</details>

<details>
<summary><b>3. Ist mein Cookie sicher?</b></summary>
<b>Ja!</b> Deine <code>spotify_config.json</code> wird ausschließlich lokal auf deinem eigenen Computer verarbeitet. Die <code>.gitignore</code>-Datei verhindert automatisch, dass die Datei jemals versehentlich auf GitHub hochgeladen wird.
</details>

---

## 📄 Lizenz

Dieses Projekt steht unter der **MIT-Lizenz**. Du darfst es kostenlos für private Zwecke nutzen, modifizieren und weiterentwickeln.
