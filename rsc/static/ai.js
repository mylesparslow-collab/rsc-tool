/* AI status: live download progress, and the "Test it" button on Setup. Plain JS, no libraries. */
(function () {
  var csrf = (document.querySelector('input[name="csrf"]') || {}).value || '';
  var boxes = document.querySelectorAll('[data-ai-download]');
  if (boxes.length) {
    var tick = function () {
      fetch('/setup/models/progress').then(function (r) { return r.json(); }).then(function (d) {
        if (!d.running) { location.reload(); return; }
        boxes.forEach(function (b) {
          var pct = b.querySelector('[data-pct]'), bar = b.querySelector('progress');
          if (pct) pct.textContent = d.running.pct + '%';
          if (bar) bar.value = d.running.pct;
        });
        setTimeout(tick, 2000);
      }).catch(function () { setTimeout(tick, 4000); });
    };
    setTimeout(tick, 1500);
  }
  var btn = document.querySelector('[data-ai-test]');
  if (btn) {
    var out = document.querySelector('[data-ai-test-result]');
    btn.addEventListener('click', function () {
      btn.disabled = true; out.textContent = 'Asking the model...';
      fetch('/setup/models/test', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'csrf=' + encodeURIComponent(csrf) })
        .then(function (r) { return r.json(); })
        .then(function (d) { out.textContent = d.ok ? 'Working. ' + d.model + ' answered in ' + d.seconds + ' seconds.' : 'Not working: ' + (d.error || 'no answer'); })
        .catch(function () { out.textContent = 'Not working: the page could not reach the app.'; })
        .then(function () { btn.disabled = false; });
    });
  }
})();
