const STORAGE_KEYS = {
  deck: "japcards.deck",
  notetype: "japcards.notetype",
  deckName: "japcards.deckname",
  accessCode: "japcards.accesscode",
};

function accessCodeHeaders() {
  const code = localStorage.getItem(STORAGE_KEYS.accessCode) || "";
  return code ? { "X-Access-Code": code } : {};
}

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
  readingComparison: document.getElementById("reading-comparison"),
  readingLlm: document.getElementById("reading-llm"),
  readingFugashi: document.getElementById("reading-fugashi"),
  regenerateBtn: document.getElementById("regenerate-btn"),
  addBtn: document.getElementById("add-btn"),
  deckList: document.getElementById("deck-list"),
  deckCount: document.getElementById("deck-count"),
  downloadBtn: document.getElementById("download-btn"),
  notetype: document.getElementById("notetype"),
  deckNameInput: document.getElementById("deck-name"),
  accessCode: document.getElementById("access-code"),
};

let deck = loadDeck();

function loadDeck() {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.deck);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveDeck() {
  localStorage.setItem(STORAGE_KEYS.deck, JSON.stringify(deck));
}

function initSettings() {
  els.notetype.value = localStorage.getItem(STORAGE_KEYS.notetype) || "";
  els.deckNameInput.value = localStorage.getItem(STORAGE_KEYS.deckName) || "";
  els.accessCode.value = localStorage.getItem(STORAGE_KEYS.accessCode) || "";
  els.notetype.addEventListener("change", () => {
    localStorage.setItem(STORAGE_KEYS.notetype, els.notetype.value);
  });
  els.deckNameInput.addEventListener("change", () => {
    localStorage.setItem(STORAGE_KEYS.deckName, els.deckNameInput.value);
  });
  els.accessCode.addEventListener("change", () => {
    localStorage.setItem(STORAGE_KEYS.accessCode, els.accessCode.value);
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
      headers: { "Content-Type": "application/json", ...accessCodeHeaders() },
      body: JSON.stringify({ vocab, research: els.research.checked }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.error || `request failed (${resp.status})`);
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
  els.vocab.focus();
}

async function downloadDeck() {
  if (deck.length === 0) return;

  els.downloadBtn.disabled = true;
  try {
    const resp = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...accessCodeHeaders() },
      body: JSON.stringify({
        cards: deck,
        notetype: els.notetype.value,
        deck: els.deckNameInput.value,
      }),
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      alert(`Export failed: ${data.error || resp.status}`);
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
