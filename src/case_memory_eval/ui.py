"""Self-contained reviewer interface assets."""

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clinical Case Memory Eval Lab</title>
  <link rel="stylesheet" href="/assets/styles.css">
</head>
<body>
  <header>
    <div>
      <p class="eyebrow">Evaluation workspace</p>
      <h1>Clinical Case Memory Eval Lab</h1>
    </div>
    <span class="boundary">Synthetic / redacted data only</span>
  </header>
  <main>
    <aside aria-label="Review queue">
      <div class="section-title"><h2>Review queue</h2><span id="queue-count">0</span></div>
      <div id="queue" class="queue"></div>
    </aside>
    <section class="workspace" aria-live="polite">
      <div id="empty" class="empty">No cases awaiting review.</div>
      <div id="case-view" hidden>
        <div class="case-heading">
          <div><p id="family" class="eyebrow"></p><h2 id="case-title"></h2></div>
          <code id="case-id"></code>
        </div>
        <div class="comparison">
          <article><h3>Source transcript</h3><p id="transcript"></p></article>
          <article><h3>Generated note</h3><p id="note"></p></article>
        </div>
        <section class="findings-section">
          <div class="section-title"><h3>Cited findings</h3><span id="finding-count"></span></div>
          <div id="findings"></div>
        </section>
        <section class="precedents-section">
          <div class="section-title"><h3>Reviewed precedents</h3><span id="precedent-count"></span></div>
          <div id="precedents"></div>
        </section>
        <form id="review-form">
          <div class="field-row">
            <label>Reviewer identity<input id="reviewer" required value="local-reviewer"></label>
            <label>Rationale<input id="rationale" required minlength="10"
              value="Evidence citations were inspected against both sources."></label>
          </div>
          <div class="actions">
            <button type="button" data-decision="deferred">Defer</button>
            <button type="button" data-decision="rejected" class="reject">Reject</button>
            <button type="button" data-decision="accepted" data-promote="true" class="accept">
              Accept and promote
            </button>
          </div>
          <p id="status" role="status"></p>
        </form>
      </div>
    </section>
  </main>
  <script src="/assets/app.js"></script>
