const tabButtonAlignment = document.querySelector("#tabButtonAlignment");
const tabButtonGames = document.querySelector("#tabButtonGames");
const tabAlignment = document.querySelector("#tabAlignment");
const tabGames = document.querySelector("#tabGames");
const setupModalEl = document.querySelector("#setupModal");

// The alignment setup modal is a full-page overlay (position: fixed;
// inset: 0), so it sits on top of the tab bar itself and would otherwise
// block reaching the Games tab at all until alignment's own setup form is
// submitted. It must only ever be shown while the Alignment tab is the
// active one.
//
// app.js owns the modal's "has setup been completed" state via its own
// .hidden add/remove calls (on setup submit, and on Reset). Tab switching
// must temporarily force it closed without destroying that state, so a
// second class (tab-hidden) is used instead of touching .hidden directly -
// the modal is visible only when NEITHER class is present.
function showTab(name) {
  const showAlignment = name === "alignment";
  tabAlignment.classList.toggle("hidden", !showAlignment);
  tabGames.classList.toggle("hidden", showAlignment);
  tabButtonAlignment.classList.toggle("active", showAlignment);
  tabButtonGames.classList.toggle("active", !showAlignment);
  tabButtonAlignment.setAttribute("aria-selected", String(showAlignment));
  tabButtonGames.setAttribute("aria-selected", String(!showAlignment));

  setupModalEl.classList.toggle("tab-hidden", !showAlignment);
}

tabButtonAlignment.addEventListener("click", () => showTab("alignment"));
tabButtonGames.addEventListener("click", () => showTab("games"));
