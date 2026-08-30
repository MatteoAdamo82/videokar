// Turning the dialog's controls into what the renderer's schema wants, and back.
// The panel speaks in multiples and percentages so a choice holds at any
// resolution; the schema speaks in pixels.

// Heights the presets render at, so a margin given as a percentage can be
// turned into the pixels the schema wants.
const PRESET_HEIGHT = {alpha: 1080, youtube: 1080, minimal: 1080, shorts: 1920};

export const presetHeight = (name) => PRESET_HEIGHT[name] || 1080;

// The size the renderer would pick on its own, so the control is a multiple of
// what a preset already looks right at rather than a bare pixel count.
export const defaultSize = (name) => Math.max(12, Math.round(presetHeight(name) / 17));

// A colour input speaks "#rrggbb" only, so any alpha the file carries is
// dropped for the swatch and put back when the choice is sent.
export const hexOf = (value, fallback) =>
  typeof value === "string" && value.startsWith("#") ? value.slice(0, 7) : fallback;

// Alpha is not something a colour input can express, so it is carried here:
// an outline and a shadow both want to sit under full opacity.
export const lookOf = (s) => ({
  main: {
    colour_on: s.colour_on,
    colour_off: s.colour_off,
    outline: s.outline_width ? s.outline + "d2" : null,
    outline_width: s.outline_width,
  },
  shadow: {colour: s.shadow ? s.shadow + "c8" : null},
});

export const overridesFrom = (s, fps, audio) => ({
  output: {
    audio,
    ...(fps ? {fps: Number(fps)} : {}),
  },
  layout: {
    anchor: s.anchor,
    margin_y: Math.round(presetHeight(s.preset) * s.margin_pct / 100),
  },
  main: {
    ...lookOf(s).main,
    size: Math.round(defaultSize(s.preset) * s.size_scale),
    ...(s.font ? {font: s.font} : {}),
  },
  shadow: lookOf(s).shadow,
  paren: {scale: s.paren_scale},
  ball: {
    squash: s.squash,
    ...(s.sprite
      ? {kind: "sprite", sprite: s.sprite, sprite_scale: s.sprite_scale}
      : {}),
  },
});

// The query the preview endpoint wants for one frame at these settings.
export function previewQuery(s, at) {
  const height = presetHeight(s.preset);
  const query = new URLSearchParams({
    at: at.toFixed(2),
    preset: s.preset,
    anchor: s.anchor,
    margin_y: Math.round(height * s.margin_pct / 100),
    paren_scale: s.paren_scale,
  });
  if (s.sprite) {
    query.set("sprite", s.sprite);
    query.set("sprite_scale", s.sprite_scale);
  }
  if (s.squash) query.set("squash", s.squash);
  if (s.font) query.set("font", s.font);
  query.set("font_size", Math.round(defaultSize(s.preset) * s.size_scale));
  query.set("extra", JSON.stringify(lookOf(s)));
  return query;
}
