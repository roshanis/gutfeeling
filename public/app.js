// Renders the survey from /api/questions. No question text lives here:
// edit survey/questions.json to change the survey.
(async function () {
  const form = document.getElementById("form");
  const backBtn = document.getElementById("back");
  const nextBtn = document.getElementById("next");
  const stepEl = document.getElementById("step");
  const bar = document.getElementById("bar");

  const config = await (await fetch("/api/questions")).json();
  document.getElementById("title").textContent = config.title;
  document.title = config.title;

  const answers = {};
  const sections = config.sections;
  let page = -1; // -1 = intro, sections.length = thank-you
  let errors = {};

  const el = (tag, attrs = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "text") node.textContent = v;
      else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v === true ? "" : v);
    }
    node.append(...children);
    return node;
  };

  const isVisible = (q) => {
    const c = q.show_if;
    if (!c) return true;
    const v = answers[c.question];
    return Array.isArray(v) ? v.some((x) => c.in.includes(x)) : c.in.includes(v);
  };
  const isEmpty = (v) => v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length);

  // Drop answers to questions that are now hidden (e.g. switched smoker -> never).
  const pruneHidden = () => {
    for (const s of sections) for (const q of s.questions) if (!isVisible(q)) delete answers[q.id];
  };

  function validateSection(section) {
    const errs = {};
    for (const q of section.questions) {
      if (!isVisible(q)) continue;
      const v = answers[q.id];
      if (isEmpty(v)) { if (q.required) errs[q.id] = "Please answer this question."; continue; }
      if ((q.type === "number" || q.type === "height") && (Number.isNaN(v) ||
          (q.min !== undefined && v < q.min) || (q.max !== undefined && v > q.max))) {
        errs[q.id] = q.type === "height" ? "Please enter a valid height."
          : `Please enter a number between ${q.min} and ${q.max}.`;
      }
    }
    return errs;
  }

  function renderChoice(q) {
    const multi = q.type === "multi";
    const box = el("div");
    for (const o of q.options) {
      const current = answers[q.id];
      const checked = multi ? (current || []).includes(o.value) : current === o.value;
      const input = el("input", { type: multi ? "checkbox" : "radio", name: q.id, value: o.value, checked });
      input.addEventListener("change", () => {
        if (multi) {
          let vals = new Set(answers[q.id] || []);
          if (input.checked) {
            const excl = q.exclusive || [];
            // Picking "None" clears the rest; picking anything else clears "None".
            if (excl.includes(o.value)) vals = new Set();
            else excl.forEach((x) => vals.delete(x));
            vals.add(o.value);
          } else vals.delete(o.value);
          answers[q.id] = q.options.map((x) => x.value).filter((x) => vals.has(x));
        } else answers[q.id] = o.value;
        pruneHidden();
        render();
      });
      box.append(el("label", { class: "opt" }, input, o.label));
    }
    return box;
  }

  function renderNumber(q) {
    const input = el("input", { type: "number", id: q.id, inputmode: "decimal", min: q.min, max: q.max,
      value: answers[q.id] ?? "" });
    input.addEventListener("input", () => {
      answers[q.id] = input.value === "" ? undefined : Number(input.value);
    });
    return el("div", { class: "row" }, input, q.unit ? el("span", { class: "muted", text: q.unit }) : "");
  }

  // Height is always stored in centimetres; people can enter cm or feet + inches.
  const heightUnit = {};
  function renderHeight(q) {
    const unit = heightUnit[q.id] || "ft";
    const select = el("select", { "aria-label": "Unit" },
      el("option", { value: "ft", selected: unit === "ft", text: "ft / in" }),
      el("option", { value: "cm", selected: unit === "cm", text: "cm" }));
    select.addEventListener("change", () => { heightUnit[q.id] = select.value; render(); });
    const row = el("div", { class: "row" });
    const cm = answers[q.id];
    if (unit === "cm") {
      const input = el("input", { type: "number", id: q.id, value: cm ?? "", "aria-label": "Centimetres" });
      input.addEventListener("input", () => {
        answers[q.id] = input.value === "" ? undefined : Number(input.value);
      });
      row.append(input, el("span", { class: "muted", text: "cm" }), select);
    } else {
      const totalIn = cm ? cm / 2.54 : null;
      let ft = totalIn ? Math.floor(totalIn / 12) : "";
      let inch = totalIn ? Math.round(totalIn - ft * 12) : "";
      if (inch === 12) { ft += 1; inch = 0; }
      const ftIn = el("input", { type: "number", id: q.id, value: ft, min: 0, max: 8, "aria-label": "Feet" });
      const inIn = el("input", { type: "number", value: inch, min: 0, max: 11, "aria-label": "Inches" });
      const update = () => {
        if (ftIn.value === "" && inIn.value === "") { answers[q.id] = undefined; return; }
        const total = Number(ftIn.value || 0) * 12 + Number(inIn.value || 0);
        answers[q.id] = Math.round(total * 2.54 * 10) / 10;
      };
      ftIn.addEventListener("input", update);
      inIn.addEventListener("input", update);
      row.append(ftIn, el("span", { class: "muted", text: "ft" }), inIn,
        el("span", { class: "muted", text: "in" }), select);
    }
    return row;
  }

  function renderText(q) {
    const input = el("input", { type: "text", id: q.id, maxlength: 500, value: answers[q.id] ?? "" });
    input.addEventListener("input", () => { answers[q.id] = input.value; });
    return input;
  }

  function renderQuestion(q) {
    const choice = q.type === "single" || q.type === "multi";
    const wrap = el(choice ? "fieldset" : "div", { class: "q" });
    const title = [q.label, q.required ? el("span", { class: "req", text: " *" }) : ""];
    wrap.append(choice ? el("legend", {}, ...title) : el("label", { class: "title", for: q.id }, ...title));
    if (q.type === "multi") wrap.append(el("p", { class: "muted", text: "Select all that apply." }));
    const render = { single: renderChoice, multi: renderChoice, number: renderNumber,
      height: renderHeight, text: renderText }[q.type];
    wrap.append(render(q));
    if (errors[q.id]) wrap.append(el("div", { class: "err", role: "alert", text: errors[q.id] }));
    return wrap;
  }

  function render() {
    form.replaceChildren();
    bar.style.width = `${Math.max(0, Math.min(page, sections.length)) / sections.length * 100}%`;
    backBtn.hidden = page <= -1 || page >= sections.length;
    nextBtn.hidden = page >= sections.length;
    if (page === -1) {
      stepEl.textContent = "";
      form.append(el("p", { text: config.intro }));
      nextBtn.textContent = "Start";
      return;
    }
    if (page >= sections.length) {
      stepEl.textContent = "";
      form.append(el("h2", { text: "Thank you!" }), el("p", { text: "Your answers have been saved." }));
      return;
    }
    const section = sections[page];
    stepEl.textContent = `Step ${page + 1} of ${sections.length}`;
    form.append(el("h2", { text: section.title }));
    for (const q of section.questions) if (isVisible(q)) form.append(renderQuestion(q));
    nextBtn.textContent = page === sections.length - 1 ? "Submit" : "Next";
  }

  async function submit() {
    nextBtn.disabled = true;
    try {
      const res = await fetch("/api/responses", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }),
      });
      if (res.ok) { page = sections.length; return; }
      const body = await res.json().catch(() => ({}));
      errors = body.fields || {};
      // Jump to the first section that has a server-side error.
      const idx = sections.findIndex((s) => s.questions.some((q) => errors[q.id]));
      if (idx >= 0) page = idx;
      else alert("Sorry, something went wrong. Please try again.");
    } catch {
      alert("Could not reach the server. Please check your connection and try again.");
    } finally {
      nextBtn.disabled = false;
      render();
    }
  }

  nextBtn.addEventListener("click", async () => {
    if (page >= 0) {
      errors = validateSection(sections[page]);
      if (Object.keys(errors).length) {
        render();
        form.querySelector(".err")?.closest(".q")?.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
    }
    if (page === sections.length - 1) return submit();
    page += 1;
    render();
    window.scrollTo(0, 0);
  });
  backBtn.addEventListener("click", () => { errors = {}; page -= 1; render(); window.scrollTo(0, 0); });

  render();
})();
