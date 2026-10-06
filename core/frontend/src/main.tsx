import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { initTheme } from "./theme/theme";
import { DEFAULT_PLATFORM_CORE_NAME } from "./core/branding";
import "../../shared/theme/index.css";
import "./theme/themes/light.css";

initTheme();
document.title = DEFAULT_PLATFORM_CORE_NAME;
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => void navigator.serviceWorker.register("/service-worker.js?v=3"));
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
