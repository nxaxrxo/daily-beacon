/* THE DAILY BEACON - app.js
   Zero dependencies, zero network, six behaviours. Everything here is an
   enhancement: with JS off the page still reads as a complete newspaper. */
(function () {
  "use strict";

  var doc = document;
  var body = doc.body;
  var root = doc.documentElement;
  var progress = doc.getElementById("progress");
  var bar = progress ? doc.getElementById("progress-bar") : null;
  var toggle = doc.querySelector("button.density-toggle");
  var reduce = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  var frame = 0;

  function scrollTop() {
    var scroller = doc.scrollingElement || root;
    return scroller.scrollTop || window.pageYOffset || 0;
  }

  /* 1 + 2. reading progress and the is-scrolled class, one rAF-throttled pass */
  function paint() {
    frame = 0;
    var scroller = doc.scrollingElement || root;
    var max = scroller.scrollHeight - window.innerHeight;

    if (bar) {
      var ratio = max > 0 ? scrollTop() / max : 0;
      if (ratio < 0) ratio = 0;
      if (ratio > 1) ratio = 1;
      bar.style.width = (ratio * 100).toFixed(1) + "%";
    }

    var scrolled = scrollTop() > 80;
    if (body.classList.contains("is-scrolled") !== scrolled) {
      body.classList.toggle("is-scrolled", scrolled);
    }
  }

  function queue() {
    if (frame) return;
    frame = window.requestAnimationFrame(paint);
  }

  /* 3. same-page anchors: no browser jump, hash still written, focus moved */
  function onClick(event) {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    var node = event.target;
    var link = node && node.closest ? node.closest('a[href^="#"]') : null;
    if (!link) return;

    var hash = link.getAttribute("href");
    if (!hash || hash.length < 2) return;

    var target = doc.getElementById(hash.slice(1));
    if (!target) return;

    event.preventDefault();
    target.scrollIntoView({
      behavior: reduce && reduce.matches ? "auto" : "smooth",
      block: "start"
    });

    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", hash);
    }

    if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
    try {
      target.focus({ preventScroll: true });
    } catch (err) {
      target.focus();
    }
  }

  /* 4. image fallback: one-shot error per figure image, plus a sweep of
     images that had already failed before this script ran. */
  function failFigure(image) {
    var figure = image.closest ? image.closest("figure.media") : null;
    if (!figure) return;
    figure.classList.add("media--failed");
    image.removeAttribute("src");
  }

  function watchImage(image) {
    image.addEventListener("error", function () {
      failFigure(image);
    }, { once: true });

    if (image.complete && image.naturalWidth === 0) failFigure(image);
  }

  function watchImages() {
    var images = doc.querySelectorAll("figure.media img");
    for (var i = 0; i < images.length; i++) watchImage(images[i]);
  }

  /* 5. density toggle, persisted; a throwing store leaves the page working */
  var KEY = "beacon.density";

  function storedDensity() {
    try {
      return window.localStorage.getItem(KEY);
    } catch (err) {
      return null;
    }
  }

  function saveDensity(value) {
    try {
      window.localStorage.setItem(KEY, value);
    } catch (err) {
      /* storage blocked: the toggle still applies for this page view */
    }
  }

  function setDensity(dense) {
    body.classList.toggle("dense", dense);
    if (toggle) toggle.setAttribute("aria-pressed", dense ? "true" : "false");
  }

  setDensity(storedDensity() === "dense");

  if (toggle) {
    toggle.addEventListener("click", function () {
      var dense = !body.classList.contains("dense");
      setDensity(dense);
      saveDensity(dense ? "dense" : "comfy");
    });
  }

  /* 6. sticky masthead compaction is CSS-only: body.is-scrolled is the hook. */

  window.addEventListener("scroll", queue, { passive: true });
  window.addEventListener("resize", queue, { passive: true });
  doc.addEventListener("click", onClick);

  watchImages();
  paint();
})();