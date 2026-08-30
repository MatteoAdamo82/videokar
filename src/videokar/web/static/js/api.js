// Talking to the server, and the one distinction worth making about failure.
import {say} from "./dom.js";

export class Offline extends Error {}

export async function api(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (err) {
    // fetch only rejects when the request never got an answer. Told apart from
    // an HTTP error because the page looks frozen either way, and the two need
    // completely different things from the reader.
    throw new Offline("the server is not answering — is `videokar serve` still running?");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

// Every write is the same shape; spelling it out at each call site was three
// lines of ceremony around the one line that mattered.
export const post = (path, body) =>
  api(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });

export function report(err) {
  say(err.message, "bad");
  document.body.classList.toggle("offline", err instanceof Offline);
}
