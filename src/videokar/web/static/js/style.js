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

// The text size the controls add up to, which the ball is then measured against.
export const textSize = (s) => Math.round(defaultSize(s.preset) * s.size_scale);

// A quarter of the text size is what the renderer picks when nothing says
// otherwise, so 1.0x on the control is the size it would have had anyway.
const BALL_OF_TEXT = 0.25;

// Always says which kind, and always in full. Overrides merge per key and a
// section that merely stops naming a sprite leaves the saved one in place —
// which is why a PNG could not be taken back off once it had been chosen.
export const ballOf = (s) => {
  if (s.bounce === "none") return {kind: "none"};
  if (s.bounce === "sprite" && s.sprite) {
    return {
      kind: "sprite",
      sprite: s.sprite,
      sprite_scale: s.sprite_scale,
      squash: s.squash,
    };
  }
  return {
    kind: "ball",
    colour: s.ball_colour,
    // Absolute pixels in the schema, a multiple of the text here: the same
    // choice then holds when the text size or the preset changes.
    radius: Math.max(1, Math.min(200, Math.round(textSize(s) * BALL_OF_TEXT * s.ball_scale))),
    squash: s.squash,
  };
};

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
    size: textSize(s),
    ...(s.font ? {font: s.font} : {}),
  },
  shadow: lookOf(s).shadow,
  paren: {scale: s.paren_scale},
  ball: ballOf(s),
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
  if (s.bounce === "sprite" && s.sprite) {
    query.set("sprite", s.sprite);
    query.set("sprite_scale", s.sprite_scale);
  }
  if (s.squash) query.set("squash", s.squash);
  if (s.font) query.set("font", s.font);
  query.set("font_size", textSize(s));
  // The still and the render read the same sections, so what is judged here is
  // what gets encoded.
  query.set("extra", JSON.stringify({...lookOf(s), ball: ballOf(s)}));
  return query;
}
