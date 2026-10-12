/* Microphone buttons for text boxes marked data-voice. Records in the browser, sends the clip to this
   computer (/voice), and puts the words in the box. Nothing leaves the machine. */
(function () {
  if (!navigator.mediaDevices || !window.MediaRecorder) return;
  var token = (document.querySelector('input[name=csrf]') || {}).value || '';
  var MAX_MS = 120000;

  function setup(el) {
    var wrap = document.createElement('div');
    wrap.className = 'voice-wrap' + (el.tagName === 'TEXTAREA' ? ' tall' : '');
    el.parentNode.insertBefore(wrap, el);
    wrap.appendChild(el);
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'mic'; btn.title = 'Talk instead of typing';
    btn.setAttribute('aria-label', 'Talk instead of typing');
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z"/></svg>';
    var note = document.createElement('div');
    note.className = 'voice-note'; note.hidden = true;
    wrap.appendChild(btn); wrap.parentNode.insertBefore(note, wrap.nextSibling);
    var rec = null, chunks = [], timer = null, stream = null;

    function say(text, bad) { note.hidden = !text; note.textContent = text || ''; note.className = 'voice-note' + (bad ? ' bad' : ''); }
    function stop() { if (rec && rec.state !== 'inactive') rec.stop(); }

    btn.addEventListener('click', function () {
      if (rec && rec.state === 'recording') { stop(); return; }
      navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
        stream = s; chunks = [];
        rec = new MediaRecorder(s);
        rec.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
        rec.onstop = function () {
          clearTimeout(timer);
          stream.getTracks().forEach(function (t) { t.stop(); });
          btn.classList.remove('rec'); btn.classList.add('wait'); say('Writing down what you said...');
          var blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
          var fd = new FormData(); fd.append('csrf', token); fd.append('audio', blob, 'clip');
          fetch('/voice', { method: 'POST', body: fd }).then(function (r) { return r.json(); }).then(function (j) {
            btn.classList.remove('wait');
            if (j.error) { say(j.error, true); return; }
            if (!j.text) { say("I didn't catch anything. Try again a little closer to the mic.", true); return; }
            el.value = el.value ? el.value.replace(/\s+$/, '') + ' ' + j.text : j.text;
            el.dispatchEvent(new Event('input', { bubbles: true })); el.focus(); say('');
          }).catch(function () { btn.classList.remove('wait'); say("Couldn't reach the app. Is it still running?", true); });
        };
        rec.start(); btn.classList.add('rec'); say('Listening... tap the mic again when you are done.');
        timer = setTimeout(stop, MAX_MS);
      }).catch(function () { say('The microphone is blocked. Allow it in the browser address bar, then try again.', true); });
    });
  }
  document.querySelectorAll('[data-voice]').forEach(setup);
})();
