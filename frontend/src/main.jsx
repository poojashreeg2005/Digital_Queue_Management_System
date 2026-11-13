import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./style.css";

// Mounts the React application inside the root element in index.html.
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
