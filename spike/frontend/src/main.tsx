import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./index.scss";

const root = document.getElementById("root");
if (!root) throw new Error("Не найден корневой элемент");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
