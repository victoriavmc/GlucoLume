// Sonido corto de aviso, generado con Web Audio (sin archivos). El navegador puede bloquearlo hasta que la persona
// interactúe con la página: en ese caso falla en silencio, el cartel se muestra igual.

let audioContext = null;

function getContext() {
  const Ctor = typeof window === 'undefined' ? null : window.AudioContext || window.webkitAudioContext;
  if (!Ctor) return null;
  if (!audioContext) audioContext = new Ctor();
  return audioContext;
}

function tone(ctx, frequency, start, duration) {
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.type = 'sine';
  oscillator.frequency.value = frequency;
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(0.18, start + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  oscillator.connect(gain).connect(ctx.destination);
  oscillator.start(start);
  oscillator.stop(start + duration + 0.02);
}

export async function playNotificationSound() {
  try {
    const ctx = getContext();
    if (!ctx) return;
    if (ctx.state === 'suspended') await ctx.resume();
    if (ctx.state !== 'running') return;
    const now = ctx.currentTime;
    tone(ctx, 880, now, 0.18);
    tone(ctx, 1175, now + 0.16, 0.26);
  } catch {
    // Sin sonido (política de autoplay o sin audio): no es un error de la aplicación.
  }
}
