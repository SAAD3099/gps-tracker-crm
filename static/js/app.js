(function () {
  const root = document.documentElement;
  const themeButton = document.getElementById('themeToggle');
  const themeGlyph = document.getElementById('themeGlyph');

  function setTheme(theme) {
    root.dataset.theme = theme;
    try { localStorage.setItem('cts-theme', theme); } catch (e) {}
    if (themeGlyph) themeGlyph.textContent = theme === 'dark' ? '☀' : '☾';
    if (themeButton) themeButton.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
  }
  setTheme(root.dataset.theme || 'light');
  if (themeButton) {
    themeButton.addEventListener('click', function () {
      setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark');
    });
  }

  const menuToggle = document.getElementById('menuToggle');
  const sidebar = document.getElementById('sidebar');
  if (menuToggle && sidebar) {
    menuToggle.addEventListener('click', function () { sidebar.classList.toggle('open'); });
    document.addEventListener('click', function (event) {
      if (window.innerWidth <= 780 && sidebar.classList.contains('open') &&
          !sidebar.contains(event.target) && !menuToggle.contains(event.target)) {
        sidebar.classList.remove('open');
      }
    });
  }

  document.querySelectorAll('.flash-close').forEach(function (button) {
    button.addEventListener('click', function () {
      const flash = button.closest('.flash');
      if (flash) flash.remove();
    });
  });

  // Keep file selection readable in the upload form.
  document.querySelectorAll('.upload-drop input[type="file"]').forEach(function (input) {
    input.addEventListener('change', function () {
      const label = input.closest('.upload-drop');
      const title = label && label.querySelector('strong');
      if (title && input.files && input.files[0]) title.textContent = input.files[0].name;
    });
  });
})();
