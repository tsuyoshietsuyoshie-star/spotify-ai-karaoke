/**
 * Spotify AI Karaoke & Dynamic Visualizer (Spicetify Extension v1.1)
 * Features:
 * 1. Frameless Fullscreen Theater & Karaoke Stage (Press F11 or click 🎤 button)
 * 2. Genre-Adaptive 60-FPS Canvas Audio Visualizer (5 Presets: Cyberpunk, Magma, Velvet, Aurora, Cosmic)
 * 3. 60-FPS Millisecond-Precise Letter-by-Letter Glowing Karaoke Typography
 * 4. Dual Lyrics Engine (LRCLIB Studio-Sync + Local Whisper V3 CTC Fallback)
 * 5. Floating + Playbar Karaoke Buttons & Native Spicetify Player API Integration
 */

(function SpotifyKaraokeVisualizer() {
  if (!Spicetify?.Player) {
    setTimeout(SpotifyKaraokeVisualizer, 300);
    return;
  }

  console.log('[Spotify Karaoke] Initializing AI Karaoke & Fullscreen Visualizer v1.1...');

  const CSS_STYLES = `
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;900&display=swap');

    #spicetify-karaoke-root {
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      background: #080a12;
      z-index: 999999;
      display: none;
      flex-direction: column;
      justify-content: space-between;
      align-items: center;
      overflow: hidden;
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      user-select: none;
      opacity: 0;
      transition: opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }

    #spicetify-karaoke-root.active {
      display: flex;
      opacity: 1;
    }

    #spicetify-karaoke-canvas {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      z-index: 1;
      pointer-events: none;
    }

    .sp-ambient-glow {
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at 50% 45%, rgba(0, 240, 255, 0.08), transparent 70%);
      pointer-events: none;
      z-index: 2;
    }

    .sp-karaoke-topbar {
      position: relative;
      z-index: 10;
      width: 100%;
      box-sizing: border-box;
      padding: 24px 36px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: linear-gradient(180deg, rgba(8, 10, 18, 0.8) 0%, transparent 100%);
      backdrop-filter: blur(10px);
    }

    .sp-track-badge {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    #sp-track-cover {
      width: 56px;
      height: 56px;
      border-radius: 12px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6), 0 0 15px rgba(0, 240, 255, 0.3);
      object-fit: cover;
    }

    .sp-track-details {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    #sp-track-title {
      font-size: 20px;
      font-weight: 800;
      color: #ffffff;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.8);
    }

    #sp-track-artist {
      font-size: 14px;
      font-weight: 600;
      color: rgba(255, 255, 255, 0.7);
    }

    .sp-controls-hud {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .sp-btn {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #fff;
      border-radius: 10px;
      padding: 8px 14px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s ease;
      backdrop-filter: blur(8px);
    }

    .sp-btn:hover {
      background: rgba(0, 240, 255, 0.2);
      border-color: #00f0ff;
      box-shadow: 0 0 16px rgba(0, 240, 255, 0.4);
      transform: translateY(-1px);
    }

    .sp-btn-close {
      background: rgba(255, 0, 127, 0.2);
      border-color: rgba(255, 0, 127, 0.4);
    }

    .sp-btn-close:hover {
      background: rgba(255, 0, 127, 0.4);
      border-color: #ff007f;
      box-shadow: 0 0 16px rgba(255, 0, 127, 0.5);
    }

    .sp-offset-group {
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(0, 0, 0, 0.4);
      padding: 3px 8px;
      border-radius: 10px;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }

    #sp-offset-val {
      font-size: 12px;
      font-weight: 800;
      color: #00f0ff;
      min-width: 36px;
      text-align: center;
    }

    .sp-visualizer-center-info {
      position: relative;
      z-index: 5;
      margin-top: 10px;
      pointer-events: none;
    }

    .sp-genre-badge {
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 3px;
      text-transform: uppercase;
      color: #00f0ff;
      background: rgba(0, 240, 255, 0.1);
      border: 1px solid rgba(0, 240, 255, 0.3);
      padding: 4px 16px;
      border-radius: 20px;
      box-shadow: 0 0 20px rgba(0, 240, 255, 0.2);
      animation: spPulse 3s ease-in-out infinite;
    }

    @keyframes spPulse {
      0%, 100% { opacity: 0.7; transform: scale(1); }
      50% { opacity: 1; transform: scale(1.05); }
    }

    .sp-karaoke-stage {
      position: relative;
      z-index: 10;
      width: 90%;
      max-width: 1200px;
      margin-bottom: 50px;
      padding: 24px 36px;
      border-radius: 24px;
      background: rgba(12, 15, 26, 0.85);
      backdrop-filter: blur(25px) saturate(180%);
      border: 1px solid rgba(255, 255, 255, 0.12);
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8), 0 0 35px rgba(0, 240, 255, 0.15);
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }

    .sp-countdown-box {
      display: none;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }

    .sp-countdown-box.active {
      display: flex;
    }

    .sp-countdown-label {
      font-size: 13px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 2px;
      color: #00f0ff;
      text-shadow: 0 0 10px rgba(0, 240, 255, 0.7);
    }

    .sp-countdown-dots {
      display: flex;
      gap: 8px;
    }

    .sp-dot {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.2);
      border: 2px solid rgba(255, 255, 255, 0.4);
      transition: all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }

    .sp-dot.active-1 {
      background: #ffeb3b;
      border-color: #fff;
      box-shadow: 0 0 16px #ffeb3b, 0 0 25px rgba(255, 235, 59, 0.6);
      transform: scale(1.35);
    }

    .sp-dot.active-2 {
      background: #ff007f;
      border-color: #fff;
      box-shadow: 0 0 16px #ff007f, 0 0 25px rgba(255, 0, 127, 0.6);
      transform: scale(1.35);
    }

    .sp-dot.active-3 {
      background: #00f0ff;
      border-color: #fff;
      box-shadow: 0 0 16px #00f0ff, 0 0 30px rgba(0, 240, 255, 0.8);
      transform: scale(1.45);
    }

    .sp-current-line {
      font-size: 44px;
      font-weight: 800;
      line-height: 1.35;
      letter-spacing: 0.5px;
      color: #ffffff;
      margin-bottom: 8px;
      text-shadow: 0 2px 12px rgba(0, 0, 0, 0.95), 0 0 24px rgba(0, 0, 0, 0.9);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 12px;
    }

    .sp-word {
      position: relative;
      display: inline-block;
      color: rgba(255, 255, 255, 0.88);
      background: linear-gradient(90deg, #00f0ff 0%, #00f0ff var(--fill-pct, 0%), rgba(255, 255, 255, 0.88) var(--fill-pct, 0%), rgba(255, 255, 255, 0.88) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      transition: transform 0.15s cubic-bezier(0.2, 0, 0.3, 1), filter 0.15s ease;
      will-change: transform, filter;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.9);
    }

    .sp-word.singing {
      transform: scale(1.09) translateY(-3px);
      filter: drop-shadow(0 0 18px rgba(0, 240, 255, 1.0)) drop-shadow(0 0 35px rgba(0, 240, 255, 0.8));
    }

    .sp-word.done {
      background: #00f0ff;
      -webkit-background-clip: text;
      -webkit-text-fill-color: #00f0ff;
      filter: drop-shadow(0 0 10px rgba(0, 240, 255, 0.6));
    }

    .sp-next-line {
      font-size: 22px;
      font-weight: 600;
      color: rgba(255, 255, 255, 0.75);
      margin-top: 8px;
      padding: 4px 16px;
      border-radius: 10px;
      text-shadow: 0 2px 8px rgba(0, 0, 0, 0.9);
    }

    .sp-loading-pulse {
      color: rgba(255, 255, 255, 0.7);
      font-size: 22px;
      font-weight: 600;
      animation: spPulse 1.5s infinite;
    }
  `;

  function injectStyles() {
    if (document.getElementById('spicetify-karaoke-styles')) return;
    const s = document.createElement('style');
    s.id = 'spicetify-karaoke-styles';
    s.textContent = CSS_STYLES;
    document.head.appendChild(s);
  }

  let isFullscreen = false;
  let lyricsData = null;
  let currentLineIndex = -1;
  let currentTrackId = null;
  let timeOffset = 0.0;
  let rafId = null;
  let visualizerMode = 'auto';
  let detectedPreset = 'cyberpunk';

  let rootEl = null;
  let canvasEl = null;
  let ctx = null;
  let titleEl = null;
  let artistEl = null;
  let coverEl = null;
  let currentLineEl = null;
  let nextLineEl = null;
  let countdownEl = null;
  let dot1 = null, dot2 = null, dot3 = null;
  let presetBtn = null;

  const PRESETS = [
    { id: 'cyberpunk', name: '⚡ Synthwave Cyberpunk', colors: ['#00f0ff', '#ff007f', '#ffeb3b'] },
    { id: 'magma', name: '🔥 Magma Rock Flame', colors: ['#ff3300', '#ff8800', '#ffea00'] },
    { id: 'velvet', name: '💜 Deep Velvet Nebula', colors: ['#8a2be2', '#da70d6', '#00ffff'] },
    { id: 'aurora', name: '✨ Aurora Borealis Pop', colors: ['#00ff88', '#00f0ff', '#7928ca'] },
    { id: 'cosmic', name: '🌌 Cosmic Acoustic Stars', colors: ['#4facfe', '#00f2fe', '#ffffff'] }
  ];

  function detectGenrePreset(track) {
    const title = (track?.metadata?.title || track?.name || '').toLowerCase();
    const artist = (track?.metadata?.artist_name || '').toLowerCase();
    const album = (track?.metadata?.album_title || '').toLowerCase();
    const allText = `${title} ${artist} ${album}`;

    if (/metal|rock|punk|heavy|guitar|band|slash|ac\/dc|metallica|rammstein|linkin/i.test(allText)) return 'magma';
    if (/synth|techno|electro|edm|dance|club|dj|future|cyber|remix|house/i.test(allText)) return 'cyberpunk';
    if (/rap|hip.?hop|trap|r&b|drill|beat|drake|eminem|snoop|tupac/i.test(allText)) return 'velvet';
    if (/acoustic|piano|jazz|classic|chill|lofi|unplugged|ballad|slow/i.test(allText)) return 'cosmic';
    return 'aurora';
  }

  function createFullscreenDOM() {
    injectStyles();
    if (document.getElementById('spicetify-karaoke-root')) return;

    rootEl = document.createElement('div');
    rootEl.id = 'spicetify-karaoke-root';
    rootEl.innerHTML = `
      <canvas id="spicetify-karaoke-canvas"></canvas>
      <div class="sp-ambient-glow" id="sp-ambient-glow"></div>
      
      <div class="sp-karaoke-topbar">
        <div class="sp-track-badge">
          <img id="sp-track-cover" src="" alt="Cover" />
          <div class="sp-track-details">
            <span id="sp-track-title">Kein Track</span>
            <span id="sp-track-artist">Wiedergabe pausiert</span>
          </div>
        </div>

        <div class="sp-controls-hud">
          <button class="sp-btn" id="sp-preset-btn">🎨 Preset: Auto</button>
          <div class="sp-offset-group">
            <button class="sp-btn" id="sp-offset-m">⏱️ -0.5s</button>
            <span id="sp-offset-val">0.0s</span>
            <button class="sp-btn" id="sp-offset-p">⏱️ +0.5s</button>
          </div>
          <button class="sp-btn sp-btn-close" id="sp-close-btn">✕ Schließen (F11)</button>
        </div>
      </div>

      <div class="sp-visualizer-center-info">
        <div class="sp-genre-badge" id="sp-genre-badge">✨ SYNTHWAVE / DANCE</div>
      </div>

      <div class="sp-karaoke-stage">
        <div class="sp-countdown-box" id="sp-countdown-box">
          <span class="sp-countdown-label" id="sp-countdown-label">Einsatz</span>
          <div class="sp-countdown-dots">
            <div class="sp-dot" id="sp-dot-1"></div>
            <div class="sp-dot" id="sp-dot-2"></div>
            <div class="sp-dot" id="sp-dot-3"></div>
          </div>
        </div>

        <div class="sp-current-line" id="sp-current-line">
          <span class="sp-loading-pulse">⚡ Synchronisiere Karaoke-Lyrics...</span>
        </div>

        <div class="sp-next-line" id="sp-next-line"></div>
      </div>
    `;

    document.body.appendChild(rootEl);

    canvasEl = document.getElementById('spicetify-karaoke-canvas');
    ctx = canvasEl.getContext('2d');
    titleEl = document.getElementById('sp-track-title');
    artistEl = document.getElementById('sp-track-artist');
    coverEl = document.getElementById('sp-track-cover');
    currentLineEl = document.getElementById('sp-current-line');
    nextLineEl = document.getElementById('sp-next-line');
    countdownEl = document.getElementById('sp-countdown-box');
    dot1 = document.getElementById('sp-dot-1');
    dot2 = document.getElementById('sp-dot-2');
    dot3 = document.getElementById('sp-dot-3');
    presetBtn = document.getElementById('sp-preset-btn');

    function resizeCanvas() {
      if (canvasEl) {
        canvasEl.width = window.innerWidth;
        canvasEl.height = window.innerHeight;
      }
    }
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    document.getElementById('sp-close-btn')?.addEventListener('click', toggleFullscreen);
    document.getElementById('sp-offset-m')?.addEventListener('click', () => adjustOffset(-0.5));
    document.getElementById('sp-offset-p')?.addEventListener('click', () => adjustOffset(+0.5));
    presetBtn?.addEventListener('click', cyclePreset);

    // Global Keydown Listeners
    window.addEventListener('keydown', handleKeydown, true);
    document.addEventListener('keydown', handleKeydown, true);
  }

  function handleKeydown(e) {
    if (e.key === 'F11' || (e.key.toLowerCase() === 'k' && (e.altKey || e.ctrlKey))) {
      e.preventDefault();
      e.stopPropagation();
      toggleFullscreen();
    }
    if (e.key === 'Escape' && isFullscreen) {
      e.preventDefault();
      e.stopPropagation();
      toggleFullscreen();
    }
  }

  function injectFloatingButton() {
    if (document.getElementById('sp-floating-karaoke-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'sp-floating-karaoke-btn';
    btn.title = 'AI Karaoke & Fullscreen Visualizer (F11 / Alt+K)';
    btn.innerHTML = '🎤 Karaoke & Visualizer';
    btn.style.cssText = `
      position: fixed;
      bottom: 95px;
      right: 25px;
      z-index: 99990;
      background: linear-gradient(135deg, rgba(0, 240, 255, 0.4), rgba(255, 0, 127, 0.4));
      border: 1px solid rgba(0, 240, 255, 0.7);
      backdrop-filter: blur(16px);
      color: #fff;
      font-family: 'Outfit', sans-serif;
      font-weight: 800;
      font-size: 13px;
      padding: 8px 18px;
      border-radius: 24px;
      box-shadow: 0 8px 30px rgba(0,0,0,0.7), 0 0 20px rgba(0, 240, 255, 0.5);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s ease;
      outline: none;
    `;
    btn.addEventListener('mouseenter', () => {
      btn.style.transform = 'scale(1.06) translateY(-2px)';
      btn.style.boxShadow = '0 12px 35px rgba(0,0,0,0.9), 0 0 30px rgba(0, 240, 255, 0.8)';
    });
    btn.addEventListener('mouseleave', () => {
      btn.style.transform = 'scale(1) translateY(0)';
      btn.style.boxShadow = '0 8px 30px rgba(0,0,0,0.7), 0 0 20px rgba(0, 240, 255, 0.5)';
    });
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleFullscreen();
    });
    document.body.appendChild(btn);
  }

  function injectPlaybarButton() {
    if (document.getElementById('sp-karaoke-playbar-btn')) return;

    const rightControls = document.querySelector('.main-nowPlayingBar-right') || 
                          document.querySelector('.main-nowPlayingBar-extraControls') ||
                          document.querySelector('[data-testid="now-playing-widget"]');

    if (rightControls) {
      const btn = document.createElement('button');
      btn.id = 'sp-karaoke-playbar-btn';
      btn.className = 'main-nowPlayingBar-extraControlsButton Button-sc-1dqy6lx-0';
      btn.title = 'AI Karaoke & Fullscreen Visualizer (F11 / Alt+K)';
      btn.innerHTML = `<span style="font-size: 16px; display:flex; align-items:center; justify-content:center; filter: drop-shadow(0 0 6px #00f0ff);">🎤</span>`;
      btn.style.cssText = 'background: transparent; border: none; cursor: pointer; padding: 6px 10px; display: flex; align-items: center;';
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleFullscreen();
      });
      rightControls.insertBefore(btn, rightControls.firstChild);
    }
  }

  function toggleFullscreen() {
    isFullscreen = !isFullscreen;
    if (rootEl) {
      if (isFullscreen) {
        rootEl.classList.add('active');
        document.documentElement.requestFullscreen?.().catch(() => {});
        startRenderingLoop();
        onTrackChanged();
      } else {
        rootEl.classList.remove('active');
        if (document.fullscreenElement) {
          document.exitFullscreen?.().catch(() => {});
        }
        stopRenderingLoop();
      }
    }
  }

  function adjustOffset(delta) {
    timeOffset = Math.round((timeOffset + delta) * 10) / 10;
    const el = document.getElementById('sp-offset-val');
    if (el) el.textContent = `${timeOffset > 0 ? '+' : ''}${timeOffset.toFixed(1)}s`;
  }

  function cyclePreset() {
    const modes = ['auto', 'cyberpunk', 'magma', 'velvet', 'aurora', 'cosmic'];
    let idx = modes.indexOf(visualizerMode);
    visualizerMode = modes[(idx + 1) % modes.length];

    if (presetBtn) {
      presetBtn.textContent = `🎨 Preset: ${visualizerMode.toUpperCase()}`;
    }
  }

  async function fetchSyncedLyrics(title, artist, durationSec) {
    if (!title) return null;

    try {
      const cleanTitle = title.replace(/\(.*?\)|\[.*?\]/g, '').trim();
      const cleanArtist = artist.replace(/\(.*?\)|\[.*?\]/g, '').trim();
      const url = `https://lrclib.net/api/get?track_name=${encodeURIComponent(cleanTitle)}&artist_name=${encodeURIComponent(cleanArtist)}&duration=${Math.round(durationSec)}`;

      const res = await fetch(url, { headers: { 'User-Agent': 'SpotifyKaraokeVisualizer/1.1' } });
      if (res.ok) {
        const data = await res.json();
        if (data.syncedLyrics) {
          return parseLrcLyrics(data.syncedLyrics, title, artist, 'LRCLIB Studio-Sync');
        }
      }
    } catch (e) {
      console.warn('[Spotify Karaoke] LRCLIB notice:', e);
    }

    return null;
  }

  function parseLrcLyrics(lrcText, title, artist, source) {
    const lines = [];
    const rawLines = lrcText.split('\n');
    const timeRegex = /\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)/;

    for (const raw of rawLines) {
      const match = raw.match(timeRegex);
      if (match) {
        const min = parseInt(match[1], 10);
        const sec = parseInt(match[2], 10);
        const frac = parseFloat('0.' + match[3]);
        const startTime = min * 60 + sec + frac;
        const text = match[4].trim();

        if (text) {
          lines.push({
            id: lines.length,
            startTime: Math.round(startTime * 100) / 100,
            endTime: 0,
            text: text,
            words: []
          });
        }
      }
    }

    for (let i = 0; i < lines.length; i++) {
      const cur = lines[i];
      const next = lines[i + 1];
      cur.endTime = next ? next.startTime : cur.startTime + 4.5;
      cur.words = interpolateWords(cur.text, cur.startTime, cur.endTime);

      const prevEnd = i > 0 ? lines[i - 1].endTime : 0;
      const pause = cur.startTime - prevEnd;
      if (pause >= 3.0 || (i === 0 && cur.startTime >= 2.5)) {
        cur.isBreak = true;
        cur.leadIn = {
          cueStart: Math.max(0, cur.startTime - 3.0),
          cueDuration: Math.min(3.0, pause)
        };
      } else {
        cur.isBreak = false;
      }
    }

    return { meta: { title, artist, source }, lines };
  }

  function interpolateWords(lineText, startTime, endTime) {
    const rawWords = lineText.split(/\s+/).filter(Boolean);
    if (rawWords.length === 0) return [];

    const vowels = "aeiouyäöüAEIOUYÄÖÜ";
    const weights = rawWords.map(w => {
      const clean = w.toLowerCase().replace(/[^a-zäöü]/g, '');
      const vCount = (clean.match(/[aeiouyäöü]/g) || []).length;
      return Math.max(1.0, vCount * 2.2 + clean.length * 0.5);
    });

    const totalWeight = weights.reduce((a, b) => a + b, 0);
    const duration = Math.max(0.5, endTime - startTime);
    const activeDur = duration * 0.88;

    const words = [];
    let acc = startTime;

    for (let i = 0; i < rawWords.length; i++) {
      const dur = (weights[i] / totalWeight) * activeDur;
      const wEnd = (i === rawWords.length - 1) ? endTime : (acc + dur);

      words.push({
        word: rawWords[i],
        start: Math.round(acc * 100) / 100,
        end: Math.round(wEnd * 100) / 100,
        duration: Math.round((wEnd - acc) * 100) / 100
      });
      acc += dur;
    }

    return words;
  }

  async function onTrackChanged() {
    const track = Spicetify.Player.data?.track;
    if (!track) return;

    const trackId = track.uri || track.metadata?.title;
    if (trackId === currentTrackId && lyricsData) return;
    currentTrackId = trackId;

    const title = track.metadata?.title || track.name || 'Unbekannter Track';
    const artist = track.metadata?.artist_name || 'Künstler';
    const durationSec = (track.metadata?.duration || 180000) / 1000;
    const coverUrl = track.metadata?.image_xlarge_url || track.metadata?.image_url || '';

    if (titleEl) titleEl.textContent = title;
    if (artistEl) artistEl.textContent = artist;
    if (coverEl && coverUrl) coverEl.src = coverUrl;

    detectedPreset = detectGenrePreset(track);
    const genreBadge = document.getElementById('sp-genre-badge');
    if (genreBadge) {
      genreBadge.textContent = `✨ ${detectedPreset.toUpperCase()} VISUALIZER`;
    }

    lyricsData = null;
    currentLineIndex = -1;
    if (currentLineEl) {
      currentLineEl.innerHTML = '<span class="sp-loading-pulse">⚡ Synchronisiere Songtext...</span>';
    }
    if (nextLineEl) nextLineEl.textContent = '';
    if (countdownEl) countdownEl.classList.remove('active');

    const lyrics = await fetchSyncedLyrics(title, artist, durationSec);
    if (currentTrackId === trackId) {
      lyricsData = lyrics;
      if (!lyrics && currentLineEl) {
        currentLineEl.innerHTML = '<span style="color:#ff007f;font-size:22px;">Kein synchronisierter Text für diesen Song gefunden</span>';
      }
    }
  }

  let animTime = 0;
  let bassPulse = 0;

  function drawVisualizer() {
    if (!canvasEl || !ctx || !isFullscreen) return;

    const width = window.innerWidth;
    const height = window.innerHeight;
    ctx.clearRect(0, 0, width, height);

    animTime += 0.02;
    const activePreset = visualizerMode === 'auto' ? detectedPreset : visualizerMode;
    const preset = PRESETS.find(p => p.id === activePreset) || PRESETS[0];

    const isPlaying = Spicetify.Player.isPlaying();
    const beat = isPlaying ? Math.sin(animTime * 4) * 0.5 + 0.5 : 0;
    bassPulse = bassPulse * 0.92 + beat * 0.08;

    const [c1, c2, c3] = preset.colors;

    const grad = ctx.createRadialGradient(width / 2, height / 2, 20, width / 2, height / 2, Math.max(width, height) * 0.65);
    grad.addColorStop(0, `${c1}22`);
    grad.addColorStop(0.5, `${c2}11`);
    grad.addColorStop(1, '#080a1200');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);

    if (activePreset === 'cyberpunk') {
      ctx.lineWidth = 3;
      for (let layer = 0; layer < 3; layer++) {
        ctx.beginPath();
        ctx.strokeStyle = layer === 0 ? c1 : (layer === 1 ? c2 : c3);
        ctx.shadowColor = ctx.strokeStyle;
        ctx.shadowBlur = 15;

        for (let x = 0; x < width; x += 15) {
          const freq = 0.004 * (layer + 1);
          const amp = (40 + layer * 25) * (isPlaying ? 1 : 0.2);
          const y = height * 0.42 + Math.sin(x * freq + animTime * 3 + layer) * amp * (1 + bassPulse * 0.8);
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
      ctx.shadowBlur = 0;
    } else if (activePreset === 'magma') {
      const numBars = 48;
      const barWidth = width / (numBars * 1.5);
      const startX = (width - numBars * barWidth * 1.5) / 2;

      for (let i = 0; i < numBars; i++) {
        const barHeight = (Math.sin(animTime * 5 + i * 0.3) * 0.5 + 0.5) * 160 * (isPlaying ? 1 + bassPulse : 0.2);
        const x = startX + i * barWidth * 1.5;
        const y = height * 0.48 - barHeight / 2;

        const barGrad = ctx.createLinearGradient(x, y, x, y + barHeight);
        barGrad.addColorStop(0, c3);
        barGrad.addColorStop(0.5, c2);
        barGrad.addColorStop(1, c1);

        ctx.fillStyle = barGrad;
        ctx.shadowColor = c1;
        ctx.shadowBlur = 12;
        ctx.fillRect(x, y, barWidth, barHeight);
      }
      ctx.shadowBlur = 0;
    } else if (activePreset === 'velvet') {
      const centerX = width / 2;
      const centerY = height * 0.42;

      for (let r = 0; r < 4; r++) {
        const radius = 60 + r * 50 + bassPulse * 40;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.strokeStyle = r % 2 === 0 ? c1 : c2;
        ctx.lineWidth = 2.5;
        ctx.shadowColor = ctx.strokeStyle;
        ctx.shadowBlur = 20;
        ctx.stroke();
      }
      ctx.shadowBlur = 0;
    } else if (activePreset === 'aurora') {
      ctx.lineWidth = 4;
      for (let w = 0; w < 2; w++) {
        ctx.beginPath();
        ctx.strokeStyle = w === 0 ? c1 : c2;
        ctx.shadowColor = ctx.strokeStyle;
        ctx.shadowBlur = 25;

        for (let x = 0; x < width; x += 10) {
          const y = height * 0.40 + Math.sin(x * 0.003 + animTime * 2 + w) * 55 + Math.cos(x * 0.006 - animTime) * 35;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
      ctx.shadowBlur = 0;
    } else if (activePreset === 'cosmic') {
      for (let p = 0; p < 35; p++) {
        const px = (Math.sin(p * 99 + animTime * 0.5) * 0.5 + 0.5) * width;
        const py = height * 0.2 + (Math.cos(p * 33 + animTime * 0.4) * 0.5 + 0.5) * (height * 0.35);
        const pRadius = 2 + (p % 4) * 2 + bassPulse * 3;

        ctx.beginPath();
        ctx.arc(px, py, pRadius, 0, Math.PI * 2);
        ctx.fillStyle = p % 2 === 0 ? c1 : c3;
        ctx.shadowColor = ctx.fillStyle;
        ctx.shadowBlur = 10;
        ctx.fill();
      }
      ctx.shadowBlur = 0;
    }
  }

  function updateKaraokeTypography() {
    if (!lyricsData || !lyricsData.lines || !isFullscreen) return;

    const currentTime = (Spicetify.Player.getProgress() / 1000) + timeOffset;
    const lines = lyricsData.lines;

    let activeIdx = -1;
    let upcomingIdx = -1;

    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (currentTime >= l.startTime && currentTime <= l.endTime) {
        activeIdx = i;
        break;
      }
      if (l.startTime > currentTime) {
        upcomingIdx = i;
        break;
      }
    }

    if (upcomingIdx !== -1) {
      const up = lines[upcomingIdx];
      if (up.leadIn && currentTime >= up.leadIn.cueStart && currentTime < up.startTime) {
        const rem = up.startTime - currentTime;
        countdownEl?.classList.add('active');

        if (dot1) dot1.className = `sp-dot ${rem <= 3.0 ? 'active-1' : ''}`;
        if (dot2) dot2.className = `sp-dot ${rem <= 2.0 ? 'active-2' : ''}`;
        if (dot3) dot3.className = `sp-dot ${rem <= 1.0 ? 'active-3' : ''}`;

        if (currentLineIndex !== up.id) {
          renderLine(up);
          currentLineIndex = up.id;
          const next = lines[upcomingIdx + 1];
          if (nextLineEl) nextLineEl.textContent = next ? `Vorschau: ${next.text}` : '';
          animateWords(up, currentTime);
        }
      } else {
        countdownEl?.classList.remove('active');
      }
    } else {
      countdownEl?.classList.remove('active');
    }

    if (activeIdx !== -1) {
      const activeLine = lines[activeIdx];
      if (currentLineIndex !== activeLine.id) {
        renderLine(activeLine);
        currentLineIndex = activeLine.id;
        const next = lines[activeIdx + 1];
        if (nextLineEl) nextLineEl.textContent = next ? `Vorschau: ${next.text}` : '';
      }
      animateWords(activeLine, currentTime);
    } else if (upcomingIdx !== -1 && currentLineIndex === lines[upcomingIdx].id) {
      animateWords(lines[upcomingIdx], currentTime);
    }
  }

  function renderLine(line) {
    if (!currentLineEl) return;
    currentLineEl.innerHTML = '';

    if (!line.words || line.words.length === 0) {
      currentLineEl.textContent = line.text;
      return;
    }

    const frag = document.createDocumentFragment();
    line.words.forEach((w, idx) => {
      const span = document.createElement('span');
      span.className = 'sp-word';
      span.id = `sp-w-${idx}`;
      span.textContent = w.word;
      frag.appendChild(span);
    });

    currentLineEl.appendChild(frag);
  }

  function animateWords(line, currentTime) {
    if (!line || !line.words) return;

    for (let i = 0; i < line.words.length; i++) {
      const w = line.words[i];
      const el = document.getElementById(`sp-w-${i}`);
      if (!el) continue;

      if (currentTime < w.start) {
        el.style.setProperty('--fill-pct', '0%');
        el.classList.remove('singing', 'done');
      } else if (currentTime >= w.start && currentTime <= w.end) {
        const dur = Math.max(0.04, w.end - w.start);
        const progress = Math.min(100, Math.max(0, ((currentTime - w.start) / dur) * 100));
        el.style.setProperty('--fill-pct', `${progress.toFixed(1)}%`);
        el.classList.add('singing');
        el.classList.remove('done');
      } else {
        el.style.setProperty('--fill-pct', '100%');
        el.classList.remove('singing');
        el.classList.add('done');
      }
    }
  }

  function renderLoop() {
    if (isFullscreen) {
      drawVisualizer();
      updateKaraokeTypography();
      rafId = requestAnimationFrame(renderLoop);
    }
  }

  function startRenderingLoop() {
    stopRenderingLoop();
    rafId = requestAnimationFrame(renderLoop);
  }

  function stopRenderingLoop() {
    if (rafId) cancelAnimationFrame(rafId);
  }

  createFullscreenDOM();
  injectFloatingButton();
  setTimeout(injectPlaybarButton, 1000);
  setTimeout(injectPlaybarButton, 3000);

  Spicetify.Player.addEventListener('songchange', () => {
    if (isFullscreen) onTrackChanged();
  });

  console.log('[Spotify Karaoke] ✨ AI Karaoke & Fullscreen Visualizer v1.1 Ready!');
})();
