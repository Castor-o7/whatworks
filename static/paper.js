// Paper pages (/papers/<slug>/): the Copy BibTeX button, and the PDF viewer's fallback for browsers
// that can't show a PDF inside the page (most phones; anything with navigator.pdfViewerEnabled false).
if (navigator.pdfViewerEnabled === false) {
  document.querySelectorAll(".paper-viewer").forEach(v => v.classList.add("no-viewer"));
}

document.querySelectorAll(".copy-btn[data-copy]").forEach(btn => {
  const status = btn.parentElement.querySelector(".copy-status");
  const say = text => {
    if (status) status.textContent = text;
    clearTimeout(btn._t);
    btn._t = setTimeout(() => { if (status) status.textContent = ""; }, 2500);
  };
  btn.addEventListener("click", async () => {
    const el = document.getElementById(btn.dataset.copy);
    const text = el.textContent;
    try {
      await navigator.clipboard.writeText(text);
      say("Copied");
      return;
    } catch (e) { /* not allowed (http, old browser): select it instead */ }
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    let copied = false;
    try { copied = document.execCommand("copy"); } catch (e) {}
    say(copied ? "Copied" : "Selected: press Ctrl+C (⌘C on a Mac) to copy");
  });
});
