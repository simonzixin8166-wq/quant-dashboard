/* MyAlpha vendor fallback (#133 6109957428 P0-2).
 * Runs synchronously right after the pinned jsDelivr tags. If a library did not load (CDN down, blocked, or
 * SRI mismatch), retry once from unpkg with the SAME exact version and SAME integrity hash (the files are
 * byte-identical on both CDNs). vendor-guard.js runs next and installs safe stubs if both attempts failed. */
(function () {
  var V = window.MAV_VENDOR = window.MAV_VENDOR || {
    chart: { global: 'Chart', version: '4.5.1', path: 'chart.js@4.5.1/dist/chart.umd.min.js',
             integrity: 'sha384-jb8JQMbMoBUzgWatfe6COACi2ljcDdZQ2OxczGA3bGNeWe+6DChMTBJemed7ZnvJ' },
    supabase: { global: 'supabase', version: '2.117.3', path: '@supabase/supabase-js@2.117.3/dist/umd/supabase.js',
                integrity: 'sha384-BWcjm9OdFth9TbhCxZPdm+gAOUMAzQy9nmTs12ioXdCcbVnJaPMn+fMUoQCLt60R' }
  };
  Object.keys(V).forEach(function (k) {
    var lib = V[k];
    lib.primary = !!window[lib.global];
    if (lib.primary) return;
    lib.fallback_attempted = true;
    try {
      document.write('<script src="https://unpkg.com/' + lib.path + '" integrity="' + lib.integrity +
                     '" crossorigin="anonymous" referrerpolicy="no-referrer"><\/script>');
    } catch (e) { lib.fallback_error = String(e && e.message || e); }
  });
})();
