const STORAGE_KEYS = {
  deck: "japcards.deck",
  notetype: "japcards.notetype",
  deckName: "japcards.deckname",
};

const els = {
  vocab: document.getElementById("vocab"),
  research: document.getElementById("research"),
  generateBtn: document.getElementById("generate-btn"),
  generateStatus: document.getElementById("generate-status"),
  cardPreview: document.getElementById("card-preview"),
  disagreementWarning: document.getElementById("disagreement-warning"),
  fieldFront: document.getElementById("field-front"),
  fieldExpression: document.getElementById("field-expression"),
  fieldReading: document.getElementById("field-reading"),
  fieldBemerkungen: document.getElementById("field-bemerkungen"),
  fieldGuidance: document.getElementById("field-guidance"),
  readingComparison: document.getElementById("reading-comparison"),
  readingLlm: document.getElementById("reading-llm"),
  readingFugashi: document.getElementById("reading-fugashi"),
  regenerateBtn: document.getElementById("regenerate-btn"),
  addBtn: document.getElementById("add-btn"),
  deckList: document.getElementById("deck-list"),
  deckCount: document.getElementById("deck-count"),
  syncStatus: document.getElementById("sync-status"),
  downloadBtn: document.getElementById("download-btn"),
  notetype: document.getElementById("notetype"),
  deckNameInput: document.getElementById("deck-name"),
};

function friendlyErrorMessage(status, fallback) {
  // The session cookie is the only auth signal now (no more per-request
  // access-code header) -- a 401 specifically means it expired or was
  // never set, which reloading (and re-hitting the ZITADEL login) fixes.
  return status === 401 ? "Session expired — reload the page to sign in again." : fallback;
}

let deck = loadDeck();

function loadDeck() {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.deck);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function persistDeckLocally() {
  localStorage.setItem(STORAGE_KEYS.deck, JSON.stringify(deck));
}

// Defaults for a fresh browser/profile that's never saved settings
// before -- your actual note type and deck, so the common case needs no
// typing. Still fully overridable, and once changed the override wins
// (STORAGE_KEYS.notetype/deckName take precedence below).
const DEFAULT_NOTETYPE = "Japanese Verb-Objekt-Kombinationen";
const DEFAULT_DECK = "Japanese::Verb-Objekt-Kombinationen";

function initSettings() {
  els.notetype.value = localStorage.getItem(STORAGE_KEYS.notetype) || DEFAULT_NOTETYPE;
  els.deckNameInput.value = localStorage.getItem(STORAGE_KEYS.deckName) || DEFAULT_DECK;
  els.notetype.addEventListener("change", () => {
    localStorage.setItem(STORAGE_KEYS.notetype, els.notetype.value);
    scheduleSync();
  });
  els.deckNameInput.addEventListener("change", () => {
    localStorage.setItem(STORAGE_KEYS.deckName, els.deckNameInput.value);
    scheduleSync();
  });
}

function renderDeck() {
  els.deckList.replaceChildren();
  deck.forEach((card, index) => {
    const li = document.createElement("li");

    const text = document.createElement("span");
    text.className = "deck-item-text";
    text.lang = "ja";
    text.textContent = `${card.expression} — ${card.front}`;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "remove-btn";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => {
      deck.splice(index, 1);
      saveDeck();
      renderDeck();
    });

    li.append(text, removeBtn);
    els.deckList.append(li);
  });

  els.deckCount.textContent = deck.length;
  els.downloadBtn.disabled = deck.length === 0;
}

// --- Server sync -----------------------------------------------------
//
// The server is the source of truth once it has a document; localStorage
// is kept as a mirror so the app still works (read-only against stale
// data) if a PUT or the initial GET fails. Every mutation writes
// localStorage immediately, then a debounced PUT pushes it to the server
// -- last write wins, there's no merge across devices/tabs.

let syncTimer = null;
// True from the moment any local edit happens. Lets initDeck() notice a
// card was added/removed while its GET was still in flight, so it doesn't
// clobber that edit with the (now stale) server response -- see there.
let hasLocalEdit = false;
// Only one PUT in flight at a time; a sync requested while one is already
// running is queued rather than fired concurrently, so two overlapping
// requests can never complete out of order and have the older one win.
let syncInFlight = false;
let syncQueued = false;

function saveDeck() {
  hasLocalEdit = true;
  persistDeckLocally();
  scheduleSync();
}

function scheduleSync() {
  els.syncStatus.textContent = "Saving…";
  clearTimeout(syncTimer);
  syncTimer = setTimeout(runSync, 1000);
}

async function runSync() {
  if (syncInFlight) {
    syncQueued = true;
    return;
  }
  syncInFlight = true;
  try {
    await syncToServer();
  } finally {
    syncInFlight = false;
    if (syncQueued) {
      syncQueued = false;
      runSync();
    }
  }
}