</body>
</html>
"""

CSS = """:root {
  color-scheme: light;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
  color: #17211d;
  background: #f4f6f5;
  letter-spacing: 0;
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; }
header {
  min-height: 76px; padding: 16px 28px; display: flex; align-items: center;
  justify-content: space-between; gap: 24px; background: #fff; border-bottom: 1px solid #d8dedb;
}
h1 { margin: 2px 0 0; font-size: 21px; font-weight: 680; }
h2 { font-size: 17px; } h3 { font-size: 14px; }
h2, h3, p { margin-top: 0; }
.eyebrow { margin: 0; color: #607069; font-size: 11px; text-transform: uppercase; font-weight: 700; }
.boundary { color: #7b3f00; background: #fff3df; border: 1px solid #e9c993; padding: 6px 9px; font-size: 12px; }
main { display: grid; grid-template-columns: 290px minmax(0, 1fr); min-height: calc(100vh - 76px); }
aside { background: #edf1ef; border-right: 1px solid #d8dedb; padding: 20px 14px; }
.section-title { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.queue { display: grid; gap: 6px; }
.queue button { width: 100%; text-align: left; padding: 10px; background: transparent; border: 1px solid transparent; color: #25342e; }
.queue button:hover, .queue button.active { background: #fff; border-color: #bec9c4; }
.queue strong, .queue small { display: block; } .queue small { color: #687770; margin-top: 4px; }
.workspace { padding: 24px 28px 40px; overflow: hidden; }
.empty { color: #687770; padding-top: 12vh; text-align: center; }
.case-heading { display: flex; justify-content: space-between; align-items: end; gap: 18px; margin-bottom: 18px; }
.case-heading h2 { margin: 4px 0 0; } code { color: #687770; font-size: 11px; word-break: break-all; }
.comparison { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid #ccd4d0; background: #fff; }
.comparison article { min-width: 0; padding: 18px; } .comparison article + article { border-left: 1px solid #ccd4d0; }
.comparison p { white-space: pre-wrap; line-height: 1.6; color: #304039; }
.findings-section, .precedents-section, form { padding: 20px 0; border-bottom: 1px solid #d8dedb; }
.finding { padding: 12px 0; border-top: 1px solid #e0e5e2; }
.finding:first-child { border-top: 0; }
.finding-head { display: flex; justify-content: space-between; gap: 12px; font-weight: 700; }
.finding blockquote { margin: 8px 0 0; padding-left: 10px; border-left: 3px solid #39906a; color: #43534b; }
.precedents-section p { color: #5d6c65; max-width: 760px; line-height: 1.5; }
.precedent { display: grid; grid-template-columns: 1fr auto; gap: 8px; padding: 9px 0; border-top: 1px solid #e0e5e2; }
.precedent code { grid-column: 1 / -1; } .precedent p { margin: 0; }
.field-row { display: grid; grid-template-columns: minmax(170px, 0.35fr) minmax(260px, 1fr); gap: 12px; }
label { display: grid; gap: 6px; font-size: 12px; font-weight: 650; }
input { min-height: 38px; border: 1px solid #b9c4bf; background: #fff; padding: 8px 10px; font: inherit; }
.actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
button { min-height: 36px; border: 1px solid #aebbb5; background: #fff; padding: 7px 12px; font: inherit; cursor: pointer; }
button.reject { color: #8e2929; border-color: #d7adad; } button.accept { color: #fff; background: #176b4c; border-color: #176b4c; }
button:disabled { cursor: wait; opacity: .55; } #status { min-height: 20px; margin: 10px 0 0; color: #43534b; text-align: right; }
@media (max-width: 780px) {
  header { align-items: flex-start; padding: 14px 16px; } .boundary { max-width: 150px; }
  main { grid-template-columns: 1fr; } aside { border-right: 0; border-bottom: 1px solid #d8dedb; }
  .workspace { padding: 20px 16px 32px; } .comparison, .field-row { grid-template-columns: 1fr; }
  .comparison article + article { border-left: 0; border-top: 1px solid #ccd4d0; }
  .case-heading { align-items: start; flex-direction: column; } .actions { flex-wrap: wrap; }
}
"""

JS = """const state = { items: [], selected: 0 };
const $ = (id) => document.getElementById(id);

async function loadQueue() {
  const response = await fetch('/reviews/queue');
  state.items = await response.json();
  state.selected = Math.min(state.selected, Math.max(0, state.items.length - 1));
  render();
}

function render() {
  $('queue-count').textContent = String(state.items.length);
  $('queue').replaceChildren(...state.items.map((item, index) => {
    const button = document.createElement('button');
    button.className = index === state.selected ? 'active' : '';
    const title = document.createElement('strong'); title.textContent = item.case.title;
    const meta = document.createElement('small');
    meta.textContent = `${item.case.scenario_family} · ${item.verdict.findings.length} findings`;
    button.append(title, meta); button.onclick = () => { state.selected = index; render(); };
    return button;
  }));
  const item = state.items[state.selected];
  $('empty').hidden = Boolean(item); $('case-view').hidden = !item;
  if (!item) return;
  $('family').textContent = item.case.scenario_family.replaceAll('_', ' ');
  $('case-title').textContent = item.case.title; $('case-id').textContent = item.case_id;
  $('transcript').textContent = item.case.transcript; $('note').textContent = item.case.generated_note;
  $('finding-count').textContent = `${item.verdict.findings.length} total`;
  $('findings').replaceChildren(...item.verdict.findings.map((finding) => {
    const article = document.createElement('article'); article.className = 'finding';
    const head = document.createElement('div'); head.className = 'finding-head';
    const label = document.createElement('span'); label.textContent = finding.label.replaceAll('_', ' ');
    const confidence = document.createElement('span'); confidence.textContent = `${Math.round(finding.confidence * 100)}%`;
    head.append(label, confidence);
    const rationale = document.createElement('p'); rationale.textContent = finding.rationale;
    const quote = document.createElement('blockquote');
    quote.textContent = `Transcript: “${finding.transcript_span.text}”\nNote: “${finding.note_span.text}”`;
    article.append(head, rationale, quote); return article;
  }));
  $('precedent-count').textContent = `${item.precedents.length} total`;
  const precedentItems = item.precedents.length ? item.precedents.map((precedent) => {
    const article = document.createElement('article'); article.className = 'precedent';
    const title = document.createElement('strong'); title.textContent = precedent.title;
    const score = document.createElement('span'); score.textContent = `score ${precedent.score.toFixed(3)}`;
    const id = document.createElement('code'); id.textContent = precedent.case_id;
    const influence = document.createElement('p'); influence.textContent = precedent.influence;
    article.append(title, score, id, influence); return article;
  }) : [Object.assign(document.createElement('p'), {textContent: 'No promoted precedent matched.'})];
  $('precedents').replaceChildren(...precedentItems);
  $('status').textContent = '';
}

async function decide(decision, promote) {
  const item = state.items[state.selected]; if (!item) return;
  const reviewer = $('reviewer').value.trim(); const rationale = $('rationale').value.trim();
  if (reviewer.length < 2 || rationale.length < 10) {
    $('status').textContent = 'Reviewer identity and a rationale of at least 10 characters are required.'; return;
  }
  document.querySelectorAll('.actions button').forEach((button) => { button.disabled = true; });
  $('status').textContent = 'Recording decision…';
  try {
    const response = await fetch(`/reviews/${item.result_id}/decisions`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({reviewer, decision, rationale,
        idempotency_key: `${item.result_id.slice(0, 12)}-${decision}-${reviewer}`})
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Decision failed');
    const review = await response.json();
    if (promote) {
      const promotion = await fetch(`/reviews/${review.review_id}/promote`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({actor: reviewer})
      });
      if (!promotion.ok) throw new Error((await promotion.json()).detail || 'Promotion failed');
    }
    await loadQueue();
  } catch (error) { $('status').textContent = error.message; }
  finally { document.querySelectorAll('.actions button').forEach((button) => { button.disabled = false; }); }
}

document.querySelectorAll('[data-decision]').forEach((button) => {
  button.onclick = () => decide(button.dataset.decision, button.dataset.promote === 'true');
});
loadQueue().catch((error) => { $('empty').textContent = error.message; });
"""
