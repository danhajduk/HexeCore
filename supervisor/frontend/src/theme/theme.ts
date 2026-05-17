const STORAGE_KEY = "synthia_theme";

export function getTheme() {
  return localStorage.getItem(STORAGE_KEY) || "dark";
}

export function setTheme(theme: string) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
}

export function initTheme() {
  setTheme(getTheme());
}
