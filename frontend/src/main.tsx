import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { initTheme } from "./theme/theme";
import { DEFAULT_PLATFORM_CONTROL_PLANE_NAME } from "./core/branding";
import "../../shared/theme/index.css";
import "./theme/themes/light.css";

initTheme();
document.title = DEFAULT_PLATFORM_CONTROL_PLANE_NAME;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
