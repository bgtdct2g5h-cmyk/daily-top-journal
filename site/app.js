(function () {
  'use strict';
  var audios = Array.prototype.slice.call(document.querySelectorAll('audio'));
  var playAllBtn = document.getElementById('playAll');

  // 状态机：index 当前播放下标；mode 'all'=连播全部，'single'=从某条往下
  var state = { index: -1, playing: false, mode: 'single' };
  var lastBtn = null;

  function getIndex(src) {
    for (var i = 0; i < audios.length; i++) {
      if (audios[i].getAttribute('src') === src) return i;
    }
    return -1;
  }

  function stopAll() {
    audios.forEach(function (a) { a.pause(); });
  }

  function clearActive() {
    if (lastBtn) { lastBtn.classList.remove('active'); lastBtn.textContent = '▶ 朗读本条'; lastBtn = null; }
  }

  function setActive(i) {
    clearActive();
    if (i < 0 || !audios[i]) return;
    var a = audios[i];
    var b = a.nextElementSibling && a.nextElementSibling.classList && a.nextElementSibling.classList.contains('play')
      ? a.nextElementSibling : null;
    if (b) { b.classList.add('active'); lastBtn = b; }
  }

  function finish() {
    stopAll();
    state.index = -1; state.playing = false; state.mode = 'single';
    if (playAllBtn) { playAllBtn.textContent = '🔊 连播全部语音'; playAllBtn.classList.remove('active'); }
    clearActive();
    updateMediaSession(-1);
  }

  // 播放条目 i，之后自动播 i+1（end 事件链）
  function playFrom(i, mode) {
    if (i >= audios.length) { finish(); return; }
    stopAll();
    state.index = i; state.mode = mode || 'single';
    var a = audios[i];
    a.onended = function () { playFrom(i + 1, state.mode); };
    a.onerror = function () { playFrom(i + 1, state.mode); };
    setActive(i);
    updateMediaSession(i);
    var p = a.play();
    if (p && p.catch) p.catch(function () { playFrom(i + 1, state.mode); });
    state.playing = true;
    syncUI();
  }

  function syncUI() {
    if (!playAllBtn) return;
    if (state.playing && state.mode === 'all') {
      playAllBtn.textContent = '⏸ 暂停连播'; playAllBtn.classList.add('active');
    } else if (state.playing) {
      playAllBtn.textContent = '🔊 连播全部语音'; playAllBtn.classList.remove('active');
    } else if (state.mode === 'all') {
      playAllBtn.textContent = '▶ 继续连播'; playAllBtn.classList.add('active');
    } else {
      playAllBtn.textContent = '🔊 连播全部语音'; playAllBtn.classList.remove('active');
    }
  }

  // 顶部「连播全部」：播放/暂停切换
  if (playAllBtn) {
    playAllBtn.addEventListener('click', function () {
      if (state.playing) {          // 正在播 → 暂停
        if (state.index >= 0) audios[state.index].pause();
        state.playing = false;
        syncUI();
      } else if (state.mode === 'all' && state.index >= 0) { // 续播
        var i = state.index;
        audios[i].play().catch(function () {});
        state.playing = true;
        syncUI();
      } else {                       // 从头连播
        playFrom(0, 'all');
      }
    });
  }

  // 每条「朗读本条」：从该条继续往下自动播；再点同一条 → 暂停/继续
  document.querySelectorAll('button.play').forEach(function (b) {
    b.addEventListener('click', function () {
      var idx = getIndex(b.getAttribute('data-audio'));
      if (idx < 0) return;
      if (state.playing && state.index === idx) {
        var a = audios[idx];
        if (state.playing) { a.pause(); state.playing = false; }
        else { a.play().catch(function () {}); state.playing = true; }
        syncUI();
        return;
      }
      state.mode = 'single';
      playFrom(idx, 'single');
    });
  });

  // Media Session：锁屏/息屏可继续与控制
  function updateMediaSession(i) {
    if (!('mediaSession' in navigator)) return;
    if (i < 0 || !audios[i]) return;
    var a = audios[i];
    var title = a.getAttribute('data-title') || (a.getAttribute('src') || '').split('/').pop();
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: title,
        artist: '顶刊快讯',
        album: '每日顶刊快讯 · ' + (title.charAt(0) === '【' ? '' : '')
      });
      navigator.mediaSession.setActionHandler('play', function () { a.play(); });
      navigator.mediaSession.setActionHandler('pause', function () { a.pause(); });
      navigator.mediaSession.setActionHandler('previoustrack', function () { playFrom(Math.max(0, state.index - 1), state.mode); });
      navigator.mediaSession.setActionHandler('nexttrack', function () { playFrom(state.index + 1, state.mode); });
      navigator.mediaSession.setActionHandler('stop', function () { finish(); });
    } catch (e) {}
  }
})();