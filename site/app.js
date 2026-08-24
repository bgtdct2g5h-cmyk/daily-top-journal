// 单条朗读
document.querySelectorAll('button.play').forEach(function (b) {
  b.addEventListener('click', function () {
    var src = b.getAttribute('data-audio');
    var audios = document.querySelectorAll('audio');
    for (var i = 0; i < audios.length; i++) {
      if (audios[i].getAttribute('src') === src) { audios[i].play(); break; }
    }
  });
});
// 连播全部
var playAll = document.getElementById('playAll');
if (playAll) {
  playAll.addEventListener('click', function () {
    var audios = Array.prototype.slice.call(document.querySelectorAll('audio'));
    var btn = playAll;
    btn.disabled = true;
    btn.textContent = '🔊 播放中…';
    (function next(i) {
      if (i >= audios.length) { btn.disabled = false; btn.textContent = '🔊 连播全部语音'; return; }
      var a = audios[i];
      a.onended = function () { next(i + 1); };
      a.onerror = function () { next(i + 1); };
      a.play().catch(function () { next(i + 1); });
    })(0);
  });
}