async function syncToServer() {
  try {
    const resp = await fetch("/api/deck", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cards: deck,
        notetype: els.notetype.value,
        deck: els.deckNameInput.value,
      }),
    });
    if (!resp.ok) {
      throw new Error(friendlyErrorMessage(resp.status, `save failed (${resp.status})`));
    }
    els.syncStatus.textContent = "Saved";
  } catch (err) {
    els.syncStatus.textContent = `Not saved — ${err.message} `;
    const retryBtn = document.createElement("button");
    retryBtn.type = "button";
    retryBtn.textContent = "Retry";
    retryBtn.addEventListener("click", runSync);
    els.syncStatus.append(retryBtn);
  }
}

async function initDeck() {
  try {
    const resp = await fetch("/api/deck");
    if (!resp.ok) {
      throw new Error(friendlyErrorMessage(resp.status, `load failed (${resp.status})`));
    }
    const data = await resp.json();

    if (data.exists) {
      // If the user already added/removed a card before this GET
      // resolved, keep their edit instead of overwriting it with what
      // was on the server before that edit happened -- the edit's own
      // scheduled sync will push it up shortly regardless.
      if (!hasLocalEdit) {
        deck = data.cards;
        persistDeckLocally();
        if (data.notetype) {
          els.notetype.value = data.notetype;
          localStorage.setItem(STORAGE_KEYS.notetype, data.notetype);
        }
        if (data.deck) {
          els.deckNameInput.value = data.deck;
          localStorage.setItem(STORAGE_KEYS.deckName, data.deck);
        }
        renderDeck();
      }
    } else if (deck.length > 0) {
      // No document on the server yet, but there's a deck in this
      // browser's localStorage (from before this feature existed, or
      // from a session that never finished syncing) -- push it up once
      // rather than treating "nothing on the server" as "start empty".
      scheduleSync();
    }
    els.syncStatus.textContent = "";
  } catch (err) {
    els.syncStatus.textContent = err.message || "Offline — showing the last saved copy";
  }
}

async function generateCard() {
  const vocab = els.vocab.value.trim();
  if (!vocab) {
    els.vocab.focus();
    return;
  }

  els.generateBtn.disabled = true;
  els.regenerateBtn.disabled = true;
  els.generateStatus.textContent = "Generating…";

  try {
    const resp = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        vocab,
        research: els.research.checked,
        guidance: els.fieldGuidance.value.trim(),
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(friendlyErrorMessage(resp.status, data.error || `request failed (${resp.status})`));
    }

    els.fieldFront.value = data.front;
    els.fieldExpression.value = data.expression;
    // fugashi's reading wins by default -- it's the deterministic,
    // dictionary-backed one. The LLM's own reading is shown alongside for
    // reference, especially when the two disagree.
    els.fieldReading.value = data.reading_fugashi;
    els.fieldBemerkungen.value = data.bemerkungen;

    els.disagreementWarning.hidden = data.furigana_agrees;
    els.readingComparison.hidden = data.furigana_agrees;
    els.readingLlm.textContent = data.reading;
    els.readingFugashi.textContent = data.reading_fugashi;

    els.cardPreview.hidden = false;
    els.generateStatus.textContent = "";
  } catch (err) {
    els.generateStatus.textContent = `Error: ${err.message}`;
  } finally {
    els.generateBtn.disabled = false;
    els.regenerateBtn.disabled = false;
  }
}

function addCurrentCardToDeck() {
  deck.push({
    front: els.fieldFront.value.trim(),
    expression: els.fieldExpression.value.trim(),
    reading: els.fieldReading.value.trim(),
    bemerkungen: els.fieldBemerkungen.value.trim(),
  });
  saveDeck();
  renderDeck();

  els.cardPreview.hidden = true;
  els.vocab.value = "";
  els.fieldGuidance.value = "";
  els.vocab.focus();
}

async function downloadDeck() {
  if (deck.length === 0) return;

  els.downloadBtn.disabled = true;
  try {
    const resp = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cards: deck,
        notetype: els.notetype.value,
        deck: els.deckNameInput.value,
      }),
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      alert(`Export failed: ${friendlyErrorMessage(resp.status, data.error || resp.status)}`);
      return;
    }

    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "japanese-phrase-cards.txt";
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } finally {
    els.downloadBtn.disabled = deck.length === 0;
  }
}

els.generateBtn.addEventListener("click", generateCard);
els.regenerateBtn.addEventListener("click", generateCard);
els.addBtn.addEventListener("click", addCurrentCardToDeck);
els.downloadBtn.addEventListener("click", downloadDeck);
els.vocab.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    generateCard();
  }
});

initSettings();
renderDeck();
initDeck();
