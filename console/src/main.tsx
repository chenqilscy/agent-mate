import React from "react";
import ReactDOM from "react-dom/client";
import ConsoleApp from "./App";
import "../../src/styles/typography.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConsoleApp />
  </React.StrictMode>,
);
