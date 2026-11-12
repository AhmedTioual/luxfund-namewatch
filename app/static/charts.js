/* Shared ECharts setup: one palette read from the CSS tokens, quiet axes, responsive charts. */
(function () {
  var css = getComputedStyle(document.documentElement);
  var v = function (n) { return css.getPropertyValue(n).trim(); };
  window.NW = {
    c: {
      ink: v('--ink'), ink2: v('--ink-2'), ink3: v('--ink-3'), ink4: v('--ink-4'), rule: v('--line'), soft: v('--line-2'),
      brand: v('--brand'), removed: v('--c-removed'), vague: v('--c-vague'), reworded: v('--c-reworded'),
      added: v('--c-added'), other: v('--c-other')
    },
    font: 'Inter, "Segoe UI", system-ui, sans-serif',
    init: function (id) {
      var el = document.getElementById(id);
      if (!el || !window.echarts) return null;
      var chart = echarts.init(el, null, { renderer: 'svg' });
      if (window.ResizeObserver) new ResizeObserver(function () { chart.resize(); }).observe(el);
      else window.addEventListener('resize', function () { chart.resize(); });
      return chart;
    },
    axis: function (extra) {
      var c = window.NW.c;
      return Object.assign({
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: c.ink3, fontFamily: window.NW.font, fontSize: 11 },
        splitLine: { lineStyle: { color: c.soft } }
      }, extra || {});
    },
    tooltip: function (extra) {
      var c = window.NW.c;
      return Object.assign({
        backgroundColor: '#fff', borderColor: c.rule, borderWidth: 1, padding: [8, 10],
        textStyle: { color: c.ink, fontFamily: window.NW.font, fontSize: 12 },
        extraCssText: 'box-shadow: 0 10px 28px -12px rgba(15,26,28,.35); border-radius: 10px;'
      }, extra || {});
    },
    empty: function (id, text) {
      var el = document.getElementById(id);
      if (el) el.innerHTML = '<div class="empty"><strong>' + text + '</strong></div>';
    }
  };
})();
