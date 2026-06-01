const STORAGE_KEY = "hexe_theme";
const LEGACY_STORAGE_KEY = "synthia_theme";

export function getTheme() {
  const current = localStorage.getItem(STORAGE_KEY);
  if (current) {
    return current;
  }
  const legacy = localStorage.getItem(LEGACY_STORAGE_KEY);
  if (legacy) {
    localStorage.setItem(STORAGE_KEY, legacy);
    return legacy;
  }
  return "dark";
}

export function setTheme(theme: string) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
}

export function initTheme() {
  setTheme(getTheme());
}
